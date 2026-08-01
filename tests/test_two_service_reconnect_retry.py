from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import two_service_live_acceptance_v2_retry_wrapper as reconnect


RUN_ID = "comprun_reconnect_retry_001"
INTEGRITY = "sha256:" + "a" * 64


class _Page:
    url = "https://app.nicoaudit.com/assessment"

    def __init__(self) -> None:
        self.waits: list[int] = []

    def wait_for_timeout(self, milliseconds: int) -> None:
        self.waits.append(milliseconds)


class _Response:
    status = 200


def _payload(*, run_id: str = RUN_ID, revision: int = 41, integrity: str = INTEGRITY) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "status": "review_required",
        "terminal": True,
        "record": {
            "run_id": run_id,
            "status": "review_required",
            "revision": revision,
            "integrity_sha256": integrity,
            "terminal": True,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_reconnect_recovers_from_transient_transport_timeouts(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page()
    attempts = 0

    def status_request(_page: Any, _service: str, _payload: dict[str, Any]):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError("temporary status read timeout")
        return _Response(), f"/api/nico/assessment/comprehensive-run/{RUN_ID}"

    monkeypatch.setattr(reconnect, "_status_request", status_request)
    monkeypatch.setattr(reconnect.acceptance, "response_json", lambda _response: _payload())

    result = reconnect.status_reconnect(page, "comprehensive", _payload())

    assert result["identity_preserved"] is True
    assert result["run_id"] == RUN_ID
    assert result["attempts"] == 3
    assert result["transient_error_count"] == 2
    assert page.waits == [reconnect.RECONNECT_RETRY_MS, reconnect.RECONNECT_RETRY_MS]
    assert all(item["code"] == "TimeoutError" for item in result["transient_errors"])


def test_reconnect_fails_after_bounded_transport_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page()
    attempts = 0

    def status_request(_page: Any, _service: str, _payload: dict[str, Any]):
        nonlocal attempts
        attempts += 1
        raise TimeoutError("persistent status read timeout")

    monkeypatch.setattr(reconnect, "_status_request", status_request)

    with pytest.raises(AssertionError, match=f"{RECONNECT_MAX_ATTEMPTS_PATTERN()} transport attempts"):
        reconnect.status_reconnect(page, "comprehensive", _payload())

    assert attempts == reconnect.RECONNECT_MAX_ATTEMPTS
    assert page.waits == [reconnect.RECONNECT_RETRY_MS] * (reconnect.RECONNECT_MAX_ATTEMPTS - 1)


def RECONNECT_MAX_ATTEMPTS_PATTERN() -> str:
    return str(reconnect.RECONNECT_MAX_ATTEMPTS)


def test_reconnect_identity_drift_fails_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page()
    calls = 0

    def status_request(_page: Any, _service: str, _payload: dict[str, Any]):
        nonlocal calls
        calls += 1
        return _Response(), f"/api/nico/assessment/comprehensive-run/{RUN_ID}"

    monkeypatch.setattr(reconnect, "_status_request", status_request)
    monkeypatch.setattr(
        reconnect.acceptance,
        "response_json",
        lambda _response: _payload(run_id="comprun_wrong_identity"),
    )

    with pytest.raises(AssertionError, match="changed run identity"):
        reconnect.status_reconnect(page, "comprehensive", _payload())

    assert calls == 1
    assert page.waits == []


def test_reconnect_integrity_drift_fails_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page()
    calls = 0

    def status_request(_page: Any, _service: str, _payload: dict[str, Any]):
        nonlocal calls
        calls += 1
        return _Response(), f"/api/nico/assessment/comprehensive-run/{RUN_ID}"

    monkeypatch.setattr(reconnect, "_status_request", status_request)
    monkeypatch.setattr(
        reconnect.acceptance,
        "response_json",
        lambda _response: _payload(integrity="sha256:" + "b" * 64),
    )

    with pytest.raises(AssertionError, match="changed exact-run integrity"):
        reconnect.status_reconnect(page, "comprehensive", _payload())

    assert calls == 1
    assert page.waits == []


def test_reconnect_revision_regression_fails_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    page = _Page()
    monkeypatch.setattr(
        reconnect,
        "_status_request",
        lambda _page, _service, _payload: (
            _Response(),
            f"/api/nico/assessment/comprehensive-run/{RUN_ID}",
        ),
    )
    monkeypatch.setattr(
        reconnect.acceptance,
        "response_json",
        lambda _response: _payload(revision=40),
    )

    with pytest.raises(AssertionError, match="moved revision backward"):
        reconnect.status_reconnect(page, "comprehensive", _payload(revision=41))

    assert page.waits == []
