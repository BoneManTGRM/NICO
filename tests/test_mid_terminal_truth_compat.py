from __future__ import annotations

from uuid import uuid4

import pytest
from fastapi import HTTPException

from nico import lifecycle_status_hardening, mid_live_status_api
from nico.mid_terminal_truth_compat import (
    _enrich_blocked_report_summary,
    _optional_scope_matches,
    install_mid_terminal_truth_compat,
)
from nico.storage import STORE


def _run_id() -> str:
    return f"midrun_compat_{uuid4().hex[:12]}"


def test_blocked_report_projects_score_coverage_and_maturity_into_summary() -> None:
    run_id = _run_id()
    STORE.put(
        "reports",
        f"mid_report_{run_id}",
        {
            "report_id": f"mid_report_{run_id}",
            "run_id": run_id,
            "customer_id": "customer_compat",
            "project_id": "project_compat",
            "status": "blocked",
            "report_path": "mid_run",
            "report_version": "mid-test-v1",
            "formats": {
                "json": {
                    "technical_score": 74,
                    "maturity_signal": {
                        "level": "Mid",
                        "score": 74,
                        "summary": "Seven-section weighted score retained for review.",
                        "evidence_readiness_score": 83,
                    },
                    "evidence_coverage": {
                        "calculated": True,
                        "percent": 83,
                        "numerator": 10,
                        "denominator": 12,
                    },
                    "decision_summary": {
                        "technical_score": 74,
                        "recommended_actions": ["Review retained findings."],
                    },
                }
            },
            "report_quality_manifest": {
                "status": "blocked",
                "issues": [
                    {
                        "severity": "critical",
                        "code": "invalid_pdf_export",
                        "message": "The PDF export was invalid.",
                    }
                ],
            },
        },
    )
    result = {
        "run_id": run_id,
        "customer_id": "customer_compat",
        "project_id": "project_compat",
        "report_generation_status": "blocked",
        "assessment": {},
    }

    output = _enrich_blocked_report_summary(result)

    assert output["technical_score"] == 74
    assert output["maturity_signal"]["level"] == "Mid"
    assert output["evidence_coverage"]["percent"] == 83
    assert output["assessment"]["maturity_signal"]["score"] == 74
    assert output["assessment"]["evidence_coverage"]["numerator"] == 10
    assert output["mid_report"]["status"] == "blocked"
    assert output["mid_report"]["technical_score"] == 74
    assert output["blocked_report_summary_projected"] is True


def test_optional_scope_fields_are_validated_independently() -> None:
    record = {
        "customer_id": "customer_expected",
        "project_id": "project_expected",
        "request": {},
    }

    assert _optional_scope_matches(record, "", "") is True
    assert _optional_scope_matches(record, "customer_expected", "") is True
    assert _optional_scope_matches(record, "", "project_expected") is True
    assert _optional_scope_matches(record, "customer_wrong", "") is False
    assert _optional_scope_matches(record, "", "project_wrong") is False
    assert _optional_scope_matches(record, "customer_expected", "project_wrong") is False


def test_live_status_wrapper_rejects_one_wrong_scope_even_when_other_scope_is_omitted(monkeypatch) -> None:
    install_mid_terminal_truth_compat()
    run_id = _run_id()
    STORE.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "workflow": "mid_assessment",
            "customer_id": "customer_expected",
            "project_id": "project_expected",
            "status": "running",
            "request": {},
            "response": {"run_id": run_id, "status": "running"},
        },
    )

    with pytest.raises(HTTPException) as customer_error:
        mid_live_status_api.mid_live_status_response(run_id, customer_id="customer_wrong", project_id="")
    with pytest.raises(HTTPException) as project_error:
        lifecycle_status_hardening.mid_live_status_response(run_id, customer_id="", project_id="project_wrong")

    assert customer_error.value.status_code == 404
    assert project_error.value.status_code == 404
