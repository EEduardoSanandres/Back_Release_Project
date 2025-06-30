# backend/api/services/graph_service.py
from __future__ import annotations

from typing import Any
import networkx as nx
from networkx.readwrite import json_graph
from bson import ObjectId

from backend.api.schemas.requests import GraphIn
from backend.api.schemas.responses import GraphOut
from backend.app.database import db


class GraphService:
    """Builds a dependency graph (NetworkX DiGraph) for a given project."""

    async def create_graph(self, body: GraphIn) -> GraphOut:
        """
        • Loads all user-stories belonging to `project_id`.
        • Adds nodes + dependency edges.
        • Serialises to node-link JSON and returns only the keys that
          GraphOut expects (`nodes`, `links`).
        """
        # 1) fetch stories from Mongo
        stories: list[dict[str, Any]] = await db.user_stories.find(
            {"project_id": ObjectId(body.project_id)}
        ).to_list(None)

        # 2) build directed graph
        g = nx.DiGraph()
        for s in stories:
            # optional tag filter
            if body.filter_tags and not set(body.filter_tags) & set(s.get("tags", [])):
                continue

            story_id = str(s["_id"])
            g.add_node(story_id, label=s["action"])

            for dep in s.get("dependencies", []):
                g.add_edge(str(dep), story_id)

        # 3) layout hook (currently client-side)
        #    if body.layout != "dagre": …  # TODO

        # 4) serialise and prune extra keys
        raw = json_graph.node_link_data(g)
        data: GraphOut = {                # type: ignore[assignment]
            "project_id": body.project_id,
            "nodes": raw["nodes"],
            "links": raw["links"],
        }
        return data
