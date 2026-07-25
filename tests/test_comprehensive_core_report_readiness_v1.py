from __future__ import annotations

import base64

from fastapi import FastAPI

from nico.comprehensive_core_report_readiness_v1 import (
    core_report_artifact_readiness,
    install_comprehensive_core_report_readiness,
    wrap_core_report_provider,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

PDF = base64.b64encode(b"%PDF-1.7\ncore report\n%%EOF").decode("ascii")


def _package(**overrides):
    package = {
        "service_id": "comprehensive",
        "report_id": "comprehensive_report_test",
        "markdown": "# NICO Comprehensive Technical Assessment\n",
        "html": "<html><body><h1>NICO Comprehensive Technical Assessment</h1></body></html>",
        "json": {"service_id": "comprehensive", "identity": {"run_id": "comprun_test"}},
        "pdf_base64": PDF,
        "pdf_error": None,
        "pdf_page_count": 12,
        "canonical_truth_sha256": "a" * 64,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package.update(overrides)
    return package


def _context():
    return {
        "run_id": "comprun_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "b" * 40,
        "evidence_ledger_id": "ledger_test",
        "customer_id": "customer_test",
        "project_id": "project_test",
    }


def test_blocked_quality_contract_with_valid_core_artifacts_proceeds_review_limited() -> None:
    def provider(_context):
        return {
            "status": "blocked",
            "reason": "decision_grade_report_contract_failed",
            "report_package": _package(),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    result = wrap_core_report_provider(provider)(_context())

    assert result["status"] == "complete"
    assert result["core_artifact_generation_complete"] is True
    assert result["report_contract_status"] == "blocked"
    assert result["report_contract_reason"] == "decision_grade_report_contract_failed"
    assert result["core_report_artifact_readiness"]["status"] == "review_limited"
    assert result["evidence"]["report_id"] == "comprehensive_report_test"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_invalid_pdf_keeps_core_stage_blocked() -> None:
    def provider(_context):
        return {
            "status": "blocked",
            "reason": "pdf_invalid",
            "report_package": _package(pdf_base64=base64.b64encode(b"not a pdf").decode("ascii")),
        }

    result = wrap_core_report_provider(provider)(_context())

    assert result["status"] == "blocked"
    assert result["core_report_artifact_readiness"]["artifacts_ready"] is False
    assert result["core_report_artifact_readiness"]["checks"]["pdf_valid"] is False


def test_missing_canonical_json_keeps_core_stage_blocked() -> None:
    result = core_report_artifact_readiness(
        {
            "status": "blocked",
            "reason": "contract_failed",
            "report_package": _package(json={}),
        }
    )

    assert result["status"] == "blocked"
    assert result["checks"]["canonical_json_present"] is False


def test_complete_provider_is_not_reclassified() -> None:
    expected = {
        "status": "complete",
        "summary": "complete package",
        "report_package": _package(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    result = wrap_core_report_provider(lambda _context: dict(expected))(_context())

    assert result["status"] == "complete"
    assert result["summary"] == "complete package"
    assert result.get("report_contract_status") is None
    assert result["core_report_artifact_readiness"]["artifacts_ready"] is True


def test_installer_wraps_only_core_provider_and_leaves_final_provider_unchanged() -> None:
    app = FastAPI()

    def core_provider(_context):
        return {"status": "blocked", "reason": "quality", "report_package": _package()}

    def final_provider(_context):
        return {"status": "blocked", "reason": "quality", "report_package": _package()}

    app.state.__setattr__(
        PROVIDER_STATE_KEY,
        {
            "report_generation": core_provider,
            "final_report_generation": final_provider,
        },
    )

    installed = install_comprehensive_core_report_readiness(app)
    providers = getattr(app.state, PROVIDER_STATE_KEY)

    assert installed["bound"] is True
    assert providers["report_generation"] is not core_provider
    assert providers["report_generation"](_context())["status"] == "complete"
    assert providers["final_report_generation"] is final_provider
    assert providers["final_report_generation"](_context())["status"] == "blocked"


def test_installer_is_idempotent() -> None:
    app = FastAPI()
    provider = lambda _context: {"status": "blocked", "reason": "quality", "report_package": _package()}
    app.state.__setattr__(PROVIDER_STATE_KEY, {"report_generation": provider})

    first = install_comprehensive_core_report_readiness(app)
    wrapped = getattr(app.state, PROVIDER_STATE_KEY)["report_generation"]
    second = install_comprehensive_core_report_readiness(app)

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert getattr(app.state, PROVIDER_STATE_KEY)["report_generation"] is wrapped
