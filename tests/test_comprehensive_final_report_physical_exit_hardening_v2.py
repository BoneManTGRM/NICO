from __future__ import annotations

import os
import stat
import subprocess
import sys
import time
from pathlib import Path

import pytest

from nico import comprehensive_final_report_process_isolation_hardening_v2 as hardening
from nico.comprehensive_final_report_process_worker_v1 import (
    _atomic_json,
    terminate_process,
)


def _pid_running(pid: int) -> bool:
    if os.name != "posix":
        return False
    status = Path(f"/proc/{pid}/stat")
    if not status.exists():
        return False
    try:
        fields = status.read_text(encoding="utf-8").split()
    except OSError:
        return False
    return len(fields) > 2 and fields[2] != "Z"


def test_atomic_json_is_mode_0600(tmp_path: Path) -> None:
    output = tmp_path / "private.json"
    _atomic_json(output, {"secret": "bounded test value"})
    assert stat.S_IMODE(output.stat().st_mode) == 0o600


@pytest.mark.skipif(os.name != "posix", reason="production container uses POSIX process groups")
def test_hard_termination_stops_sigterm_resistant_descendant_group(tmp_path: Path) -> None:
    child_pid_path = tmp_path / "child.pid"
    descendant = (
        "import signal,time; "
        "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
        "time.sleep(60)"
    )
    script = (
        "import pathlib,subprocess,sys,time; "
        f"child=subprocess.Popen([sys.executable,'-c',{descendant!r}]); "
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8'); "
        "time.sleep(60)"
    )
    process = subprocess.Popen(
        [sys.executable, "-c", script, str(child_pid_path)],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    setattr(process, "_nico_isolated_process_group", process.pid)
    try:
        deadline = time.time() + 3.0
        while not child_pid_path.exists() and time.time() < deadline:
            time.sleep(0.02)
        assert child_pid_path.exists()
        child_pid = int(child_pid_path.read_text(encoding="utf-8"))
        assert _pid_running(child_pid)
        assert terminate_process(process, grace_seconds=0.2) is True
        assert process.poll() is not None

        deadline = time.time() + 2.0
        while _pid_running(child_pid) and time.time() < deadline:
            time.sleep(0.02)
        assert not _pid_running(child_pid), "renderer descendant survived process-group termination"
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_renderer_capacity_waits_for_physical_exit_then_releases_once(
    monkeypatch,
) -> None:
    released: list[bool] = []

    def release_once(state: dict) -> None:
        if state.get("slot_acquired") and not state.get("slot_released"):
            state["slot_released"] = True
            released.append(True)

    monkeypatch.setattr(
        hardening,
        "_ORIGINAL_RELEASE_LOCAL_TASK_CAPACITY",
        release_once,
    )
    process = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=os.name == "posix",
    )
    state = {
        "worker_model": "isolated_subprocess",
        "worker_process": process,
        "slot_acquired": True,
        "slot_released": False,
    }
    try:
        hardening._release_local_task_capacity_after_physical_exit(state)
        assert released == []
        assert state["capacity_release_blocked_until_worker_exit"] is True
        assert state["physical_worker_exit_confirmed"] is False
        assert state["capacity_exit_reaper_started"] is True

        assert terminate_process(process, grace_seconds=0.2) is True
        deadline = time.time() + 2.0
        while not released and time.time() < deadline:
            time.sleep(0.02)
        assert released == [True]
        assert state["physical_worker_exit_confirmed"] is True
        assert state["capacity_release_blocked_until_worker_exit"] is False
        assert state["capacity_exit_reaper_completed"] is True

        hardening._release_local_task_capacity_after_physical_exit(state)
        assert released == [True]
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_production_bootstrap_installs_physical_exit_hardening_last() -> None:
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "install_comprehensive_final_report_process_isolation_v1" in source
    assert "install_comprehensive_final_report_process_isolation_hardening_v2" in source
    assert source.index("FINAL_REPORT_PROCESS_ISOLATION =") < source.index(
        "FINAL_REPORT_PROCESS_ISOLATION_HARDENING ="
    )
    assert "physical_worker_exit_required_before_capacity_release" in source
    assert "failed_termination_keeps_renderer_capacity_reserved" in source
