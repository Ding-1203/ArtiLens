"""v1 API aggregate router."""

from __future__ import annotations

from fastapi import APIRouter

from artilens.api.v1 import health

api_router = APIRouter()
api_router.include_router(health.router)
