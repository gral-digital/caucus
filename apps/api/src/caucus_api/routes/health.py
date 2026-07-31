"""Healthcheck endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from caucus_api.deps import get_db_session, get_vectorstore
from caucus_rag_core.vectorstore.qdrant_store import QdrantStore

router = APIRouter()


@router.get("/health/live")
async def live() -> dict[str, str]:
    """Liveness: è il processo vivo e risponde?"""
    return {"status": "ok"}


@router.get("/health/ready")
async def ready(
    session: AsyncSession = Depends(get_db_session),
    vs: QdrantStore = Depends(get_vectorstore),
) -> dict[str, object]:
    """Readiness: dipendenze critiche raggiungibili?"""
    checks: dict[str, bool] = {}
    try:
        await session.execute(text("SELECT 1"))
        checks["postgres"] = True
    except Exception:  # pragma: no cover - diagnostic
        checks["postgres"] = False

    try:
        collections = await vs.client.get_collections()
        checks["qdrant"] = bool(collections)
    except Exception:  # pragma: no cover - diagnostic
        checks["qdrant"] = False

    return {
        "status": "ok" if all(checks.values()) else "degraded",
        "checks": checks,
    }
