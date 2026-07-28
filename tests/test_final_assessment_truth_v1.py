from __future__ import annotations

import pytest

from nico.final_assessment_truth_v1 import (
    FinalAssessmentTruthV1,
    ReportStatus,
    TruthViolation,
    build_report_filename,
    canonicalize_findings,
)


def _identity() -> dict[str, str]:
    return {
        "provider": "github",
        "repository": "BoneManTGRM/NICO",
        "immutable_revision": "a" * 40,
    }


def test_duplicate_finding_records_collapse_to_one_canonical_record() -> None:
    findings = [
        {
            "id": "legacy-a",
            "category": "security",
            "tool": "semgrep",
            "rule_id": "python.lang.security.audit.eval-detected",
            "path": "nico/runtime.py",
            "line": 42,
            "title": "Unsafe eval usage",
            "evidence": "eval(user_code)",
            "acceptance_criteria": ["Remove direct eval"],
        },
        {
            "id": "legacy-b",
            "category": "security",
            "tool": "semgrep",
            "rule_id": "python.lang.security.audit.eval-detected",
            "path": "./nico/runtime.py",
            "line": 42,
            "title": "Unsafe eval usage",
            "evidence": "eval(user_code)",
            "acceptance_criteria": ["Remove direct eval"],
        },
    ]

    canonical = canonicalize_findings(findings, _identity())

    assert len(canonical) == 1
    assert canonical[0]["finding_id"].startswith("RISK-")
    assert canonical[0]["legacy_finding_ids"] == ["legacy-a", "legacy-b"]
    assert len(canonical[0]["acceptance_criteria"]) == 1


def test_legacy_and_enriched_hotspot_records_with_string_location_collapse() -> None:
    findings = [
        {
            "id": "RISK-OLD",
            "category": "architecture",
            "title": "High-complexity code hotspot",
            "location": "apps/web/app/operations/page.tsx:177",
            "acceptance_criteria": ["Reduce complexity and retain behavior coverage"],
        },
        {
            "id": "RISK-P1-ENRICHED",
            "category": "architecture",
            "decision_title": "High-complexity code hotspot",
            "location": "apps/web/app/operations/page.tsx:177",
            "acceptance_criteria": [
                "Reduce complexity and retain behavior coverage",
                "Reduce complexity and retain behavior coverage",
            ],
            "roadmap_mappings": ["WP-02"],
        },
    ]

    canonical = canonicalize_findings(findings, _identity())

    assert len(canonical) == 1
    assert canonical[0]["canonical_path"] == "apps/web/app/operations/page.tsx"
    assert canonical[0]["canonical_line"] == 177
    assert canonical[0]["legacy_finding_ids"] == ["RISK-OLD", "RISK-P1-ENRICHED"]
    assert len(canonical[0]["acceptance_criteria"]) == 1
    assert canonical[0]["roadmap_mappings"] == ["WP-02"]


def test_frozen_truth_rejects_contradictory_report_surface() -> None:
    truth = FinalAssessmentTruthV1.freeze(
        {
            "assessment_identity": _identity(),
            "technical_score": 70.4,
            "evidence_adjusted_score": 62.0,
            "approval_state": "pending_human_approval",
            "limitations": [{"id": "missing-static-analysis"}],
            "canonical_findings": [],
        }
    )

    with pytest.raises(TruthViolation, match="contradicts frozen assessment truth"):
        truth.assert_surface(
            {
                "technical_score": 83,
                "evidence_adjusted_score": 81,
                "limitation_count": 0,
                "ranked_risks": [],
                "approval_state": "approved",
            }
        )


def test_report_filename_is_idempotent_and_has_one_terminal_status() -> None:
    first = build_report_filename(
        "ara-assessment-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL",
        language="en",
        status=ReportStatus.FINAL_PENDING_APPROVAL,
        extension="pdf",
    )
    second = build_report_filename(
        first,
        language=None,
        status=ReportStatus.FINAL_PENDING_APPROVAL,
        extension="pdf",
    )

    assert first == "ara-assessment-en-FINAL-PENDING-APPROVAL.pdf"
    assert second == first
    assert first.count("FINAL-PENDING-APPROVAL") == 1


def test_scores_outside_zero_to_one_hundred_are_rejected() -> None:
    with pytest.raises(TruthViolation, match="Technical score"):
        FinalAssessmentTruthV1.freeze(
            {
                "assessment_identity": _identity(),
                "technical_score": 101,
                "evidence_adjusted_score": 50,
                "canonical_findings": [],
            }
        )
