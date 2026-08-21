from __future__ import annotations

from pathlib import Path

from nico.comprehensive_final_report_process_isolation_v1 import (
    _process_worker_failure,
)
from nico.comprehensive_final_report_process_worker_v1 import DEFAULT_BOOTSTRAP


def _context() -> dict[str, str]:
    return {
        "run_id": "comprun_spanish_worker_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_spanish_worker_test",
    }


def test_isolated_renderer_uses_dedicated_worker_bootstrap() -> None:
    assert DEFAULT_BOOTSTRAP == "nico.api.final_report_worker_bootstrap:app"
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "from nico.api.terminal_authority_bootstrap import app" in source
    assert "install_comprehensive_spanish_final_report_runtime_cache_v94" in source
    assert "process_isolation_owned_by_parent" in source
    assert "physical_exit_hardening_owned_by_parent" in source
    assert "production_proof_lifecycle_owned_by_parent" in source
    assert "install_comprehensive_final_report_process_isolation_v1" not in source
    assert "install_comprehensive_final_report_process_isolation_hardening_v2" not in source
    assert "install_comprehensive_production_proof_lifecycle_v1" not in source


def test_worker_failure_projects_bounded_process_exit_cause() -> None:
    state = {
        "worker_model": "isolated_subprocess",
        "worker_pid": 31415,
        "worker_exit_code": -9,
        "worker_exit_signal": "SIGKILL",
        "worker_error_type": "WorkerProcessExit",
        "worker_error": "isolated_final_report_worker_output_missing:exit=-9:signal=SIGKILL",
        "worker_bootstrap": DEFAULT_BOOTSTRAP,
    }
    result = _process_worker_failure(
        _context(),
        RuntimeError("opaque parent error must not erase child cause"),
        state,
    )
    assert result["status"] == "blocked"
    assert result["reason"] == "detached_stage_execution_failed"
    assert result["worker_model"] == "isolated_subprocess"
    assert result["worker_exit_code"] == -9
    assert result["worker_exit_signal"] == "SIGKILL"
    assert result["worker_error_type"] == "WorkerProcessExit"
    assert result["worker_failure_class"] == "process_signal"
    assert result["worker_bootstrap"] == DEFAULT_BOOTSTRAP
    assert result["worker_diagnostics_bounded"] is True
    assert result["worker_traceback_exposed"] is False
    assert "SIGKILL" in result["worker_error"]


def test_worker_failure_projects_bounded_child_exception_cause() -> None:
    long_error = "missing Spanish presentation translation: " + ("x" * 3000)
    result = _process_worker_failure(
        _context(),
        ValueError(long_error),
        {
            "worker_model": "isolated_subprocess",
            "worker_pid": 27182,
            "worker_exit_code": 1,
            "worker_error_type": "ValueError",
            "worker_error": long_error,
            "worker_bootstrap": DEFAULT_BOOTSTRAP,
        },
    )
    assert result["worker_exit_code"] == 1
    assert result["worker_error_type"] == "ValueError"
    assert result["worker_failure_class"] == "child_exception"
    assert len(result["worker_error"]) <= 1200
    assert result["worker_traceback_exposed"] is False


def test_existing_spanish_web_bootstrap_keeps_parent_worker_lifecycle() -> None:
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_final_report_process_isolation_v1" in source
    assert "install_comprehensive_final_report_process_isolation_hardening_v2" in source
    assert "install_comprehensive_production_proof_lifecycle_v1" in source
    # The web process still owns orchestration; only the child entry point changed.
    assert "final_report_worker_bootstrap" not in source
