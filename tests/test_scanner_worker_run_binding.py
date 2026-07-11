from __future__ import annotations

from nico import scanner_worker


class _NoopThread:
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs

    def start(self) -> None:
        return None


def test_start_scan_binds_full_run_id(monkeypatch) -> None:
    monkeypatch.setattr(scanner_worker.threading, "Thread", _NoopThread)

    job = scanner_worker.start_scan(
        {
            "repository": "BoneManTGRM/NICO",
            "authorized": True,
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "run_id": "fullrun_abc",
            "authorized_by": "tester",
            "authorization_scope": "repository assessment only",
            "tools": ["bandit"],
        }
    )

    assert job["status"] == "queued"
    assert job["run_id"] == "fullrun_abc"
    assert job["customer_id"] == "cust-a"
    assert job["project_id"] == "proj-a"
    assert scanner_worker.get_scan(job["scan_id"])["run_id"] == "fullrun_abc"
