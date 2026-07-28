from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _module():
    path = ROOT / "scripts" / "capture_phase6_ci_truth.py"
    spec = importlib.util.spec_from_file_location("phase6_ci_truth", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(*, status: str, conclusion: str | None, updated_at: str, run_id: int, event: str = "pull_request") -> dict[str, object]:
    return {
        "name": "NICO CI",
        "status": status,
        "conclusion": conclusion,
        "updated_at": updated_at,
        "run_attempt": 1,
        "id": run_id,
        "event": event,
        "head_sha": "abc123",
    }


def test_successful_exact_sha_check_is_authoritative_over_duplicate_failure() -> None:
    module = _module()
    selected = module._latest_by_name(
        [
            _run(status="completed", conclusion="success", updated_at="2026-07-28T07:00:00Z", run_id=1),
            _run(status="completed", conclusion="failure", updated_at="2026-07-28T07:10:00Z", run_id=2, event="push"),
        ]
    )

    assert selected["NICO CI"]["conclusion"] == "success"
    assert selected["NICO CI"]["id"] == 1


def test_successful_exact_sha_check_is_authoritative_over_duplicate_active_run() -> None:
    module = _module()
    selected = module._latest_by_name(
        [
            _run(status="completed", conclusion="success", updated_at="2026-07-28T07:00:00Z", run_id=1),
            _run(status="in_progress", conclusion=None, updated_at="2026-07-28T07:10:00Z", run_id=2, event="push"),
        ]
    )

    assert selected["NICO CI"]["conclusion"] == "success"
    assert selected["NICO CI"]["id"] == 1


def test_newest_failed_run_is_selected_when_no_success_or_active_run_exists() -> None:
    module = _module()
    selected = module._latest_by_name(
        [
            _run(status="completed", conclusion="failure", updated_at="2026-07-28T07:00:00Z", run_id=1),
            _run(status="completed", conclusion="cancelled", updated_at="2026-07-28T07:10:00Z", run_id=2),
        ]
    )

    assert selected["NICO CI"]["id"] == 2
    assert selected["NICO CI"]["conclusion"] == "cancelled"


def test_duplicate_run_summary_keeps_failed_history_visible() -> None:
    module = _module()
    summary = module._duplicate_run_summary(
        [
            _run(status="completed", conclusion="success", updated_at="2026-07-28T07:00:00Z", run_id=1),
            _run(status="completed", conclusion="failure", updated_at="2026-07-28T07:10:00Z", run_id=2),
            _run(status="queued", conclusion=None, updated_at="2026-07-28T07:20:00Z", run_id=3),
        ]
    )

    assert summary["NICO CI"] == {"success": 1, "active": 1, "failed": 1}
