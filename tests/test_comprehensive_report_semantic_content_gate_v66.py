from __future__ import annotations

import pytest

from nico.candidate_phase1_report_workload_text_v1 import rewrite_compact_markdown
from nico.comprehensive_report_semantic_content_gate_v66 import (
    validate_retained_decision_content,
)


CURRENT_SCORE_EFFECT = (
    "Score effect: assurance-only while human disposition remains pending; "
    "NICO technical triage is complete."
)
AUTHORIZED_SCORE_EFFECT = (
    "Score effect: assurance-only while authorized human disposition remains pending; "
    "NICO automated technical triage is complete."
)
LEGACY_SCORE_EFFECT = "Score effect: assurance-only until triaged."


def _review_package(score_effect: str) -> dict:
    return {
        "json": {
            "canonical_findings": [],
            "architecture_hotspots": [],
            "review_candidate_summary": {
                "review_required_total": 59,
                "verified_material_total": 0,
            },
        },
        "markdown": f"""
## Review-Required Candidate Register
- Confirmed material findings: 0.
- Review-required candidates: 59.
- {score_effect}
""",
        "html": "",
    }


def test_semantic_gate_accepts_authoritative_register_candidates_and_ci_context() -> None:
    package = {
        "json": {
            "canonical_findings": [
                {
                    "finding_id": "NICO-FINDING-ABC",
                    "title": "Reduce complexity in build_report",
                }
            ],
            "architecture_hotspots": [{"path": "nico/report.py"}],
            "review_candidate_summary": {
                "review_required_total": 59,
                "verified_material_total": 0,
            },
            "ci_operational_context": {"successful_runs": 83},
        },
        "markdown": f"""
## Finding and Remediation Register
NICO-FINDING-ABC
## Review-Required Candidate Register
- Confirmed material findings: 0.
- Review-required candidates: 59.
- {CURRENT_SCORE_EFFECT}
## CI/CD Operational Readiness and Historical Health
""",
        "html": "",
    }

    result = validate_retained_decision_content(package)

    assert result["canonical_finding_count_rendered"] == 1
    assert result["review_required_candidate_count_rendered"] == 59
    assert result["ci_operational_context_rendered"] is True
    assert result["authoritative_finding_register_present"] is True
    assert result["finding_register_marker"] == "finding and remediation register"
    assert result["review_candidate_score_effect_truth_present"] is True
    assert result["superseded_review_candidate_score_effect_absent"] is True


def test_semantic_gate_accepts_authorized_phase1_score_effect_wording() -> None:
    result = validate_retained_decision_content(_review_package(AUTHORIZED_SCORE_EFFECT))

    assert result["review_candidate_score_effect_truth_present"] is True
    assert "authorized human disposition" in result[
        "review_candidate_score_effect_marker"
    ]


def test_semantic_gate_accepts_actual_phase1_compact_markdown_rewrite() -> None:
    canonical = {
        "review_candidate_summary": {
            "review_required_total": 59,
            "verified_material_total": 0,
        }
    }
    legacy = _review_package(LEGACY_SCORE_EFFECT)["markdown"]
    rewritten = rewrite_compact_markdown(legacy, canonical, spanish=False)

    assert LEGACY_SCORE_EFFECT not in rewritten
    assert CURRENT_SCORE_EFFECT in rewritten
    result = validate_retained_decision_content(
        {
            "json": canonical,
            "markdown": rewritten,
            "html": "",
        }
    )
    assert result["review_candidate_score_effect_truth_present"] is True


def test_semantic_gate_rejects_superseded_until_triaged_score_effect() -> None:
    with pytest.raises(ValueError, match="superseded review-candidate score-effect"):
        validate_retained_decision_content(_review_package(LEGACY_SCORE_EFFECT))


def test_semantic_gate_rejects_missing_current_score_effect_truth() -> None:
    package = _review_package("Score effect: assurance-only.")

    with pytest.raises(ValueError, match="human disposition is pending"):
        validate_retained_decision_content(package)


def test_semantic_gate_accepts_spanish_authoritative_register_heading() -> None:
    package = {
        "json": {
            "canonical_findings": [{"finding_id": "NICO-FINDING-ABC"}],
            "architecture_hotspots": [{"path": "nico/report.py"}],
        },
        "markdown": """
## Registro de hallazgos y remediación
NICO-FINDING-ABC
""",
        "html": "",
    }

    result = validate_retained_decision_content(package)

    assert result["authoritative_finding_register_present"] is True
    assert result["finding_register_marker"] == "registro de hallazgos y remediación"


def test_semantic_gate_keeps_legacy_detailed_heading_compatible() -> None:
    package = {
        "json": {
            "canonical_findings": [{"finding_id": "NICO-FINDING-ABC"}],
            "architecture_hotspots": [{"path": "nico/report.py"}],
        },
        "markdown": """
## Detailed Canonical Findings
NICO-FINDING-ABC
""",
        "html": "",
    }

    result = validate_retained_decision_content(package)

    assert result["authoritative_finding_register_present"] is True


def test_semantic_gate_rejects_false_zero_finding_claim() -> None:
    package = {
        "json": {
            "canonical_findings": [{"finding_id": "NICO-FINDING-ABC"}],
            "architecture_hotspots": [{"path": "nico/report.py"}],
        },
        "markdown": "No unresolved priority finding retained",
        "html": "",
    }

    with pytest.raises(ValueError, match="suppressed retained canonical findings"):
        validate_retained_decision_content(package)


def test_semantic_gate_rejects_missing_authoritative_register() -> None:
    package = {
        "json": {
            "canonical_findings": [{"finding_id": "NICO-FINDING-ABC"}],
            "architecture_hotspots": [{"path": "nico/report.py"}],
        },
        "markdown": "NICO-FINDING-ABC",
        "html": "",
    }

    with pytest.raises(ValueError, match="authoritative finding and remediation register"):
        validate_retained_decision_content(package)


def test_semantic_gate_rejects_hotspots_with_zero_canonical_findings() -> None:
    package = {
        "json": {
            "canonical_findings": [],
            "architecture_hotspots": [{"path": "nico/report.py"}],
        },
        "markdown": "",
        "html": "",
    }

    with pytest.raises(ValueError, match="actionable exact-SHA complexity hotspots"):
        validate_retained_decision_content(package)


def test_semantic_gate_rejects_missing_review_candidate_truth() -> None:
    package = {
        "json": {
            "canonical_findings": [],
            "architecture_hotspots": [],
            "review_candidate_summary": {
                "review_required_total": 614,
                "verified_material_total": 0,
            },
        },
        "markdown": "",
        "html": "",
    }

    with pytest.raises(ValueError, match="omitted review-candidate truth"):
        validate_retained_decision_content(package)


def test_semantic_gate_rejects_missing_ci_operational_boundary() -> None:
    package = {
        "json": {
            "canonical_findings": [],
            "architecture_hotspots": [],
            "ci_operational_context": {"successful_runs": 83},
        },
        "markdown": "",
        "html": "",
    }

    with pytest.raises(ValueError, match="omitted CI/CD operational health"):
        validate_retained_decision_content(package)
