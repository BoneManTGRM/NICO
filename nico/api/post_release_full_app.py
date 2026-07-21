from __future__ import annotations

import os
from typing import Mapping

from fastapi import FastAPI

from nico.api.post_release_app import (
    _database_dependencies,
    _truthy,
    build_app as build_base_app,
)
from nico.post_release_extensions import install_post_release_extensions


VERSION = "nico.post_release_full_app.v1"


def build_app(
    *,
    base_app: FastAPI | None = None,
    environ: Mapping[str, str] | None = None,
) -> FastAPI:
    selected: Mapping[str, str] = dict(os.environ if environ is None else environ)
    target = build_base_app(base_app=base_app, environ=selected)

    enable_admin = _truthy(selected.get("NICO_ENABLE_PROVIDER_ADMIN"))
    enable_operational = _truthy(selected.get("NICO_ENABLE_OPERATIONAL_API"))
    connection_factory, dialect, extension_storage = _database_dependencies(
        selected,
        required=enable_admin or enable_operational,
    )
    extensions, extension_closeables = install_post_release_extensions(
        target,
        environ=selected,
        connection_factory=connection_factory,
        database_dialect=dialect,
    )

    status = dict(getattr(target.state, "nico_post_release_runtime", {}) or {})
    status["full_app_wrapper"] = VERSION
    status["extensions"] = extensions
    if enable_admin or enable_operational:
        status["extension_storage"] = extension_storage
    status["human_review_required"] = True
    status["client_delivery_allowed"] = False
    target.state.nico_post_release_runtime = status

    existing = list(getattr(target.state, "nico_post_release_closeables", ()) or ())
    for item in extension_closeables:
        if item not in existing:
            existing.append(item)
    target.state.nico_post_release_closeables = existing

    if existing and not getattr(target.state, "nico_post_release_shutdown_registered", False):
        def close_clients() -> None:
            for item in list(getattr(target.state, "nico_post_release_closeables", ()) or ()):
                close = getattr(item, "close", None)
                if callable(close):
                    close()

        target.router.add_event_handler("shutdown", close_clients)
        target.state.nico_post_release_shutdown_registered = True

    return target


app = build_app()


__all__ = ["VERSION", "app", "build_app"]
