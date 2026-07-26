from __future__ import annotations

import base64
import hashlib
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_mobile_recovery_v1 import (
    ARTIFACT_ROUTE_PATHS,
    BROWSER_PROJECTION_HEADER,
    BROWSER_PROJECTION_VALUE,
)


class _Service:
    def __init__(self, record: dict) -> None:
        self.record = record

    def load(self, run_id: str) -> dict:
        assert run_id == self.record["identity"]["run_id"]
        return self.record


def _record(*, terminal: bool = True) -> dict:
    pdf = b"%PDF-1.4\n% NICO terminal report\n%%EOF\n"
    markdown = "# NICO Comprehensive Technical Assessment\n\nFinal report pending human approval.\n"
    html = "<!doctype html><html><body><h1>NICO Comprehensive Technical Assessment</h1></body></html>"
    canonical = {
        "canonical_truth_sha256": "a" * 64,
        "assessment": {"maturity_signal": {"level": "Senior", "presented_score": 91}},
        "large": "z" * (2 * 1024 * 1024),
    }
    report = {
        "service_id": "comprehensive",
        "report_id": "report_mobile_recovery_001",
        "markdown": markdown,
        "html": html,
        "json": canonical,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "pdf_filename": "nico-comprehensive-FINAL-PENDING-APPROVAL.pdf",
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "canonical_truth_sha256": "a" * 64,
    }
    assessment = {
        "executive_summary": "Decision-grade assessment complete pending expert review.",
        "evidence_coverage": {"calculated": True, "percent": 98, "label": "Evidence"},
        "maturity_signal": {"level": "Senior", "score": 91, "presented_score": 91},
        "sections": [
            {
                "id": "architecture",
                "label": "Architecture",
                "score": 91,
                "presented_score": 91,
                "summary": "Architecture evidence was reconciled.",
                "evidence": ["bounded evidence"],
            }
        ],
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
    }
    status = "review_required" if terminal else "running"
    return {
        "artifact_schema": "nico.comprehensive_run_record.v4",
        "service_id": "comprehensive",
        "identity": {
            "run_id": "comprun_mobile_recovery_001",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "b" * 40,
            "evidence_ledger_id": "ledger_mobile_recovery_001",
            "customer_id": "customer_mobile",
            "project_id": "project_mobile",
            "assessment_depth": "strategic",
            "report_language": "en",
        },
        "status": status,
        "current_stage": "human_review_request" if terminal else "cross_format_truth_verification",
        "completed_stages": ["final_comprehensive_report_generation"] if terminal else [],
        "stage_results": {
            "final_comprehensive_report_generation": {
                "status": "complete" if terminal else "running",
                "summary": "Final report generated." if terminal else "Final report is being generated.",
                "report_package": report,
                "assessment": assessment,
            }
        },
        "blockers": [],
        "progress_percent": 100.0 if terminal else 94.0,
        "revision": 77,
        "terminal": terminal,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "integrity_sha256": "c" * 64,
    }


def _app(record: dict) -> FastAPI:
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "durability_verified": True,
        "survives_container_replacement_verified": True,
    }
    routes.register_comprehensive_api_routes(
        app,
        controller=ComprehensiveApiController(_Service(record)),
    )
    return app


def test_browser_terminal_status_returns_small_manifest_not_embedded_artifacts() -> None:
    response = TestClient(_app(_record())).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001",
        headers={BROWSER_PROJECTION_HEADER: BROWSER_PROJECTION_VALUE},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["assessment"]["maturity_signal"]["presented_score"] == 91
    assert body["reports"]["pdf_available"] is True
    assert body["reports"]["markdown_available"] is True
    assert body["reports"]["artifact_delivery"] == "on_demand_exact_run"
    assert "pdf_base64" not in body["reports"]
    assert "markdown" not in body["reports"]
    assert "html" not in body["reports"]
    assert "json" not in body["reports"]
    assert len(response.content) < 200_000


def test_non_browser_status_preserves_full_report_for_existing_consumers() -> None:
    response = TestClient(_app(_record())).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001"
    )

    assert response.status_code == 200
    report = response.json()["reports"]
    assert report["markdown"].startswith("# NICO Comprehensive")
    assert base64.b64decode(report["pdf_base64"]).startswith(b"%PDF")
    assert report["json"] == {"canonical_truth_sha256": "a" * 64}


def test_exact_run_artifact_routes_stream_canonical_content() -> None:
    client = TestClient(_app(_record()))
    markdown = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/markdown"
    )
    pdf = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )
    canonical = client.get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/json"
    )

    assert markdown.status_code == 200
    assert markdown.text.startswith("# NICO Comprehensive Technical Assessment")
    assert markdown.headers["x-nico-run-id"] == "comprun_mobile_recovery_001"
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF")
    assert pdf.headers["x-nico-artifact-sha256"] == hashlib.sha256(pdf.content).hexdigest()
    assert "FINAL-PENDING-APPROVAL.pdf" in pdf.headers["content-disposition"]
    assert canonical.status_code == 200
    assert canonical.json()["canonical_truth_sha256"] == "a" * 64
    assert len(json.dumps(canonical.json())) > 2 * 1024 * 1024


def test_report_artifacts_fail_closed_before_terminal_state() -> None:
    response = TestClient(_app(_record(terminal=False))).get(
        "/assessment/comprehensive-run/comprun_mobile_recovery_001/report/pdf"
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "comprehensive_report_not_ready"
    assert detail["human_review_required"] is True
    assert detail["client_delivery_allowed"] is False


def test_artifact_route_registration_is_idempotent() -> None:
    app = _app(_record())
    controller = ComprehensiveApiController(_Service(_record()))
    routes.register_comprehensive_api_routes(app, controller=controller)

    paths = [str(getattr(route, "path", "")) for route in app.routes]
    for path in ARTIFACT_ROUTE_PATHS:
        assert paths.count(path) == 1
