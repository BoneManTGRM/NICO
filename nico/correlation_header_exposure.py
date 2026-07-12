from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response

from nico.operational_observability import CORRELATION_HEADER


def _exposed_headers(response: Response) -> str:
    existing = response.headers.get("Access-Control-Expose-Headers", "")
    values = [item.strip() for item in existing.split(",") if item.strip()]
    if not any(item.lower() == CORRELATION_HEADER.lower() for item in values):
        values.append(CORRELATION_HEADER)
    return ", ".join(values)


async def correlation_header_exposure_middleware(
    request: Request,
    call_next: Callable[[Request], Awaitable[Response]],
) -> Response:
    response = await call_next(request)
    response.headers["Access-Control-Expose-Headers"] = _exposed_headers(response)
    return response


def install_correlation_header_exposure(target: FastAPI) -> dict[str, object]:
    reused = bool(getattr(target.state, "nico_correlation_header_exposure", False))
    if not reused:
        target.middleware("http")(correlation_header_exposure_middleware)
        target.state.nico_correlation_header_exposure = True
    return {
        "installed": True,
        "middleware_reused": reused,
        "exposed_header": CORRELATION_HEADER,
    }


__all__ = [
    "correlation_header_exposure_middleware",
    "install_correlation_header_exposure",
]
