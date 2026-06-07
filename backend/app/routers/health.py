from fastapi import APIRouter, HTTPException
from app import db as db_module

router = APIRouter()


@router.get("/health/db")
async def health_db():
    try:
        await db_module.ping_db()
        return {"status": "ok"}
    except Exception:
        raise HTTPException(status_code=503, detail="db unavailable")
