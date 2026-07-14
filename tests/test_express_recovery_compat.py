from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

import nico.assessment_recovery as recovery
import nico.express_recovery_compat as compat
from nico.storage import MemoryAdapter


@pytest.fixture
def installed(monkeypatch):
    original_workflows = set(recovery.SUPPORTED_WORKFLOWS)
    original_active = set(recovery.ACTIVE_ASSESSMENT_STATUSES)
    original_terminal = set(recovery.TERMINAL_ASSESSMENT_STATUSES)
    original_summary = recovery._safe_run_summary
    original_patch = recovery._recovery_patch
    original_valid = recovery._valid_resume_source
    original_inventory = recovery.assessment_recovery_inventory
    result = compat.install_express_recovery_compatibility()
    yield result
    recovery.SUPPORTED_WORKFLOWS.clear()
    recovery.SUPPORTED_WORKFLOWS.update(original_workflows)
    recovery.ACTIVE_ASSESSMENT_STATUSES.clear()
    recovery.ACTIVE_ASSESSMENT_STATUSES.update(original_active)
    recovery.TERMINAL_ASSESSMENT_STATUSES.clear()
    recovery.TERMINAL_ASSESSMENT_STATUSES.update(original_terminal)
    recovery._safe_run_summary = original_summary
    recovery._recovery_patch = original_patch
    recovery._valid_resume_source = original_valid
    recovery.assessment_recovery_inventory = original_inventory


def express_record(run_id: str, status: str = "interrupted") -> dict:
    now = datetime.now(timezone.utc).replace(microsecond=0)
    return {
        "workflow": "express",
        "run_id": run_id,
        "customer_id": "customer_test",
        "project_id": "project_test",
        "repository": "BoneManTGRM/NICO",
        "status": status,
        "request": {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "customer_test",
            "project_id": "project_test",
            "authorized_by": "requester",
            "authorization_scope": "repository assessment only",
            "authorization_confirmed": True,
            "authorized": True,
        },
        "response": {
            "status": status,
            "run_id": run_id,
            "assessment_type": "express",
            "human_review_required": True,
            "client_ready": False,
        },
        "created_at": (now - timedelta(minutes=20)).isoformat().replace("+00:00", "Z"),
        "updated_at": now.isoformat().replace("+00:00", "Z"),
    }


def test_install_adds_express_without_enabling_resume(installed) -> None:
    assert installed["status"] == "installed"
    assert "express" in recovery.SUPPORTED_WORKFLOWS
    assert "queued" in recovery.ACTIVE_ASSESSMENT_STATUSES
    assert installed["automatic_resume"] is False
    assert installed["same_id_resume"] is False


def test_interrupted_express_is_immediately_visible_in_inventory(installed) -> None:
    store = MemoryAdapter()
    record = express_record("express_run_interrupted")
    store.put("assessment_runs", record["run_id"], record)

    inventory = recovery.assessment_recovery_inventory(store=store, refresh=False, limit=20)

    assert inventory["status"] == "attention_required"
    assert inventory["counts"]["express_recovery_required"] == 1
    assert inventory["counts"]["recovery_required"] == 1
    item = inventory["recovery_required"][0]
    assert item["run_id"] == "express_run_interrupted"
    assert item["workflow"] == "express"
    assert item["service_tier"] == "express"
    assert item["recovery"]["resume_allowed"] is False
    assert item["human_review_required"] is True
    assert item["client_delivery_allowed"] is False


def test_stale_running_express_reconciles_to_manual_recovery(installed) -> None:
    store = MemoryAdapter()
    record = express_record("express_run_stale", status="running")
    record["updated_at"] = (
        datetime.now(timezone.utc).replace(microsecond=0) - timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")
    store.put("assessment_runs", record["run_id"], record)

    # Memory mode deliberately blocks automatic durable reconciliation.
    result = recovery.reconcile_interrupted_assessment_runs(store=store, stale_seconds=60)
    assert result["status"] == "blocked"
    assert result["automatic_resume"] is False

    patch = recovery._recovery_patch(record, now_text="2026-07-14T20:00:00Z", age_seconds=3600)
    assert patch["recovery"]["reason"] == "stale_express_worker"
    assert patch["recovery"]["resume_allowed"] is False
    assert patch["recovery"]["automatic_resume"] is False


def test_express_resume_validation_fails_closed(installed) -> None:
    valid, reason = recovery._valid_resume_source(express_record("express_run_no_resume"))

    assert valid is False
    assert reason == "express_manual_review_required"
