from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


class _Response:
    status = 200

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def json(self) -> dict[str, Any]:
        return self._payload


class _Request:
    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload
        self.get_calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> _Response:
        self.get_calls.append({"url": url, **kwargs})
        return _Response(self.payload)


class _Page:
    url = "https://app.nicoaudit.com/assessment"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.request = _Request(payload)


def _terminal_payload() -> dict[str, Any]:
    return {
        "run_id": "comprun_bounded_reconnect_001",
        "revision": 44,
        "integrity_sha256": "sha256:" + "1" * 64,
    }


def _bounded_response() -> dict[str, Any]:
    return {
        "run_id": "comprun_bounded_reconnect_001",
        "revision": 45,
        "integrity_sha256": "sha256:" + "1" * 64,
        "reports": {
            "response_bounded": True,
            "artifact_delivery": "on_demand_exact_run",
            "canonical_truth_sha256": "a" * 64,
            "markdown_available": True,
            "html_available": True,
            "json_available": True,
            "pdf_available": True,
        },
    }


def test_loader_preserves_full_backend_reads_and_bounds_reconnect() -> None:
    runtime = importlib.import_module("two_service_live_acceptance_v2")
    page = _Page(_bounded_response())

    evidence = runtime.status_reconnect(page, "comprehensive", _terminal_payload())

    assert len(page.request.get_calls) == 1
    call = page.request.get_calls[0]
    assert call["headers"] == {
        "x-nico-browser-projection": "terminal-manifest-v1"
    }
    assert call["timeout"] == 30_000
    assert evidence["identity_preserved"] is True
    assert evidence["response_bounded"] is True
    assert evidence["artifact_delivery"] == "on_demand_exact_run"
    assert evidence["canonical_truth_sha256"] == "a" * 64

    # Normal lifecycle polling remains delegated to the original full status read.
    page.request.get_calls.clear()
    runtime._status_request(page, "comprehensive", _terminal_payload())
    assert page.request.get_calls[0].get("headers") in (None, {})


def test_bounded_reconnect_rejects_embedded_report_bodies() -> None:
    runtime = importlib.import_module("two_service_live_acceptance_v2")
    payload = _bounded_response()
    payload["reports"]["json"] = {"assessment": {}}
    page = _Page(payload)

    try:
        runtime.status_reconnect(page, "comprehensive", _terminal_payload())
    except AssertionError as exc:
        assert "unexpectedly included json" in str(exc)
    else:
        raise AssertionError("bounded reconnect accepted an embedded report body")
