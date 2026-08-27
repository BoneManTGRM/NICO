from __future__ import annotations

import threading

import pytest

from nico import comprehensive_final_report_process_isolation_v1 as isolation
from nico import comprehensive_final_report_process_worker_v1 as worker


class _NeverEndingProcess:
    pid = 424242

    def __init__(self) -> None:
        self.return_code = None

    def poll(self):
        return self.return_code

    def terminate(self) -> None:
        self.return_code = 0

    def kill(self) -> None:
        self.return_code = -9

    def wait(self, timeout=None):
        if self.return_code is None:
            self.return_code = 0
        return self.return_code


def _context() -> dict:
    return {
        "run_id": "comprun_local_deadline",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger-local-deadline",
        "customer_id": "customer",
        "project_id": "project",
        "authorized": True,
    }


def test_process_local_deadline_state_is_monotonic_and_boundary_exact() -> None:
    before = worker._render_deadline_state(
        started_monotonic=100.0,
        max_render_seconds=5.0,
        now_monotonic=104.999,
    )
    at_deadline = worker._render_deadline_state(
        started_monotonic=100.0,
        max_render_seconds=5.0,
        now_monotonic=105.0,
    )

    assert before["active"] is True
    assert before["overdue"] is False
    assert at_deadline["overdue"] is True
    assert at_deadline["deadline_clock"] == "process_local_monotonic"
    assert at_deadline["deadline_phase"] == "rendering"


def test_isolated_worker_enforces_local_deadline_without_durable_store(monkeypatch) -> None:
    fake = _NeverEndingProcess()
    monkeypatch.setattr(worker.subprocess, "Popen", lambda *args, **kwargs: fake)
    monkeypatch.setattr(worker, "_isolated_process_group", lambda process: 0)

    def signal(process, *, force: bool) -> None:
        process.kill() if force else process.terminate()

    monkeypatch.setattr(worker, "_signal_worker", signal)

    state: dict = {}
    with pytest.raises(
        worker.IsolatedFinalReportCancelled,
        match="render_deadline_exceeded",
    ):
        worker.run_isolated_final_report(
            _context(),
            stop=threading.Event(),
            state=state,
            max_render_seconds=0.02,
        )

    assert state["local_render_deadline_expired"] is True
    assert state["deadline_expired"] is True
    assert state["worker_terminated"] is True
    assert state["local_render_deadline_clock"] == "process_local_monotonic"
    assert state["local_render_elapsed_seconds"] >= 0.02


def test_local_deadline_result_remains_fail_closed_and_recoverable() -> None:
    result = isolation._local_deadline_blocked_result(
        _context(),
        lease_id="frpub_local_deadline",
        state={
            "local_render_deadline_seconds": 900.0,
            "local_render_elapsed_seconds": 900.1,
            "worker_terminated": True,
            "physical_worker_exit_confirmed": True,
        },
        render_started_epoch=1_700_000_000.0,
    )

    assert result["status"] == "blocked"
    assert result["reason"] == "final_report_publication_deadline_exceeded"
    assert result["retryable"] is True
    assert result["recovery_scope"] == "final_report_only"
    assert result["local_render_deadline_expired"] is True
    assert result["deadline_source"] == "process_local_monotonic_clock"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False

    execution = result["stage_execution"]
    assert execution["deadline_enforced_by"] == "isolated_process_local_monotonic_clock"
    assert execution["deadline_independent_of_durable_lease_reads"] is True
    assert execution["worker_termination_confirmed"] is True
    assert execution["physical_worker_exit_confirmed"] is True
