from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from qdrant_client import QdrantClient
from app import db as db_module
from app.config import get_settings

router = APIRouter()


@router.get("/health/db")
async def health_db():
    try:
        await db_module.ping_db()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="db unavailable")


async def ping_qdrant() -> None:
    s = get_settings()
    client = QdrantClient(url=s.qdrant_url)
    await run_in_threadpool(client.get_collections)


@router.get("/health/qdrant")
async def health_qdrant():
    try:
        await ping_qdrant()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="qdrant unavailable")
