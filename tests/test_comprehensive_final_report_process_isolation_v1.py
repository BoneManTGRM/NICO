from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

from nico.comprehensive_final_report_process_isolation_v1 import (
    FINAL_REPORT_STAGE_ID,
    _active_final_report_execution,
)
from nico.comprehensive_final_report_process_worker_v1 import terminate_process


class _JobStore:
    def load_final_report_job(self, lease_id: str):
        assert lease_id == "frpub_live"
        now = time.time()
        return {
            "lease_id": lease_id,
            "run_id": "comprun_live",
            "status": "rendering",
            "started_epoch": now - 12.0,
            "heartbeat_epoch": now - 1.25,
            "updated_at": "2026-08-20T00:00:00+00:00",
        }


def test_hard_termination_actually_stops_worker_process() -> None:
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        assert terminate_process(process, grace_seconds=0.2) is True
        assert process.poll() is not None
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_active_final_report_projection_exposes_durable_renderer_liveness() -> None:
    record = {
        "current_stage": FINAL_REPORT_STAGE_ID,
        "stage_results": {
            FINAL_REPORT_STAGE_ID: {
                "status": "running",
                "stage_execution": {"lease_id": "frpub_live"},
            }
        },
    }
    projection = _active_final_report_execution(record, _JobStore())
    assert projection is not None
    assert projection["stage_id"] == FINAL_REPORT_STAGE_ID
    assert projection["state"] == "rendering"
    assert projection["killable_worker"] is True
    assert projection["worker_model"] == "isolated_subprocess"
    assert projection["heartbeat_age_seconds"] is not None
    assert projection["deadline_seconds"] > 0


def test_deadline_path_waits_for_physical_worker_exit_before_recovery() -> None:
    source = Path("nico/comprehensive_final_report_process_isolation_v1.py").read_text(
        encoding="utf-8"
    )
    stop_method = source.split("def _isolated_stop_local_task", 1)[1].split(
        "def _isolated_start_worker", 1
    )[0]
    watchdog = source.split("def watchdog()", 1)[1].split("def invoke()", 1)[0]
    assert "stop.set()" in stop_method
    assert "_terminate_state_process(state)" in stop_method
    assert "_wait_for_invoke_shutdown(state)" in stop_method
    assert stop_method.index("_wait_for_invoke_shutdown(state)") < stop_method.index(
        "background._release_local_task_capacity(state)"
    )
    assert "self._expire_publication" in watchdog
    assert "self._recover_after_deadline" in watchdog


def test_spanish_bootstrap_enforces_process_isolation_last() -> None:
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_spanish_final_report_runtime_cache_v94" in source
    assert "install_comprehensive_final_report_process_isolation_v1" in source
    assert source.index("SPANISH_FINAL_REPORT_RUNTIME_CACHE =") < source.index(
        "FINAL_REPORT_PROCESS_ISOLATION ="
    )
    assert "hard_termination_supported" in source
    assert "recovery_waits_for_worker_termination" in source
    assert "logical_capacity_released_only_after_worker_exit" in source
