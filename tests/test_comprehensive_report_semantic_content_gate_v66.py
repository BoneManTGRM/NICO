from __future__ import annotations

import pytest

from nico.comprehensive_report_semantic_content_gate_v66 import (
    validate_retained_decision_content,
)


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
        "markdown": """
## Finding and Remediation Register
NICO-FINDING-ABC
## Review-Required Candidate Register
- Confirmed material findings: 0.
- Review-required candidates: 59.
- Score effect: assurance-only until triaged.
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
