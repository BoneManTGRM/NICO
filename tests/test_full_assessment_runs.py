from __future__ import annotations

from nico.full_assessment_runs import (
    build_status_payload,
    load_full_assessment_run,
    persist_full_assessment_run,
    persistence_metadata,
)
from nico.storage import MemoryAdapter


def test_persist_full_assessment_run_preserves_resume_identifiers_and_progress() -> None:
    store = MemoryAdapter()
    result = {
        "status": "running",
        "run_id": "fullrun_persist",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "generated_at": "2026-07-11T12:00:00Z",
        "progress": [{"step": "scanner_worker", "status": "queued"}],
        "scanner": {"scan_id": "scan-a", "status": "queued"},
        "reports": {"report_id": "report-a", "pdf_base64": "large-pdf-bytes"},
        "approval": {"approval_id": "approval-a", "report_id": "report-a"},
    }
    request = {
        "repository": "BoneManTGRM/NICO",
        "authorization_confirmed": True,
        "authorized": True,
        "customer_id": "cust-a",
        "project_id": "proj-a",
        "run_scanners": True,
    }

    saved = persist_full_assessment_run(result, request, store=store)
    loaded = load_full_assessment_run("fullrun_persist", store=store)

    assert saved["workflow"] == "full_assessment"
    assert loaded is not None
    assert loaded["repository"] == "BoneManTGRM/NICO"
    assert loaded["scan_id"] == "scan-a"
    assert loaded["report_id"] == "report-a"
    assert loaded["approval_id"] == "approval-a"
    assert loaded["response"]["progress"] == [{"step": "scanner_worker", "status": "queued"}]
    assert loaded["response"]["reports"]["pdf_base64"] == ""
    assert "not duplicated" in loaded["response"]["reports"]["pdf_retention_note"]
    assert loaded["created_at"] == "2026-07-11T12:00:00Z"
    assert loaded["updated_at"]


def test_full_assessment_update_keeps_existing_identifiers_when_response_omits_them() -> None:
    store = MemoryAdapter()
    persist_full_assessment_run(
        {
            "status": "running",
            "run_id": "fullrun_update",
            "repository": "BoneManTGRM/NICO",
            "scanner": {"scan_id": "scan-existing"},
            "reports": {"report_id": "report-existing"},
            "approval": {"approval_id": "approval-existing"},
        },
        {"repository": "BoneManTGRM/NICO", "authorization_confirmed": True},
        store=store,
    )

    updated = persist_full_assessment_run(
        {"status": "complete", "run_id": "fullrun_update", "repository": "BoneManTGRM/NICO"},
        {},
        store=store,
    )

    assert updated["status"] == "complete"
    assert updated["scan_id"] == "scan-existing"
    assert updated["report_id"] == "report-existing"
    assert updated["approval_id"] == "approval-existing"


def test_status_polling_cannot_erase_requested_report_and_review_intent() -> None:
    store = MemoryAdapter()
    persist_full_assessment_run(
        {
            "status": "running",
            "run_id": "fullrun_intent",
            "repository": "BoneManTGRM/NICO",
            "scanner": {"scan_id": "scan-intent", "status": "running"},
        },
        {
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized": True,
            "build_reports": True,
            "create_final_review_request": True,
            "auto_continue": True,
        },
        store=store,
    )

    refreshed = persist_full_assessment_run(
        {
            "status": "running",
            "run_id": "fullrun_intent",
            "repository": "BoneManTGRM/NICO",
            "scanner": {"scan_id": "scan-intent", "status": "running"},
        },
        {
            "repository": "BoneManTGRM/NICO",
            "scan_id": "scan-intent",
            "build_reports": False,
            "create_final_review_request": False,
            "auto_continue": True,
        },
        store=store,
    )

    assert refreshed["request"]["build_reports"] is True
    assert refreshed["request"]["create_final_review_request"] is True


def test_explicit_recovery_can_upgrade_legacy_false_completion_intent() -> None:
    store = MemoryAdapter()
    persist_full_assessment_run(
        {"status": "complete", "run_id": "fullrun_repair", "repository": "BoneManTGRM/NICO"},
        {
            "repository": "BoneManTGRM/NICO",
            "build_reports": False,
            "create_final_review_request": False,
        },
        store=store,
        preserve_existing_completion_intent=False,
    )

    repaired = persist_full_assessment_run(
        {"status": "complete", "run_id": "fullrun_repair", "repository": "BoneManTGRM/NICO"},
        {
            "repository": "BoneManTGRM/NICO",
            "build_reports": True,
            "create_final_review_request": True,
        },
        store=store,
    )

    assert repaired["request"]["build_reports"] is True
    assert repaired["request"]["create_final_review_request"] is True


def test_status_payload_restores_saved_scope_and_scan_without_default_overwrite() -> None:
    store = MemoryAdapter()
    persist_full_assessment_run(
        {
            "status": "running",
            "run_id": "fullrun_resume",
            "repository": "BoneManTGRM/NICO",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "scanner": {"scan_id": "scan-resume"},
        },
        {
            "repository": "BoneManTGRM/NICO",
            "customer_id": "cust-a",
            "project_id": "proj-a",
            "authorization_confirmed": True,
            "authorized": True,
            "build_reports": True,
            "create_final_review_request": True,
        },
        store=store,
    )

    payload, record = build_status_payload(
        "fullrun_resume",
        {
            "repository": "",
            "customer_id": "default_customer",
            "project_id": "default_project",
            "build_reports": False,
            "create_final_review_request": False,
        },
        explicit_fields=set(),
        store=store,
    )

    assert record is not None
    assert payload["repository"] == "BoneManTGRM/NICO"
    assert payload["customer_id"] == "cust-a"
    assert payload["project_id"] == "proj-a"
    assert payload["scan_id"] == "scan-resume"
    assert payload["run_scanners"] is True
    assert payload["build_reports"] is False
    assert payload["create_final_review_request"] is False


def test_memory_persistence_metadata_is_honest_about_durability() -> None:
    metadata = persistence_metadata(MemoryAdapter(), restored=True)

    assert metadata["recorded"] is True
    assert metadata["durable"] is False
    assert metadata["adapter"] == "memory"
    assert metadata["restored"] is True
