from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v2.py"


def _module():
    spec = importlib.util.spec_from_file_location("two_service_live_acceptance_v2", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_acceptance_wrapper_installs_runtime_observer_and_keeps_absolute_reconnect() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "acceptance.status_reconnect = status_reconnect" in source
    assert "acceptance.run_service = run_service" in source
    assert 'return f"{parsed.scheme}://{parsed.netloc}{path}"' in source
    assert "APIRequestContext: Invalid URL" in source
    assert "COMPREHENSIVE_HARD_EXTENSION_SECONDS" in source
    assert "COMPREHENSIVE_STALE_SECONDS" in source
    assert "backend_status_history" in source
    assert "runtime-diagnostic.json" in source


def test_status_summary_is_bounded_and_omits_report_bodies() -> None:
    module = _module()
    payload = {
        "run_id": "comprun_test_001",
        "status": "running",
        "current_stage": "deep_scanner_triage",
        "progress_percent": 47.5,
        "canonical_progress_percent": 45.0,
        "active_stage_progress_percent": 50.0,
        "revision": 9,
        "record": {
            "current_stage": "deep_scanner_triage",
            "revision": 9,
            "completed_stages": ["authorization_and_scope", "immutable_repository_snapshot"],
            "stage_results": {"reports": {"pdf_base64": "secret-large-body"}},
        },
        "reports": {"markdown": "private report", "pdf_base64": "encoded"},
        "persistence": {"recorded": True, "durable": True, "adapter": "sqlite"},
    }

    summary = module._status_summary(payload, http_status=200)

    assert summary["run_id"] == "comprun_test_001"
    assert summary["current_stage"] == "deep_scanner_triage"
    assert summary["completed_stage_count"] == 2
    assert summary["revision"] == 9
    assert summary["persistence"]["durable"] is True
    assert "reports" not in summary
    assert "pdf_base64" not in repr(summary)
    assert "private report" not in repr(summary)


def test_activity_signature_changes_when_exact_run_advances() -> None:
    module = _module()
    before = {
        "run_id": "comprun_test_002",
        "status": "running",
        "current_stage": "functional_qa",
        "progress_percent": 55,
        "revision": 11,
        "record": {"completed_stages": ["a"], "revision": 11},
    }
    after = {
        **before,
        "current_stage": "platform_parity",
        "progress_percent": 60,
        "revision": 12,
        "record": {"completed_stages": ["a", "b"], "revision": 12},
    }

    assert module._activity_signature(before) != module._activity_signature(after)
