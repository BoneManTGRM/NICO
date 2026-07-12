from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.correlation_header_exposure import install_correlation_header_exposure
from nico.operational_observability import CORRELATION_HEADER, install_operational_observability


def test_browser_clients_can_read_the_correlation_header() -> None:
    app = FastAPI()
    install_operational_observability(app)
    install_correlation_header_exposure(app)

    @app.get("/ok")
    def ok() -> dict[str, str]:
        return {"status": "ok"}

    response = TestClient(app).get("/ok", headers={CORRELATION_HEADER: "browser-12345678"})

    assert response.status_code == 200
    assert response.headers[CORRELATION_HEADER] == "browser-12345678"
    exposed = response.headers.get("Access-Control-Expose-Headers", "")
    assert CORRELATION_HEADER.lower() in {item.strip().lower() for item in exposed.split(",")}


def test_correlation_header_exposure_preserves_existing_exposed_headers() -> None:
    app = FastAPI()
    install_operational_observability(app)
    first = install_correlation_header_exposure(app)
    second = install_correlation_header_exposure(app)

    @app.get("/existing")
    def existing():
        from fastapi.responses import JSONResponse

        return JSONResponse(
            {"status": "ok"},
            headers={"Access-Control-Expose-Headers": "X-Existing-Header"},
        )

    response = TestClient(app).get("/existing")
    exposed = {item.strip().lower() for item in response.headers["Access-Control-Expose-Headers"].split(",")}

    assert first["middleware_reused"] is False
    assert second["middleware_reused"] is True
    assert "x-existing-header" in exposed
    assert CORRELATION_HEADER.lower() in exposed
