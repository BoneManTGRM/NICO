from __future__ import annotations

import asyncio
from threading import Event, Timer
from time import monotonic
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI

from nico.comprehensive_api_routes import register_comprehensive_api_routes


def test_long_comprehensive_intake_does_not_starve_event_loop() -> None:
    """Repository snapshot capture must not starve lightweight ASGI requests."""

    started = Event()
    release = Event()

    def blocking_snapshot(context: dict[str, object]) -> dict[str, object]:
        del context
        started.set()
        if not release.wait(timeout=2.0):
            raise RuntimeError("blocking_snapshot_test_release_timeout")
        raise ValueError("blocking_snapshot_test_complete")

    app = FastAPI()
    register_comprehensive_api_routes(app)

    @app.get("/health-intake-concurrency-probe")
    async def health_intake_concurrency_probe() -> dict[str, str]:
        return {"status": "ok"}

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://nico-test",
        ) as client:
            safety_release = Timer(1.0, release.set)
            safety_release.daemon = True
            safety_release.start()
            with patch(
                "nico.comprehensive_api_routes.capture_repository_snapshot",
                new=blocking_snapshot,
            ), patch(
                "nico.comprehensive_api_routes._controller",
                return_value=SimpleNamespace(_service=None),
            ):
                intake = asyncio.create_task(
                    client.post(
                        "/assessment/comprehensive-intake",
                        json={
                            "repository": "BoneManTGRM/NICO",
                            "authorized": True,
                            "authorization_confirmed": True,
                        },
                    )
                )
                try:
                    began = await asyncio.wait_for(
                        asyncio.to_thread(started.wait, 0.25),
                        timeout=0.5,
                    )
                    assert began is True

                    probe_started = monotonic()
                    health = await asyncio.wait_for(
                        client.get("/health-intake-concurrency-probe"),
                        timeout=0.5,
                    )
                    assert health.status_code == 200
                    assert health.json() == {"status": "ok"}
                    assert monotonic() - probe_started < 0.5
                finally:
                    release.set()
                    safety_release.cancel()

                response = await asyncio.wait_for(intake, timeout=1.0)
                assert response.status_code == 422
                assert response.json()["detail"] == "blocking_snapshot_test_complete"

    asyncio.run(exercise())
