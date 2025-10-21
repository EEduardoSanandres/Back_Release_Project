from __future__ import annotations
import base64, io, json, logging, os, re, anyio, time
from datetime import datetime
from typing import List, Generator, Iterable, Optional, Tuple, Literal

import google.generativeai as genai
import httpx
from fastapi import UploadFile, HTTPException
from pydantic import HttpUrl
from pypdf import PdfReader, errors as pdf_errors
from bson import ObjectId
from pymongo.errors import BulkWriteError, DuplicateKeyError  # ⬅️ añadido

# ───────── Stubs si no carga el paquete del proyecto ─────────
try:
    from ..schemas.responses import PdfStoryOut, PdfImportOut
    from ...app.db import db
except (ImportError, ValueError):
    logging.warning("No se pudieron resolver las importaciones relativas. Usando stubs.")
    from pydantic import BaseModel
    class PdfStoryOut(BaseModel):
        epic: str; us: str; nombre: str; descripcion: str; criterios: List[str]
    class PdfImportOut(BaseModel):
        project_id: str; historias: List[PdfStoryOut]
        total_prompt_tokens: int; total_completion_tokens: int; total_processing_time_ms: float
    class MockCollection:
        async def find(self, *a, **k): return []
        async def find_one(self, *a, **k): return None
        async def insert_one(self, *a, **k):
            class R: inserted_id = ObjectId()
            return R()
        async def insert_many(self, *a, **k): pass
        async def update_one(self, *a, **k): pass
    class MockDb: user_stories = MockCollection(); projects = MockCollection()
    db = MockDb()

# ───────── LLM config ─────────
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-pro"
CHARS = 18_000

PROMPT = """
Eres un extractor experto de Historias de Usuario (HU).
Analiza el texto suministrado y genera EXCLUSIVAMENTE el bloque comprendido entre
BEGIN_JSON y END_JSON (no incluyas ni BEGIN_JSON ni END_JSON en la respuesta),
sin explicaciones adicionales.

↳ Formato (JSON por línea):
{
  "epic"       : "<código o título de la épica>",
  "us"         : "<código de la historia, ej. '001' o 'us-045'>",
  "nombre"     : "<nombre breve de la HU>",
  "descripcion": "<frase 'Como … quiero … para …'>",
  "criterios"  : ["<Criterio 1>", "<Criterio 2>", …]
}

Reglas estrictas
1. Devuelve UNA línea JSON por historia.
2. Usa exactamente las claves indicadas, en español, en ese orden.
3. Todos los valores son strings, excepto "criterios", que es un array de strings.
4. Sin saltos de línea dentro de un valor.
5. No incluyas comentarios ni caracteres fuera del bloque JSON.
6. Si no tienes criterios, devuelve "criterios": []
7. No uses retornos de carro ni tabulaciones: cada historia en **una sola línea**.
8. La salida debe ser JSON válido según RFC 8259.

Ejemplo
BEGIN_JSON
{"epic":"001","us":"001","nombre":"Búsqueda por palabra clave","descripcion":"Como Comprador quiero buscar productos por palabra clave para encontrar rápidamente lo que necesito.","criterios":["La búsqueda devuelve solo coincidencias de título o descripción.","La respuesta tarda < 30 ms.","Mensaje \"No se encontraron productos\" si no hay coincidencias."]}
END_JSON

El texto a analizar es:
"""

class PdfService:
    async def extract_stories(
        self,
        *,
        pdf_file: UploadFile | None,
        pdf_url:  HttpUrl    | None,
        pdf_b64:  str        | None,
        user_id:  str        | None = None,
        dedupe_mode: Literal["none","project","global"] = None,
        force_llm: bool | None = None,
    ) -> PdfImportOut:
        """
        dedupe_mode:
          - "project" (default): dedup solo dentro del proyecto actual → permite reimportar el mismo PDF en proyectos nuevos.
          - "none": no deduplica (inserta todo tal cual).
          - "global": dedup por code en toda la colección (no recomendado si quieres reprocesar).
        force_llm:
          - True: ignora parser determinista y llama LLM (útil para pruebas).
        También puedes controlar por env:
          EXTRACT_DEDUPE_MODE = none|project|global
          EXTRACT_FORCE_LLM   = 1|0
        """
        dedupe_mode = dedupe_mode or os.getenv("EXTRACT_DEDUPE_MODE", "project")
        force_llm = bool(int(os.getenv("EXTRACT_FORCE_LLM", "0"))) if force_llm is None else force_llm

        # 1) PDF → texto
        pdf_bytes = await self._read(pdf_file, pdf_url, pdf_b64)
        raw_text  = self._pdf_to_text(pdf_bytes)
        text      = self._normalize_text(raw_text)

        # 2) Proyecto
        project_id = await self._create_project(self._filename(pdf_file, pdf_url), user_id)

        historias: list[PdfStoryOut] = []
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_processing_time_ms = 0.0

        # 3) Extracción
        if not force_llm:
            parsed = self._extract_structured_stories(text)
            historias.extend(parsed)
            logging.info(f"[extract] Parser determinista → {len(parsed)} HU")
        else:
            logging.info("[extract] FORCE_LLM=1 → saltando parser determinista")

        # Bloques detectados (aunque no tengan criterios) para LLM por bloque
        all_blocks = list(self._iter_story_blocks(text, allow_without_criterios=True))

        # Fallbacks LLM
        need_block_llm = force_llm or (all_blocks and len(historias) < len(all_blocks))
        need_chunk_llm = force_llm or (not all_blocks and not historias)

        if need_block_llm and all_blocks:
            parsed_us = {h.us for h in historias}
            pending = [(e,u,n,b) for (e,u,n,b) in all_blocks if u not in parsed_us]
            logging.info(f"[extract] LLM por bloque → {len(pending)} pendientes")
            for epic, us, name, block in pending:
                raw, pt, ct, proc = await self._chat(self._tight_prompt_for_block(epic, us, name, block))
                total_prompt_tokens += pt; total_completion_tokens += ct; total_processing_time_ms += proc
                historias.extend(self._parse_objs(raw))

        if need_chunk_llm:
            logging.info("[extract] LLM por chunks (sin encabezados detectados)")
            for chunk in self._chunks(text, size=min(CHARS, 16000), overlap_ratio=0.15):
                raw, pt, ct, proc = await self._chat(PROMPT + chunk)
                total_prompt_tokens += pt; total_completion_tokens += ct; total_processing_time_ms += proc
                historias.extend(self._parse_objs(raw))

        # 4) De-duplicación según modo
        docs = []
        seen_run: set[str] = set()  # dedupe dentro del mismo lote
        existing_codes: set[str] = set()

        if dedupe_mode == "global":
            existing_codes = {
                d["code"]
                async for d in db.user_stories.find({}, {"code": 1, "_id": 0})
            }
        elif dedupe_mode == "project":
            existing_codes = {
                d["code"]
                async for d in db.user_stories.find({"project_id": project_id}, {"code": 1, "_id": 0})
            }
        elif dedupe_mode == "none":
            existing_codes = set()

        for h in historias:
            # dedupe dentro del mismo batch (mismo 'us' repetido)
            if dedupe_mode != "none" and (h.us in seen_run or h.us in existing_codes):
                continue
            seen_run.add(h.us)

            docs.append({
                "project_id":  project_id,
                "epica":       h.epic,
                "nombre":      h.nombre,
                "descripcion": h.descripcion,
                "criterios":   h.criterios,
                "code":        h.us,                           # mantiene semántica original
                "code_full":   f"{project_id}::{h.us}",        # opcional para índice único alterno
                "created_at":  datetime.utcnow(),
            })

        # 5) Inserción robusta (soporta unique en code_full o {project_id,code})
        if docs:
            try:
                await db.user_stories.insert_many(docs, ordered=False)
            except BulkWriteError as e:
                logging.warning(f"[insert] BulkWriteError: {getattr(e, 'details', '')}")
                # Intento por-doc para rescatar válidos si hay colisiones
                for d in docs:
                    try:
                        await db.user_stories.insert_one(d)
                    except DuplicateKeyError:
                        # Ya existe según índice único → continuar sin romper
                        continue
                    except Exception as ex:
                        logging.error(f"[insert_one] unexpected: {ex}")

        await db.projects.update_one(
            {"_id": project_id},
            {"$set": {
                "total_prompt_tokens": total_prompt_tokens,
                "total_completion_tokens": total_completion_tokens,
                "total_processing_time_ms": total_processing_time_ms,
            }}
        )

        return PdfImportOut(
            project_id=str(project_id),
            historias=historias,
            total_prompt_tokens=total_prompt_tokens,
            total_completion_tokens=total_completion_tokens,
            total_processing_time_ms=total_processing_time_ms,
        )

    # ───────── LLM ─────────
    async def _chat(self, full_prompt: str) -> tuple[str, int, int, float]:
        model = genai.GenerativeModel(MODEL)
        prompt_tokens = completion_tokens = 0
        processing_time_ms = 0.0

        def _generate():
            nonlocal prompt_tokens, completion_tokens, processing_time_ms
            try:
                t0 = time.perf_counter()
                resp = model.generate_content(
                    full_prompt,
                    generation_config={"temperature": 0.15, "max_output_tokens": 8192},
                    safety_settings={
                        'HARM_CATEGORY_HARASSMENT': 'BLOCK_NONE',
                        'HARM_CATEGORY_HATE_SPEECH': 'BLOCK_NONE',
                        'HARM_CATEGORY_SEXUALLY_EXPLICIT': 'BLOCK_NONE',
                        'HARM_CATEGORY_DANGEROUS_CONTENT': 'BLOCK_NONE',
                    }
                )
                processing_time_ms = (time.perf_counter() - t0) * 1000
                um = getattr(resp, "usage_metadata", None)
                if um:
                    prompt_tokens = um.prompt_token_count or 0
                    completion_tokens = um.candidates_token_count or 0
                return getattr(resp, "text", "") or ""
            except Exception as e:
                logging.warning(f"[llm] error o vacío: {e}")
                return ""

        raw_text = await anyio.to_thread.run_sync(_generate)
        return raw_text, prompt_tokens, completion_tokens, processing_time_ms

    def _parse_objs(self, raw: str) -> List[PdfStoryOut]:
        historias: list[PdfStoryOut] = []
        if not raw: return historias
        raw = raw.replace("BEGIN_JSON", "").replace("END_JSON", "")
        raw = raw.replace("```json", "").replace("```", "").strip()

        for line in raw.splitlines():
            line = line.strip()
            if not line: continue
            candidates = []
            if line.startswith("{") and line.endswith("}"):
                candidates = [line]
            elif "}{" in line:
                parts = line.split("}{")
                candidates = ["{"+parts[0].lstrip("{").strip(), *[p.strip() for p in parts[1:-1]], parts[-1].rstrip("}").strip()+"}"]
                candidates = [c for c in candidates if c.startswith("{") and c.endswith("}")]

            for cand in (candidates or [line]):
                try:
                    data = json.loads(cand)
                    if not isinstance(data.get("criterios"), list):
                        data["criterios"] = []
                    historias.append(PdfStoryOut(**data))
                except Exception:
                    logging.debug(f"[parse] descartado: {cand[:120]}…")
        return historias

    # ───────── Proyecto ─────────
    async def _create_project(self, name: str, user_id: str | None = None) -> ObjectId:
        last = await db.projects.find_one(sort=[("created_at", -1)])
        seq  = int(last["code"].split("-")[1]) + 1 if last and "code" in last else 1
        owner_id = ObjectId(user_id) if user_id and ObjectId.is_valid(user_id) else None
        res = await db.projects.insert_one({
            "code":        f"PROJ-{seq:03d}",
            "name":        name or "PDF importado",
            "description": "",
            "owner_id":    owner_id,
            "created_at":  datetime.utcnow(),
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_processing_time_ms": 0.0,
        })
        return res.inserted_id

    # ───────── PDF I/O ─────────
    async def _read(self, f, url, b64) -> bytes:
        if f:
            data = await f.read()
        elif url:
            async with httpx.AsyncClient() as c:
                data = (await c.get(str(url))).content
        elif b64:
            data = base64.b64decode(b64)
        else:
            raise HTTPException(400, "Proporciona pdf_file, pdf_url o pdf_b64")
        if not data.startswith(b"%PDF"):
            raise HTTPException(415, "El archivo no es PDF")
        return data

    def _pdf_to_text(self, b: bytes) -> str:
        try:
            reader = PdfReader(io.BytesIO(b))
        except pdf_errors.PdfStreamError:
            raise HTTPException(400, "PDF dañado")
        return "\n".join(p.extract_text() or "" for p in reader.pages)

    # ───────── Normalización ─────────
    def _normalize_text(self, text: str) -> str:
        text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)     # une cortes por guion
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\r\n?", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    # ───────── Bloques / Parser ─────────
    def _iter_story_blocks(self, text: str, *, allow_without_criterios: bool = False
                           ) -> Iterable[Tuple[str, str, str, str]]:
        header_re = re.compile(r"(?m)^(?P<epic>\d{3})\s+(?P<us>\d{3})\s+(?P<name>.+)$")
        matches = list(header_re.finditer(text))
        for i, m in enumerate(matches):
            epic, us, name = m.group("epic"), m.group("us"), m.group("name").strip()
            start, end = m.start(), (matches[i+1].start() if i+1 < len(matches) else len(text))
            block = text[start:end].strip()

            has_crit = ("Criterios de Aceptación" in block or "Criterios de Aceptacion" in block)
            has_como = "Como" in block
            if allow_without_criterios or (has_crit and has_como):
                yield (epic, us, name, block)

    def _extract_structured_stories(self, text: str) -> List[PdfStoryOut]:
        historias: list[PdfStoryOut] = []
        for epic, us, name, block in self._iter_story_blocks(text, allow_without_criterios=False):
            criterios = self._parse_criterios(block)
            descripcion = self._parse_descripcion(block)
            if descripcion:
                historias.append(PdfStoryOut(epic=epic, us=us, nombre=name, descripcion=descripcion, criterios=criterios))
        return historias

    def _parse_criterios(self, block: str) -> List[str]:
        idx_crit = block.find("Criterios de Aceptación")
        if idx_crit == -1: idx_crit = block.find("Criterios de Aceptacion")
        if idx_crit == -1: return []
        tail = block[idx_crit:]; idx_desc = tail.find("\nComo"); tail = tail if idx_desc == -1 else tail[:idx_desc]
        tail = tail.replace("Criterios de Aceptación Descripción", "").replace("Criterios de Aceptacion Descripcion", "")
        criterios: List[str] = []
        for raw in tail.splitlines():
            line = raw.strip()
            if not line: continue
            if re.match(r'^(-|—|•|\*|\d+\)|\d+\.)\s+', line):
                criterios.append(re.sub(r'^(-|—|•|\*|\d+\)|\d+\.)\s+', '', line).strip())
            elif line.lower().startswith("criterios:"):
                criterios += [s.strip() for s in line.split(":",1)[1].split(";") if s.strip()]
        return criterios

    def _parse_descripcion(self, block: str) -> Optional[str]:
        m = re.search(r"Como(?:\s+[^\n]+)?(?:\n[^\n]+){0,4}", block)
        if not m: return None
        frag = " ".join(s.strip() for s in m.group(0).splitlines() if s.strip())
        frag = re.sub(r"\s+", " ", frag).strip()
        if not frag.endswith("."): frag += "."
        return frag

    # ───────── LLM por bloque ─────────
    def _tight_prompt_for_block(self, epic: str, us: str, nombre: str, block: str) -> str:
        header = (
            "Instrucciones estrictas:\n"
            "- Devuelve exactamente UNA línea JSON con las claves en este orden: epic, us, nombre, descripcion, criterios.\n"
            f'- Usa los códigos dados: epic="{epic}" y us="{us}".\n'
            f'- Usa el nombre dado exactamente: "{nombre}".\n'
            '- "criterios" debe ser un array de strings.\n'
            "- Sin texto adicional.\n\nBEGIN_JSON\n"
        )
        sample = f'{{"epic":"{epic}","us":"{us}","nombre":"{nombre}","descripcion":"<Como … quiero … para …>","criterios":["<Criterio 1>","<Criterio 2>"]}}'
        return PROMPT + header + block + "\n" + sample + "\nEND_JSON"

    # ───────── Troceo ─────────
    def _chunks(self, text: str, size: int = CHARS, overlap_ratio: float = 0.1) -> Generator[str, None, None]:
        if len(text) <= size:
            yield text; return
        overlap = max(200, min(int(size * overlap_ratio), 2000))
        start = 0
        while True:
            end = start + size
            yield text[start:end]
            if end >= len(text): break
            start += (size - overlap)

    @staticmethod
    def _filename(f: UploadFile | None, url: HttpUrl | None) -> str:
        if f and getattr(f, "filename", None): return f.filename
        if url:
            path = url.path if hasattr(url, "path") else str(url).split("?")[0]
            return path.rsplit("/", 1)[-1] or "PDF importado"
        return "PDF importado"
