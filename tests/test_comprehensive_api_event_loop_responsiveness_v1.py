from __future__ import annotations

import asyncio
from threading import Event, Timer
from time import monotonic
from typing import Any, cast

import httpx
from fastapi import FastAPI

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_run_service import ComprehensiveRunService


class _BlockingResumeService:
    def __init__(self, started: Event, release: Event) -> None:
        self.started = started
        self.release = release

    def resume(self, run_id: str, *, max_stages: int | None = None) -> dict[str, Any]:
        del run_id, max_stages
        self.started.set()
        if not self.release.wait(timeout=2.0):
            raise RuntimeError("blocking_resume_test_release_timeout")
        raise ValueError("blocking_resume_test_complete")


def test_long_comprehensive_continuation_does_not_starve_event_loop() -> None:
    """A long synchronous stage must not make lightweight API requests unresponsive."""

    started = Event()
    release = Event()
    service = cast(ComprehensiveRunService, _BlockingResumeService(started, release))
    controller = ComprehensiveApiController(service)
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)

    @app.get("/health-concurrency-probe")
    async def health_concurrency_probe() -> dict[str, str]:
        return {"status": "ok"}

    async def exercise() -> None:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport,
            base_url="http://nico-test",
        ) as client:
            # The independent timer guarantees cleanup even if a regression blocks the
            # ASGI event loop. Before the threadpool boundary this request cannot yield
            # to the health probe until the timer releases the synchronous resume call.
            safety_release = Timer(1.0, release.set)
            safety_release.daemon = True
            safety_release.start()
            continuation = asyncio.create_task(
                client.post(
                    "/assessment/comprehensive-run/comprun_event_loop_probe/continue",
                    json={"max_stages": 1},
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
                    client.get("/health-concurrency-probe"),
                    timeout=0.5,
                )
                assert health.status_code == 200
                assert health.json() == {"status": "ok"}
                assert monotonic() - probe_started < 0.5
            finally:
                release.set()
                safety_release.cancel()

            response = await asyncio.wait_for(continuation, timeout=1.0)
            assert response.status_code == 422
            assert response.json()["detail"] == "blocking_resume_test_complete"

    asyncio.run(exercise())
