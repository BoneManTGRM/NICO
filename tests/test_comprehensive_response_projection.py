from __future__ import annotations

import json

from nico.comprehensive_api_controller import ComprehensiveApiController, VERSION


def _record(*, terminal: bool) -> dict:
    large = "x" * (2 * 1024 * 1024)
    status = "review_required" if terminal else "running"
    completed = [
        "authorization_and_scope",
        "immutable_repository_snapshot",
        "repository_and_delivery_evidence",
    ]
    stage_results = {
        "authorization_and_scope": {
            "status": "complete",
            "summary": "Authorization verified.",
            "evidence": {"authorized": True},
        },
        "final_comprehensive_report_generation": {
            "status": "complete",
            "summary": "Decision-grade report generated.",
            "assessment": {
                "maturity_signal": {"level": "Senior", "score": 86, "presented_score": 86},
                "sections": [
                    {
                        "id": "architecture",
                        "label": "Architecture",
                        "score": 88,
                        "presented_score": 88,
                        "status": "green",
                        "presented_status": "Strong",
                        "evidence": [large],
                    }
                ],
                "human_review_required": True,
                "client_ready": False,
            },
            "report_package": {
                "service_id": "comprehensive",
                "report_id": "report_projection_001",
                "markdown": "# NICO Comprehensive Technical Assessment\nArchitecture 88/100",
                "html": "<!doctype html><html><body>Architecture 88/100</body></html>",
                "pdf_base64": large,
                "pdf_filename": "nico-comprehensive.pdf",
                "canonical_truth_sha256": "a" * 64,
                "json": {"canonical_truth_sha256": "a" * 64, "raw": large},
            },
            "scanner_outputs": {"raw": large},
            "raw_evidence": {"raw": large},
        },
    }
    return {
        "artifact_schema": "nico.comprehensive_run_record.v1",
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_projection_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_projection_001",
            "customer_id": "customer_projection",
            "project_id": "project_projection",
        },
        "status": status,
        "current_stage": "human_review_request" if terminal else "cross_format_truth_verification",
        "completed_stages": completed,
        "stage_results": stage_results,
        "blockers": [],
        "progress_percent": 100.0 if terminal else 78.26,
        "revision": 76,
        "terminal": terminal,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "integrity_sha256": "c" * 64,
    }


def test_active_response_omits_generated_report_and_large_stage_payloads() -> None:
    response = ComprehensiveApiController._response(_record(terminal=False), operation="continued")

    assert response["artifact_schema"] == VERSION
    assert response["terminal"] is False
    assert "reports" not in response
    assert "assessment" not in response
    stage = response["record"]["stage_results"]["final_comprehensive_report_generation"]
    assert "report_package" not in stage
    assert "assessment" not in stage
    assert "scanner_outputs" not in stage
    assert "raw_evidence" not in stage
    assert stage["response_bounded"] is True
    assert response["response_projection"]["large_stage_payloads_omitted"] is True
    assert len(json.dumps(response).encode("utf-8")) < 200_000


def test_terminal_response_attaches_one_report_package_outside_projected_record() -> None:
    response = ComprehensiveApiController._response(_record(terminal=True), operation="status")

    assert response["terminal"] is True
    assert response["status"] == "review_required"
    assert response["reports"]["service_id"] == "comprehensive"
    assert response["reports"]["pdf_base64"] == "x" * (2 * 1024 * 1024)
    assert response["reports"]["json"] == {"canonical_truth_sha256": "a" * 64}
    assert response["assessment"]["maturity_signal"]["presented_score"] == 86
    assert response["assessment"]["sections"][0]["label"] == "Architecture"
    assert len(response["assessment"]["sections"][0]["evidence"][0]) <= 4_001
    stage = response["record"]["stage_results"]["final_comprehensive_report_generation"]
    assert "report_package" not in stage
    assert "assessment" not in stage
    assert response["response_projection"]["terminal_report_attached"] is True


def test_projected_status_is_deterministic_for_same_persisted_record() -> None:
    record = _record(terminal=False)
    started = ComprehensiveApiController._response(record, operation="started")
    status = ComprehensiveApiController._response(record, operation="status")

    assert started["record"] == status["record"]
    assert started["integrity_sha256"] == status["integrity_sha256"]
    assert started["revision"] == status["revision"]
