from __future__ import annotations

from nico.comprehensive_finding_integrity_v1 import build_finding_integrity_manifest


def test_authoritative_register_recommended_correction_is_retained() -> None:
    finding = {
        "finding_id": "NICO-FINDING-ALIAS",
        "priority": "P2",
        "path": "nico/example.py",
        "line": 12,
        "location": "nico/example.py:12",
        "observed_evidence": "cyclomatic_complexity=42; method=python_ast",
        "impact": "Concentrated branch logic increases regression risk.",
        "recommended_correction": "Decompose cohesive branch groups and preserve behavior.",
        "acceptance_criteria": [
            "Exact-SHA complexity is at or below 30.",
            "Characterization tests pass.",
        ],
        "cyclomatic_complexity": 42,
        "disposition": "human_review_required",
    }
    register = {
        "code_findings": [finding],
        "operational_findings": [],
        "summary": {"decision_finding_count": 1},
    }
    canonical = {"canonical_findings": [finding]}

    manifest = build_finding_integrity_manifest(canonical, register)

    assert manifest["validation_status"] == "valid"
    assert manifest["records"][0]["correction"] == (
        "Decompose cohesive branch groups and preserve behavior."
    )
