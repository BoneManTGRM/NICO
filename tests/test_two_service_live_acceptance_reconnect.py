from __future__ import annotations

import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"


class _Response:
    def __init__(self, payload: dict, status: int = 200) -> None:
        self._payload = payload
        self.status = status

    def json(self) -> dict:
        return self._payload


class _Request:
    def __init__(self, payload: dict) -> None:
        self.payload = payload
        self.calls: list[tuple[str, str, dict | None]] = []

    def post(self, url: str, data: dict | None = None) -> _Response:
        self.calls.append(("POST", url, data))
        return _Response(self.payload)

    def get(self, url: str) -> _Response:
        self.calls.append(("GET", url, None))
        return _Response(self.payload)


class _Page:
    def __init__(self, payload: dict) -> None:
        self.url = "https://app.nicoaudit.com/assessment?tier=express#assessment"
        self.request = _Request(payload)


def _module():
    sys.path.insert(0, str(SCRIPTS))
    try:
        return importlib.import_module("two_service_live_acceptance_v2")
    finally:
        sys.path.remove(str(SCRIPTS))


def _payload(run_id: str) -> dict:
    return {
        "run_id": run_id,
        "customer_id": "customer_acceptance",
        "project_id": "project_acceptance",
        "revision": 7,
        "integrity_sha256": "a" * 64,
    }


def test_express_reconnect_uses_absolute_same_origin_url() -> None:
    module = _module()
    payload = _payload("express_run_acceptance")
    page = _Page(payload)

    result = module.status_reconnect(page, "express", payload)

    assert page.request.calls == [
        (
            "POST",
            "https://app.nicoaudit.com/api/nico/assessment/express-run/express_run_acceptance/status",
            {"customer_id": "customer_acceptance", "project_id": "project_acceptance"},
        )
    ]
    assert result["identity_preserved"] is True
    assert result["request_url"].startswith("https://app.nicoaudit.com/")


def test_comprehensive_reconnect_uses_absolute_same_origin_url() -> None:
    module = _module()
    payload = _payload("comprun_acceptance")
    page = _Page(payload)

    result = module.status_reconnect(page, "comprehensive", payload)

    assert page.request.calls == [
        (
            "GET",
            "https://app.nicoaudit.com/api/nico/assessment/comprehensive-run/comprun_acceptance",
            None,
        )
    ]
    assert result["identity_preserved"] is True


def test_reconnect_rejects_non_https_or_missing_browser_origin() -> None:
    module = _module()
    payload = _payload("express_run_invalid_origin")
    page = _Page(payload)
    page.url = "about:blank"

    try:
        module.status_reconnect(page, "express", payload)
    except AssertionError as exc:
        assert "HTTPS origin" in str(exc)
    else:
        raise AssertionError("non-HTTPS reconnect origin was accepted")


def test_workflow_runs_v2_wrapper_and_compiles_both_contracts() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "python -m py_compile scripts/two_service_live_acceptance.py scripts/two_service_live_acceptance_v2.py" in source
    assert "python scripts/two_service_live_acceptance_v2.py" in source
    assert "python scripts/two_service_live_acceptance.py" not in source.split(
        "Run two consecutive Express and Comprehensive production passes", 1
    )[1]
