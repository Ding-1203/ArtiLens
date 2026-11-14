"""Liveness and readiness endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Request

from artilens import __version__
from artilens.core.config import Settings

router = APIRouter(tags=["ops"])


@router.get("/health")
async def health(request: Request) -> dict[str, object]:
    settings: Settings = request.app.state.settings
    return {
        "status": "ok",
        "app": settings.app_name,
        "version": __version__,
        "env": settings.env,
        "llm_enabled": settings.llm_enabled,
    }


@router.get("/ready")
async def ready(request: Request) -> dict[str, object]:
    """Readiness probe: reports which optional subsystems are configured."""
    settings: Settings = request.app.state.settings
    return {
        "status": "ready",
        "database": "sqlite" if settings.is_sqlite else "postgres",
        "vector_backend": settings.vector_backend,
        "llm": "configured" if settings.llm_enabled else "missing_api_key",
    }
