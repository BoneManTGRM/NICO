from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_api_routes import register_comprehensive_api_routes
from nico.comprehensive_client_delivery_contract_v1 import canonical_sha256


class _PublicationRaceService:
    """Expose a stale resume result followed by the newly published terminal record."""

    def __init__(self) -> None:
        identity = {
            "run_id": "comprun_projection_race",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_projection_race",
            "customer_id": "customer_projection_race",
            "project_id": "project_projection_race",
            "assessment_depth": "strategic",
            "report_language": "en",
        }
        self.running = {
            "artifact_schema": "nico.comprehensive_run_record.v1",
            "identity": identity,
            "status": "running",
            "current_stage": "final_comprehensive_report_generation",
            "completed_stages": [],
            "stage_results": {},
            "blockers": [],
            "progress_percent": 95.0,
            "revision": 1,
            "terminal": False,
            "human_review_required": True,
            "human_review_completed": False,
            "client_delivery_allowed": False,
            "integrity_sha256": "running-integrity",
        }
        self.terminal = {
            **self.running,
            "status": "review_required",
            "completed_stages": ["final_comprehensive_report_generation"],
            "stage_results": {
                "final_comprehensive_report_generation": {
                    "status": "complete",
                    "report_package": {
                        "service_id": "comprehensive",
                        "report_id": "report_projection_race",
                        "report_language": "en",
                        "locale": "en",
                        "markdown": "# Terminal report\n",
                        "html": "<h1>Terminal report</h1>",
                        "pdf_base64": "JVBERi0xLjQ=",
                        "pdf_filename": "nico-comprehensive-projection-race.pdf",
                        "canonical_truth_sha256": "truth-sha",
                        "json": {
                            "report_id": "report_projection_race",
                            "report_language": "en",
                            "locale": "en",
                            "identity": {
                                "run_id": identity["run_id"],
                                "repository": identity["repository"],
                                "commit_sha": identity["commit_sha"],
                                "evidence_ledger_id": identity["evidence_ledger_id"],
                                "report_language": "en",
                            },
                            "assessment": {
                                "report_language": "en",
                                "locale": "en",
                            },
                            "technical_maturity": 93,
                        },
                    },
                    "assessment": {
                        "executive_summary": "Terminal assessment",
                        "maturity_signal": {
                            "technical_maturity": 93,
                            "evidence_adjusted": 90,
                        },
                        "sections": [],
                        "human_review_required": True,
                        "client_ready": False,
                        "client_delivery_allowed": False,
                    },
                }
            },
            "progress_percent": 100.0,
            "revision": 2,
            "terminal": True,
            "integrity_sha256": "terminal-integrity",
        }
        report = self.terminal["stage_results"][
            "final_comprehensive_report_generation"
        ]["report_package"]
        pdf = base64.b64decode(report["pdf_base64"], validate=True)
        report["pdf_sha256"] = hashlib.sha256(pdf).hexdigest()
        report["canonical_truth_sha256"] = canonical_sha256(report["json"])

    def resume(self, run_id: str, *, max_stages: int | None = None) -> dict:
        assert run_id == "comprun_projection_race"
        return deepcopy(self.running)

    def load(self, run_id: str) -> dict:
        assert run_id == "comprun_projection_race"
        return deepcopy(self.terminal)


def test_continue_reprojects_terminal_record_after_async_publication_race() -> None:
    service = _PublicationRaceService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    app.state.comprehensive_runtime = {
        "configured": True,
        "persistence_adapter": "postgres",
        "storage_source": "DATABASE_URL",
    }
    register_comprehensive_api_routes(app, controller=controller)

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_projection_race/continue",
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["terminal"] is True
    assert body["record"]["status"] == "review_required"
    assert body["record"]["terminal"] is True
    assert body["reports"]["markdown"] == "# Terminal report\n"
    assert body["reports"]["pdf_base64"] == "JVBERi0xLjQ="
    assert body["assessment"]["maturity_signal"]["technical_maturity"] == 93
    assert body["assessment"]["maturity_signal"]["evidence_adjusted"] == 90
