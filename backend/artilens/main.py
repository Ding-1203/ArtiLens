"""Application factory.

Run locally:
    uvicorn artilens.main:app --reload --port 8000
or:
    python -m artilens
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from artilens import __version__
from artilens.api.v1.router import api_router
from artilens.core.config import Settings, get_settings
from artilens.core.errors import register_error_handlers
from artilens.core.logging import get_logger, setup_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)
    log = get_logger(__name__)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        settings.ensure_dirs()
        log.info(
            "app_start",
            version=__version__,
            env=settings.env,
            data_dir=str(settings.data_dir.resolve()),
            database="sqlite" if settings.is_sqlite else "postgres",
            vector_backend=settings.vector_backend,
        )
        yield
        log.info("app_stop")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description="AI paper reading assistant",
        lifespan=lifespan,
    )
    app.state.settings = settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_error_handlers(app)
    app.include_router(api_router, prefix="/api/v1")

    return app


app = create_app()
