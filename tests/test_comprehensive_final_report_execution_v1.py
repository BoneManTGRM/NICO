from __future__ import annotations

import base64

from fastapi import FastAPI

from nico.comprehensive_final_report_execution_v1 import (
    final_report_execution_readiness,
    install_comprehensive_final_report_execution,
    wrap_final_report_provider,
)
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY

PDF = base64.b64encode(b"%PDF-1.7\nfinal report\n%%EOF").decode("ascii")


def _package(**overrides):
    package = {
        "service_id": "comprehensive",
        "report_id": "comprehensive_report_final_test",
        "markdown": "# NICO Comprehensive Technical Assessment\n\nCLIENT DELIVERY NOT AUTHORIZED\n",
        "html": "<html><body><h1>NICO Comprehensive Technical Assessment</h1></body></html>",
        "json": {
            "service_id": "comprehensive",
            "identity": {"run_id": "comprun_final_test"},
            "decision_grade_contract": {
                "readiness_status": "Evidence Incomplete",
                "validation_issues": [
                    {
                        "code": "human_evidence_incomplete",
                        "severity": "error",
                    }
                ],
            },
        },
        "pdf_base64": PDF,
        "pdf_error": None,
        "pdf_page_count": 18,
        "canonical_truth_sha256": "a" * 64,
        "delivery_status": "Human Review Required",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    package.update(overrides)
    return package


def _context():
    return {
        "run_id": "comprun_final_test",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "b" * 40,
        "evidence_ledger_id": "ledger_final_test",
        "customer_id": "customer_test",
        "project_id": "project_test",
    }


def test_valid_final_artifacts_with_review_gate_complete_execution() -> None:
    def provider(_context):
        return {
            "status": "blocked",
            "reason": "decision_grade_report_contract_failed",
            "report_package": _package(),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    result = wrap_final_report_provider(provider)(_context())

    assert result["status"] == "complete"
    assert result["final_artifact_generation_complete"] is True
    assert result["final_package"] is True
    assert result["report_contract_status"] == "blocked"
    assert result["report_contract_reason"] == "decision_grade_report_contract_failed"
    assert result["final_report_execution_readiness"]["status"] == "generated_review_required"
    assert result["evidence"]["report_id"] == "comprehensive_report_final_test"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_critical_validation_issue_does_not_mislabel_generation_as_failed() -> None:
    result = wrap_final_report_provider(
        lambda _context: {
            "status": "blocked",
            "reason": "critical_consistency_issue",
            "report_package": _package(),
        }
    )(_context())

    assert result["status"] == "complete"
    assert result["report_contract_reason"] == "critical_consistency_issue"
    assert result["report_package"]["json"]["decision_grade_contract"]["validation_issues"][0]["severity"] == "error"
    assert result["client_delivery_allowed"] is False


def test_missing_markdown_remains_terminal_generation_failure() -> None:
    result = wrap_final_report_provider(
        lambda _context: {
            "status": "blocked",
            "reason": "markdown_missing",
            "report_package": _package(markdown=""),
        }
    )(_context())

    assert result["status"] == "blocked"
    assert result["final_report_execution_readiness"]["artifacts_ready"] is False
    assert result["final_report_execution_readiness"]["checks"]["markdown_present"] is False


def test_invalid_pdf_remains_terminal_generation_failure() -> None:
    readiness = final_report_execution_readiness(
        {
            "status": "blocked",
            "reason": "pdf_invalid",
            "report_package": _package(
                pdf_base64=base64.b64encode(b"not a pdf").decode("ascii")
            ),
        }
    )

    assert readiness["status"] == "generation_failed"
    assert readiness["checks"]["pdf_valid"] is False


def test_delivery_must_remain_blocked_for_execution_reclassification() -> None:
    result = wrap_final_report_provider(
        lambda _context: {
            "status": "blocked",
            "reason": "unsafe_delivery_state",
            "report_package": _package(client_delivery_allowed=True),
        }
    )(_context())

    assert result["status"] == "blocked"
    assert result["final_report_execution_readiness"]["checks"]["client_delivery_blocked"] is False


def test_complete_provider_is_not_reclassified() -> None:
    expected = {
        "status": "complete",
        "summary": "final package generated",
        "report_package": _package(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    result = wrap_final_report_provider(lambda _context: dict(expected))(_context())

    assert result["status"] == "complete"
    assert result["summary"] == "final package generated"
    assert result.get("report_contract_status") is None
    assert result["final_report_execution_readiness"]["artifacts_ready"] is True


def test_installer_wraps_only_final_provider() -> None:
    app = FastAPI()

    def core_provider(_context):
        return {"status": "blocked", "reason": "core_quality", "report_package": _package()}

    def final_provider(_context):
        return {"status": "blocked", "reason": "final_quality", "report_package": _package()}

    app.state.__setattr__(
        PROVIDER_STATE_KEY,
        {
            "report_generation": core_provider,
            "final_report_generation": final_provider,
        },
    )

    installed = install_comprehensive_final_report_execution(app)
    providers = getattr(app.state, PROVIDER_STATE_KEY)

    assert installed["bound"] is True
    assert providers["report_generation"] is core_provider
    assert providers["final_report_generation"] is not final_provider
    assert providers["final_report_generation"](_context())["status"] == "complete"


def test_installer_is_idempotent() -> None:
    app = FastAPI()
    provider = lambda _context: {
        "status": "blocked",
        "reason": "quality",
        "report_package": _package(),
    }
    app.state.__setattr__(PROVIDER_STATE_KEY, {"final_report_generation": provider})

    first = install_comprehensive_final_report_execution(app)
    wrapped = getattr(app.state, PROVIDER_STATE_KEY)["final_report_generation"]
    second = install_comprehensive_final_report_execution(app)

    assert first["status"] == "installed"
    assert second["status"] == "already_installed"
    assert getattr(app.state, PROVIDER_STATE_KEY)["final_report_generation"] is wrapped
