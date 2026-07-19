from __future__ import annotations

from datetime import datetime, timedelta, timezone

from nico.express_durable_duplicate_start_guard import find_fresh_durable_run


class Store:
    def __init__(self, records):
        self.records = records

    def list(self, table, customer_id=None, project_id=None):
        assert table == "assessment_runs"
        return [
            record
            for record in self.records
            if (customer_id is None or record.get("customer_id") == customer_id)
            and (project_id is None or record.get("project_id") == project_id)
        ]


def _time(seconds_ago: int) -> str:
    value = datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def test_fresh_same_scope_run_prevents_cross_worker_duplicate() -> None:
    record = {
        "workflow": "express",
        "run_id": "express_run_existing",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer",
        "project_id": "project",
        "status": "running",
        "response": {
            "run_id": "express_run_existing",
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer",
            "project_id": "project",
            "status": "running",
            "current_stage": "truth_and_review_gates",
            "updated_at": _time(30),
        },
    }

    result = find_fresh_durable_run(Store([record]), ("BoneManTGRM/NICO", "customer", "project"))

    assert result is not None
    assert result["run_id"] == "express_run_existing"
    assert result["duplicate_start_prevented"] is True
    assert result["duplicate_start_guard"]["cross_worker"] is True


def test_stale_active_record_does_not_permanently_block_new_run() -> None:
    record = {
        "workflow": "express",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer",
        "project_id": "project",
        "status": "running",
        "response": {"status": "running", "updated_at": _time(3600)},
    }

    assert find_fresh_durable_run(Store([record]), ("BoneManTGRM/NICO", "customer", "project")) is None


def test_other_tenant_or_repository_is_never_returned() -> None:
    records = [
        {
            "workflow": "express",
            "repository": "Other/Repo",
            "customer_id": "customer",
            "project_id": "project",
            "status": "running",
            "response": {"status": "running", "updated_at": _time(10)},
        },
        {
            "workflow": "express",
            "repository": "BoneManTGRM/NICO",
            "customer_id": "other",
            "project_id": "project",
            "status": "running",
            "response": {"status": "running", "updated_at": _time(10)},
        },
    ]

    assert find_fresh_durable_run(Store(records), ("BoneManTGRM/NICO", "customer", "project")) is None


def test_terminal_record_never_blocks_new_run() -> None:
    record = {
        "workflow": "express",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer",
        "project_id": "project",
        "status": "complete",
        "response": {"status": "complete", "updated_at": _time(5)},
    }

    assert find_fresh_durable_run(Store([record]), ("BoneManTGRM/NICO", "customer", "project")) is None
