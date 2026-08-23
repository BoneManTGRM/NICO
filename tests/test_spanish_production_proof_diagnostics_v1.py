from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "spanish-comprehensive-production-proof.yml"
TELEMETRY = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v2.py"
TERMINAL = ROOT / "scripts" / "spanish_comprehensive_live_acceptance_v3.py"


def test_running_exact_sha_spanish_proof_is_not_cancelled_by_new_pushes() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "group: nico-spanish-comprehensive-production" in source
    assert "cancel-in-progress: false" in source
    assert "cancel-in-progress: true" not in source
    assert "PYTHONUNBUFFERED: \"1\"" in source
    assert "NICO_SPANISH_PROOF_TELEMETRY_SECONDS" in source


def test_workflow_runs_terminal_wrapper_and_uploads_progress_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    terminal = TERMINAL.read_text(encoding="utf-8")

    assert "python scripts/spanish_comprehensive_live_acceptance_v3.py" in source
    assert "spanish-comprehensive-live-proof.progress.json" in source
    assert "if: always()" in source
    # v3 owns exact terminal presentation expectations while delegating the bounded
    # worker/deadline telemetry instrumentation to v2. This preserves one proof run
    # and one diagnostic stream rather than duplicating execution.
    assert "from scripts import spanish_comprehensive_live_acceptance_v2" in terminal or "spanish_comprehensive_live_acceptance_v2" in terminal


def test_telemetry_projects_bounded_worker_and_deadline_diagnostics() -> None:
    source = TELEMETRY.read_text(encoding="utf-8")

    for field in (
        "worker_exit_code",
        "worker_exit_signal",
        "worker_error_type",
        "worker_error",
        "worker_failure_class",
        "worker_bootstrap",
        "heartbeat_age_seconds",
        "elapsed_seconds",
        "deadline_seconds",
        "deadline_phase",
        "overdue",
    ):
        assert field in source

    assert "SPANISH_PROOF_PROGRESS" in source
    assert "ensure_ascii=False" in source
    assert "worker_traceback" not in source
    assert '"client_delivery_allowed": False' in source


def test_wrapper_restores_shared_wait_function_after_every_outcome() -> None:
    source = TELEMETRY.read_text(encoding="utf-8")

    assert "original_wait = recovery._wait_for_terminal" in source
    assert "recovery._wait_for_terminal = _wait_for_terminal_with_telemetry" in source
    assert "finally:" in source
    assert "recovery._wait_for_terminal = original_wait" in source
