"""`python -m artilens` — start the dev server."""

from __future__ import annotations

import uvicorn

from artilens.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "artilens.main:app",
        host="127.0.0.1",
        port=8000,
        reload=settings.debug,
        app_dir="backend",
    )


if __name__ == "__main__":
    main()
