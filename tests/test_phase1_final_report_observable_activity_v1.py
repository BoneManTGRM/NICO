from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace

from nico.comprehensive_final_report_activity_v1 import (
    ObservableComprehensiveApiController,
    describe_final_report_activity,
)
from nico.comprehensive_final_report_execution_boundary_v4 import FINAL_REPORT_STAGE_ID
from scripts.final_report_activity_acceptance_v1 import install


RUN_ID = "comprun_phase1_activity"
LEASE_ID = "frpub_phase1_activity"


def _record() -> dict:
    return {
        "artifact_schema": "nico.comprehensive_run_record.v1",
        "identity": {
            "run_id": RUN_ID,
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_phase1_activity",
            "customer_id": "customer_phase1_activity",
            "project_id": "project_phase1_activity",
            "assessment_depth": "strategic",
            "report_language": "en",
        },
        "human_evidence": {},
        "status": "running",
        "current_stage": FINAL_REPORT_STAGE_ID,
        "completed_stages": ["risk_reduction_and_executive_briefing"],
        "stage_results": {
            FINAL_REPORT_STAGE_ID: {
                "status": "running",
                "reason": "final_report_background_publication_in_progress",
                "human_review_required": True,
                "client_delivery_allowed": False,
                "stage_execution": {
                    "lease_id": LEASE_ID,
                    "orphan_after_seconds": 30.0,
                    "provider_lifetime_owner": "durable_final_report_coordinator",
                    "nested_timeout_thread": False,
                },
            }
        },
        "blockers": [],
        "progress_percent": 82.61,
        "revision": 57,
        "terminal": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "integrity_sha256": "b" * 64,
    }


class _Store:
    def __init__(self, heartbeat_epoch: float) -> None:
        self.heartbeat_epoch = heartbeat_epoch

    def load_final_report_job(self, lease_id: str) -> dict:
        assert lease_id == LEASE_ID
        return {
            "lease_id": lease_id,
            "run_id": RUN_ID,
            "status": "running",
            "started_epoch": self.heartbeat_epoch - 20.0,
            "heartbeat_epoch": self.heartbeat_epoch,
            "updated_at": "2026-08-09T00:00:00+00:00",
        }


class _Service:
    def __init__(self, record: dict, heartbeat_epoch: float) -> None:
        self._record = record
        self._store = _Store(heartbeat_epoch)

    def load(self, run_id: str) -> dict:
        assert run_id == RUN_ID
        return self._record

    def resume(self, run_id: str, *, max_stages=None) -> dict:
        assert run_id == RUN_ID
        assert max_stages in (None, 1)
        return self._record


def test_fresh_durable_heartbeat_is_observable_without_revision_mutation() -> None:
    record = _record()
    service = _Service(record, heartbeat_epoch=105.0)

    activity = describe_final_report_activity(service, record, now_epoch=110.0)

    assert activity["stage_id"] == FINAL_REPORT_STAGE_ID
    assert activity["durable_job_status"] == "running"
    assert activity["heartbeat_fresh"] is True
    assert activity["heartbeat_age_seconds"] == 5.0
    assert activity["activity_token"]
    assert activity["canonical_run_revision"] == 57
    assert activity["canonical_run_revision_mutated"] is False
    assert activity["provider_lifetime_owner"] == "durable_final_report_coordinator"
    assert activity["nested_timeout_thread"] is False
    assert activity["human_review_required"] is True
    assert activity["client_delivery_allowed"] is False
    assert record["revision"] == 57
    assert record["progress_percent"] == 82.61


def test_stale_durable_heartbeat_is_not_presented_as_fresh_progress() -> None:
    record = _record()
    service = _Service(record, heartbeat_epoch=105.0)

    activity = describe_final_report_activity(service, record, now_epoch=200.0)

    assert activity["heartbeat_fresh"] is False
    assert activity["heartbeat_age_seconds"] == 95.0
    assert activity["canonical_run_revision_mutated"] is False
    assert activity["client_delivery_allowed"] is False


def test_observable_controller_attaches_bounded_activity_only_to_response() -> None:
    record = _record()
    service = _Service(record, heartbeat_epoch=time.time())
    controller = ObservableComprehensiveApiController(service)

    response = controller.status(RUN_ID)

    assert response["run_id"] == RUN_ID
    assert response["revision"] == 57
    assert response["canonical_progress_percent"] == 82.61
    assert response["terminal"] is False
    assert response["human_review_required"] is True
    assert response["client_delivery_allowed"] is False
    assert "reports" not in response
    activity = response["active_stage_execution"]
    assert activity["heartbeat_fresh"] is True
    assert activity["lease_fingerprint"]
    assert LEASE_ID not in str(activity)
    assert activity["canonical_run_revision_mutated"] is False
    assert response["response_projection"]["active_stage_execution_attached"] is True
    assert (
        response["response_projection"]["canonical_run_revision_mutated_for_activity"]
        is False
    )
    assert record["revision"] == 57


def test_acceptance_signature_advances_only_for_fresh_durable_activity() -> None:
    def original_summary(payload, *, http_status=None):
        return {
            "status": payload.get("status", "running"),
            "current_stage": payload.get("current_stage", FINAL_REPORT_STAGE_ID),
            "http_status": http_status,
        }

    def original_signature(payload):
        return (payload.get("status", "running"), payload.get("revision", 57))

    runtime = SimpleNamespace(
        _status_summary=original_summary,
        _activity_signature=original_signature,
    )
    installed = install(runtime)
    assert installed["fresh_heartbeat_counts_as_observable_activity"] is True
    assert installed["canonical_progress_fabricated"] is False
    assert installed["canonical_revision_mutated"] is False
    assert installed["stale_heartbeat_still_fails"] is True

    def payload(token: str, *, fresh: bool) -> dict:
        return {
            "status": "running",
            "revision": 57,
            "current_stage": FINAL_REPORT_STAGE_ID,
            "active_stage_execution": {
                "artifact_schema": "nico.comprehensive_final_report_activity.v1",
                "stage_id": FINAL_REPORT_STAGE_ID,
                "status": "active",
                "phase": "durable_publication",
                "lease_fingerprint": "abc123",
                "durable_job_status": "running",
                "heartbeat_epoch": 100.0,
                "heartbeat_age_seconds": 2.0,
                "heartbeat_fresh": fresh,
                "activity_token": token,
                "local_worker_active": True,
                "orphan_after_seconds": 30.0,
                "canonical_run_revision_mutated": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        }

    first = runtime._activity_signature(payload("heartbeat-one", fresh=True))
    second = runtime._activity_signature(payload("heartbeat-two", fresh=True))
    stale_one = runtime._activity_signature(payload("stale-one", fresh=False))
    stale_two = runtime._activity_signature(payload("stale-two", fresh=False))

    assert first != second
    assert "heartbeat-one" in first
    assert "heartbeat-two" in second
    assert stale_one == stale_two
    summary = runtime._status_summary(payload("heartbeat-two", fresh=True), http_status=200)
    bounded = summary["active_stage_execution"]
    assert bounded["heartbeat_fresh"] is True
    assert bounded["activity_token"] == "heartbeat-two"
    assert "lease_id" not in bounded
    assert bounded["client_delivery_allowed"] is False


def test_production_runtime_and_acceptance_loader_install_one_activity_path() -> None:
    runtime_source = Path("nico/comprehensive_runtime.py").read_text(encoding="utf-8")
    loader_source = Path("scripts/two_service_live_acceptance_v2.py").read_text(
        encoding="utf-8"
    )

    assert "ObservableComprehensiveApiController" in runtime_source
    assert "final_report_activity_projection" in runtime_source
    assert "FINAL_REPORT_ACTIVITY = install_final_report_activity(_legacy)" in loader_source
    assert "nico.two_service_live_acceptance_v2.loader.v3" in loader_source
