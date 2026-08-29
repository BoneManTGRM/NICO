from __future__ import annotations

import base64
import hashlib
from copy import deepcopy

from fastapi import FastAPI
from fastapi.testclient import TestClient

import nico.comprehensive_api_routes as routes
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


class _ActivePublicationService(_PublicationRaceService):
    """Expose a durable active marker that is already authoritative for this tick."""

    def __init__(self) -> None:
        super().__init__()
        self.load_calls = 0
        self.running["stage_results"] = {
            "final_comprehensive_report_generation": {
                "status": "running",
                "reason": "final_report_background_publication_in_progress",
                "stage_execution": {
                    "lease_id": "frpub_projection_active",
                    "detached_background_execution": True,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        }

    def load(self, run_id: str) -> dict:
        assert run_id == "comprun_projection_race"
        self.load_calls += 1
        raise AssertionError(
            "an active final-report continuation must not reload the full run"
        )


class _CompletedPublicationService(_PublicationRaceService):
    """Return the terminal record adopted by the first continuation load."""

    def __init__(self) -> None:
        super().__init__()
        self.load_calls = 0

    def resume(self, run_id: str, *, max_stages: int | None = None) -> dict:
        assert run_id == "comprun_projection_race"
        return deepcopy(self.terminal)

    def load(self, run_id: str) -> dict:
        assert run_id == "comprun_projection_race"
        self.load_calls += 1
        raise AssertionError(
            "an adopted terminal continuation must not reload the full run"
        )


class _NonFinalPublicationRaceService(_PublicationRaceService):
    """Keep the historical reload for a non-final background publication race."""

    def __init__(self) -> None:
        super().__init__()
        self.running["current_stage"] = "source_code_understanding"
        self.running["stage_results"] = {
            "source_code_understanding": {
                "status": "running",
                "reason": "background_stage_execution_in_progress",
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
        }


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


def test_browser_continue_reprojects_without_reviewer_package_digest(
    monkeypatch,
) -> None:
    def fail_if_called(_record):
        raise AssertionError(
            "public browser continuation must not digest reviewer artifact bodies"
        )

    monkeypatch.setattr(routes, "review_artifact_identity", fail_if_called)
    service = _PublicationRaceService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_projection_race/continue",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
        json={},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "continued"
    assert body["terminal"] is True
    assert body["reports"]["report_id"] == "report_projection_race"
    assert "markdown" not in body["reports"]
    assert "pdf_base64" not in body["reports"]
    assert "review_artifact_identity" not in body


def test_browser_continue_reuses_durable_active_projection_without_full_reload() -> None:
    service = _ActivePublicationService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_projection_race/continue",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
        json={"max_stages": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "continued"
    assert body["status"] == "running"
    assert body["terminal"] is False
    assert body["record"]["stage_results"][
        "final_comprehensive_report_generation"
    ]["status"] == "running"
    assert body["human_review_required"] is True
    assert body["client_delivery_allowed"] is False
    assert "review_artifact_identity" not in body
    assert service.load_calls == 0


def test_browser_continue_reuses_adopted_terminal_projection_without_full_reload() -> None:
    service = _CompletedPublicationService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_projection_race/continue",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
        json={"max_stages": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["operation"] == "continued"
    assert body["status"] == "review_required"
    assert body["terminal"] is True
    assert body["reports"]["report_id"] == "report_projection_race"
    assert body["reports"]["response_bounded"] is True
    assert "markdown" not in body["reports"]
    assert "pdf_base64" not in body["reports"]
    assert "review_artifact_identity" not in body
    assert service.load_calls == 0


def test_browser_continue_retains_non_final_background_publication_reload() -> None:
    service = _NonFinalPublicationRaceService()
    controller = ComprehensiveApiController(service)  # type: ignore[arg-type]
    app = FastAPI()
    register_comprehensive_api_routes(app, controller=controller)

    response = TestClient(app).post(
        "/assessment/comprehensive-run/comprun_projection_race/continue",
        headers={"x-nico-browser-projection": "terminal-manifest-v1"},
        json={"max_stages": 1},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "review_required"
    assert body["terminal"] is True
    assert body["reports"]["report_id"] == "report_projection_race"
