from __future__ import annotations

from pathlib import Path

import nico.express_async_api as express
from nico.canonical_assessment_contract_v1 import VERSION as CANONICAL_CONTRACT_VERSION
from nico.canonical_express_contract_binding_v1 import (
    VERSION,
    canonical_core_response,
    install_canonical_express_contract_binding_v1,
)


ROOT = Path(__file__).resolve().parents[1]


def _request() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_contract",
        "project_id": "project_contract",
        "report_language": "es-MX",
    }


def _complete_response() -> dict:
    return {
        "status": "complete",
        "run_id": "express_run_contract_v1",
        "assessment_type": "express",
        "service_tier": "express",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "tree_sha": "b" * 40,
        "assessment": {
            "sections": [
                {
                    "id": "code_audit",
                    "label": "Code quality",
                    "presented_score": 86,
                    "score_band_label": "STRONG",
                    "assurance_label": "VERIFIED",
                    "risk_disposition": "GREEN",
                },
                {
                    "id": "secrets_review",
                    "label": "Secrets posture",
                    "presented_score": 86,
                    "score_band_label": "STRONG",
                    "assurance_label": "REVIEW LIMITED",
                    "risk_disposition": "YELLOW",
                },
            ]
        },
        "reports": {
            "markdown": "# NICO Core assessment",
            "html": "<html><body>NICO Core assessment</body></html>",
            "pdf_base64": "JVBERi0xLjQK",
            "pdf_sha256": "c" * 64,
        },
        "human_review_required": True,
        "client_ready": False,
    }


def test_completed_express_response_receives_shared_core_contract() -> None:
    enriched = canonical_core_response(
        "express_run_contract_v1",
        _request(),
        _complete_response(),
    )

    assert enriched["assessment_type"] == "express"
    assert enriched["service_tier"] == "express"
    assert enriched["assessment_depth"] == "core"
    assert enriched["report_language"] == "es-MX"
    assert enriched["human_review_required"] is True
    assert enriched["client_ready"] is False
    assert enriched["client_delivery_allowed"] is False

    contract = enriched["canonical_assessment_contract"]
    assert contract["schema_version"] == CANONICAL_CONTRACT_VERSION
    assert contract["identity"]["run_id"] == "express_run_contract_v1"
    assert contract["identity"]["repository"] == "BoneManTGRM/NICO"
    assert contract["identity"]["commit_sha"] == "a" * 40
    assert contract["identity"]["assessment_depth"] == "core"
    assert contract["independent_core_and_strategic_scorecards_allowed"] is False
    assert contract["automatic_approval"] is False
    assert contract["client_delivery_allowed"] is False

    secrets = next(
        item
        for item in contract["canonical_score_and_assurance_ledger"]
        if item["control_id"] == "secrets_review"
    )
    assert secrets["technical_score"] == 86
    assert secrets["technical_band"] == "STRONG"
    assert secrets["evidence_assurance"] == "REVIEW LIMITED"
    assert secrets["risk_disposition"] == "YELLOW"

    core = enriched["canonical_core_contract"]
    assert core["schema_version"] == VERSION
    assert core["canonical_contract_version"] == CANONICAL_CONTRACT_VERSION
    assert core["same_contract_used_by_strategic"] is True
    assert core["independent_core_scorecard_allowed"] is False
    assert core["legacy_transport_identity_preserved"] is True


def test_installer_enriches_only_completed_report_ready_responses(monkeypatch) -> None:
    captured: list[dict] = []

    def recorder(run_id: str, request_payload: dict, response: dict) -> dict:
        captured.append(response)
        return response

    monkeypatch.setattr(express, "_record", recorder)
    installed = install_canonical_express_contract_binding_v1()

    assert installed["status"] == "installed"
    assert installed["completed_express_runs_receive_core_contract"] is True
    assert installed["running_or_failed_responses_modified"] is False

    complete = _complete_response()
    returned = express._record("express_run_contract_v1", _request(), complete)
    assert returned["canonical_assessment_contract"]["identity"]["assessment_depth"] == "core"
    assert captured[-1] is returned
    assert returned is not complete

    running = {
        "status": "running",
        "run_id": "express_run_running",
        "reports": {},
    }
    returned_running = express._record("express_run_running", _request(), running)
    assert returned_running is running
    assert "canonical_assessment_contract" not in returned_running

    failed = {
        "status": "failed",
        "run_id": "express_run_failed",
        "reports": _complete_response()["reports"],
    }
    returned_failed = express._record("express_run_failed", _request(), failed)
    assert returned_failed is failed
    assert "canonical_assessment_contract" not in returned_failed


def test_installer_is_idempotent(monkeypatch) -> None:
    def recorder(run_id: str, request_payload: dict, response: dict) -> dict:
        return response

    monkeypatch.setattr(express, "_record", recorder)
    first = install_canonical_express_contract_binding_v1()
    wrapped = express._record
    second = install_canonical_express_contract_binding_v1()

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert express._record is wrapped
    assert second["same_contract_used_by_strategic"] is True
    assert second["independent_core_scorecard_allowed"] is False


def test_production_bootstrap_installs_and_enforces_the_binding() -> None:
    source = (ROOT / "nico" / "api" / "terminal_authority_bootstrap.py").read_text(
        encoding="utf-8"
    )

    assert "install_canonical_express_contract_binding_v1" in source
    assert "CANONICAL_EXPRESS_CONTRACT" in source
    assert 'completed_express_runs_receive_core_contract") is not True' in source
    assert 'same_contract_used_by_strategic") is not True' in source
    assert 'independent_core_scorecard_allowed") is not False' in source
    assert 'client_delivery_allowed") is not False' in source
