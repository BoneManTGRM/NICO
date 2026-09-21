"""Synthetic transport/recovery fixtures; no assessment or human approval occurs."""
from copy import deepcopy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256
from nico.comprehensive_run_store import _browser_projection_sha256
from tests.test_comprehensive_mobile_recovery_v1 import _record
from tests.test_comprehensive_run_service import _executors, _run_to_review, _store
from tests.test_scanner_summary_legacy_projection import app_for, HEADERS


SECTIONS = [
    {"id": "code_audit", "score": 96, "status": "strong",
     "assurance_status": "evidence_bound", "source_assurance_status": "green",
     "risk_disposition": "review_required"},
    {"id": "dependencies", "score": 96, "status": "strong",
     "assurance_status": "human_review_required", "assurance_label": "Human review required"},
    {"id": "unknown", "score": 96, "status": "strong"},
    {"id": "label_only", "score": 80, "assurance_label": "review_limited"},
]
FIELDS = ("assurance_status", "assurance_label", "source_assurance_status", "risk_disposition")
RUN = "comprun_section_assurance_projection"


def final_stage(sections):
    stage = _record()["stage_results"]["final_comprehensive_report_generation"]
    stage["assessment"]["sections"] = deepcopy(sections)
    report = stage["report_package"]
    report["json"]["assessment"] = deepcopy(stage["assessment"])
    report["canonical_truth_sha256"] = canonical_sha256(report["json"])
    return stage


@pytest.mark.parametrize("browser", [False, True])
def test_terminal_response_preserves_explicit_assurance_without_inventing_missing_state(browser):
    # The whitelist previously dropped explicit assurance and risk from the UI.
    record = _record()
    record["stage_results"]["final_comprehensive_report_generation"] = final_stage(SECTIONS)
    before = deepcopy(record)
    response = ComprehensiveApiController._response(record, operation="status", browser_projection=browser)
    assert response["assessment"]["sections"] == SECTIONS
    assert response["human_review_completed"] is False
    assert response["client_delivery_allowed"] is False
    assert response["assessment"]["human_review_required"] is True
    assert response["assessment"]["client_ready"] is False
    assert record == before
    if browser:
        assert "json" not in response["reports"]
        assert len(json.dumps(response).encode()) < 200_000


def test_new_assurance_fields_remain_bounded_and_do_not_admit_arbitrary_section_payloads():
    section = {"id": "bounded", "assurance_label": "x" * 100_000, "untrusted_raw": "y" * 100_000}
    record = _record()
    record["stage_results"]["final_comprehensive_report_generation"] = final_stage([section])
    response = ComprehensiveApiController._response(record, operation="status", browser_projection=True)
    projected = response["assessment"]["sections"][0]
    assert 0 < len(projected["assurance_label"]) <= 1_201
    assert "untrusted_raw" not in projected


@pytest.mark.parametrize("sections", [SECTIONS, [SECTIONS[2]]], ids=["explicit", "missing"])
def test_saved_projection_refreshes_once_and_survives_restart_without_rewriting_history(tmp_path, monkeypatch, sections):
    # A valid old projection must gain retained semantics even with a current scanner policy.
    database = tmp_path / "assurance.sqlite3"
    store = _store(database)
    executors = _executors()
    original = executors["final_report_generation"]

    def final(context):
        output = original(context)
        stage = final_stage(sections)
        report = stage["report_package"]
        report["json"]["identity"].update({key: context[key] for key in
            ("run_id", "repository", "commit_sha", "evidence_ledger_id")})
        report["canonical_truth_sha256"] = canonical_sha256(report["json"])
        output.update(assessment=stage["assessment"], report_package=report)
        return output

    executors["final_report_generation"] = final
    app, service = app_for(store, executors)
    service.start(run_id=RUN, repository="owner/control", commit_sha="a" * 40,
                  evidence_ledger_id="ledger_assurance", customer_id="test_customer",
                  project_id="test_project", authorized=True)
    _run_to_review(service, RUN)
    before = store.load(RUN)
    projection = store.load_browser_projection(RUN)
    assert projection["response_projection"]["artifact_integrity_valid"] is True
    for section in projection["assessment"]["sections"]:
        for field in FIELDS:
            section.pop(field, None)
    projection["response_projection"].pop("section_assurance_policy", None)
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE nico_comprehensive_browser_projections SET projection=?, projection_sha256=? WHERE run_id=?",
            (json.dumps(projection), _browser_projection_sha256(projection), RUN),
        )
        connection.commit()
    calls = []
    original_load = store.load

    def counted(run_id):
        calls.append(run_id)
        return original_load(run_id)

    monkeypatch.setattr(store, "load", counted)
    result = TestClient(app).get(f"/assessment/comprehensive-run/{RUN}", headers=HEADERS)
    assert result.status_code == 200
    body = result.json()
    assert body["assessment"]["sections"] == sections
    assert calls == [RUN]
    assert original_load(RUN) == before  # Includes revision, hashes, artifacts and review/delivery state.
    assert body["human_review_completed"] is False
    assert body["client_delivery_allowed"] is False
    restarted = _store(database)
    restarted_app, _ = app_for(restarted)

    def forbidden(_):
        raise AssertionError("current projection must survive restart without a full canonical read")

    monkeypatch.setattr(restarted, "load", forbidden)
    again = TestClient(restarted_app).get(f"/assessment/comprehensive-run/{RUN}", headers=HEADERS)
    assert again.status_code == 200
    assert again.json()["assessment"] == body["assessment"]
