import os
from pathlib import Path
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

# Load .env from project root (go up 2 levels from backend/app/)
env_path = Path(__file__).resolve().parent.parent.parent / ".env"
load_dotenv(env_path)

# Support both MONGODB_URI (preferred) and MONGO_URI (legacy)
MONGO_URI = os.getenv("MONGODB_URI") or os.getenv("MONGO_URI", "mongodb://localhost:27017")

print(f"[DB] Connecting to MongoDB: {MONGO_URI[:30]}...")
mongo_client = AsyncIOMotorClient(MONGO_URI)
db           = mongo_client["tdp_prototype"]

__all__ = ["db", "mongo_client"]
