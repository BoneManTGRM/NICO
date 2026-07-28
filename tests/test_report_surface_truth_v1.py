from __future__ import annotations

import pytest

from nico.final_assessment_truth_v1 import TruthViolation
from nico.report_surface_truth_v1 import validate_localizations, validate_report_surfaces


def _assessment() -> dict:
    return {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "abc123",
        "run_id": "run-1",
        "maturity_signal": {
            "observed_performance": 80.0,
            "coverage_adjusted_maturity": 70.0,
            "evidence_adjusted_readiness": 62.0,
        },
        "approval_state": "FINAL-PENDING-APPROVAL",
        "client_ready": False,
        "client_delivery_allowed": False,
        "canonical_findings": [{"finding_id": "RISK-1"}],
        "unavailable_data_notes": ["static analysis incomplete"],
    }


def test_all_required_surfaces_must_match_one_truth_projection() -> None:
    assessment = _assessment()
    surfaces = {name: dict(assessment) for name in ("json", "markdown", "html", "pdf", "csv")}
    result = validate_report_surfaces(assessment, surfaces)
    assert result["valid"] is True
    assert result["validated_surfaces"] == ["csv", "html", "json", "markdown", "pdf"]


def test_missing_or_contradictory_surface_fails_closed() -> None:
    assessment = _assessment()
    surfaces = {name: dict(assessment) for name in ("json", "markdown", "html", "pdf")}
    with pytest.raises(TruthViolation, match="missing=.*csv"):
        validate_report_surfaces(assessment, surfaces)

    surfaces["csv"] = {**assessment, "client_ready": True}
    with pytest.raises(TruthViolation, match="mismatches=.*csv"):
        validate_report_surfaces(assessment, surfaces)


def test_localized_reports_may_translate_text_but_not_truth() -> None:
    english = _assessment()
    spanish = {**english, "title": "Evaluacion tecnica"}
    assert validate_localizations(english, spanish)["valid"] is True

    spanish["evidence_adjusted_readiness"] = 99.0
    spanish["maturity_signal"] = {**english["maturity_signal"], "evidence_adjusted_readiness": 99.0}
    with pytest.raises(TruthViolation):
        validate_localizations(english, spanish)
