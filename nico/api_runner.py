from __future__ import annotations

import os

import uvicorn


def main() -> None:
    """Start the complete local NICO API using environment-controlled settings."""

    host = os.getenv("NICO_API_HOST", "127.0.0.1")
    port = int(os.getenv("NICO_API_PORT", "8000"))
    reload_enabled = os.getenv("NICO_API_RELOAD", "true").lower() == "true"
    uvicorn.run("nico.api.production:app", host=host, port=port, reload=reload_enabled)
