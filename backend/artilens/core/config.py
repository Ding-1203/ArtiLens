"""Typed application settings.

Every runtime knob lives here. Adapters read settings, never `os.environ`
directly, so the whole app can be reconfigured from one `.env` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ARTILENS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- app ---
    app_name: str = "ArtiLens"
    env: Literal["local", "dev", "prod"] = "local"
    debug: bool = False
    log_json: bool = False

    # --- storage ---
    data_dir: Path = Path("./data")
    database_url: str = "sqlite+aiosqlite:///./data/artilens.db"

    # --- llm (DashScope OpenAI-compatible endpoint by default) ---
    llm_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    llm_api_key: SecretStr | None = None
    llm_model: str = "qwen-plus"
    llm_timeout_s: float = 120.0

    # --- retrieval ---
    vector_backend: Literal["lance", "pgvector"] = "lance"
    embedding_model: str = "text-embedding-v4"
    embedding_dim: int = 1024
    chunk_size: int = 900
    chunk_overlap: int = 120
    retrieve_top_k: int = 8
    retrieve_rerank_top_n: int = 4

    # --- upload ---
    upload_max_mb: int = 50

    # --- http ---
    cors_origins: list[str] = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]

    # ---------------------------------------------------------------- derived
    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def parsed_dir(self) -> Path:
        return self.data_dir / "parsed"

    @property
    def vectors_dir(self) -> Path:
        return self.data_dir / "vectors"

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def llm_enabled(self) -> bool:
        return self.llm_api_key is not None and bool(self.llm_api_key.get_secret_value())

    def ensure_dirs(self) -> None:
        """Create the runtime directory tree. Safe to call repeatedly."""
        for path in (self.data_dir, self.uploads_dir, self.parsed_dir, self.vectors_dir):
            path.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
