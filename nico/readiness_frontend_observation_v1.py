"""Bound readiness's wait for the existing trusted frontend capture adapters."""
from __future__ import annotations

from queue import Empty, Queue
from threading import BoundedSemaphore, Thread
import time
from typing import Any

from nico import report_execution_provenance_e6 as provenance

# Leave headroom below the frontend proxy's 20-second deadline. Socket timeouts
# cannot bound DNS or trickling response headers, so bound the caller's wait too.
_WAIT_SECONDS = 8.0
_CAPTURE_SLOT = BoundedSemaphore(1)


def capture_readiness_frontend_release(expected_sha: str, expected_deployment_id: str) -> dict[str, Any]:
    unavailable = {
        "status": "unavailable",
        "frontend_observation_schema": "nico.frontend-runtime-observation.v2",
        "source_url": provenance.FRONTEND_URL,
        "deployment_identity_verified": False,
        "native_provider_record_verified_by_this_code": False,
    }
    if not _CAPTURE_SLOT.acquire(blocking=False):
        return {**unavailable, "reason": "frontend_readiness_capture_busy"}
    deadline = time.monotonic() + _WAIT_SECONDS
    completed: Queue[dict[str, Any]] = Queue(maxsize=1)

    def capture() -> None:
        try:
            try:
                result = provenance.capture_frontend_release(expected_sha, expected_deployment_id)
                if not provenance.verify_frontend_release(result, expected_sha, expected_deployment_id):
                    result = {**result, "deployment_identity_verified": False}
            except Exception:
                # Adapter failures cannot establish identity or disclose exception data.
                result = {**unavailable, "reason": "frontend_readiness_capture_failed"}
            completed.put_nowait(result)
        finally:
            _CAPTURE_SLOT.release()

    try:
        # A late worker owns only its private result queue. It cannot update
        # readiness, cache proof, or block shutdown; at most one runs per process.
        Thread(target=capture, daemon=True, name="nico-readiness-frontend").start()
    except RuntimeError:
        _CAPTURE_SLOT.release()
        return {**unavailable, "reason": "frontend_readiness_capture_failed"}
    try:
        remaining = deadline - time.monotonic()
        if remaining > 0:
            result = completed.get(timeout=remaining)
            if time.monotonic() < deadline:
                return result
    except Empty:
        pass
    return {**unavailable, "reason": "frontend_readiness_capture_timed_out"}
