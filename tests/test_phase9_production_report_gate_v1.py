from __future__ import annotations

import pytest

from nico.phase9_production_report_gate_v1 import (
    assert_production_report,
    contextual_title,
    normalized_filename,
    validate_production_report,
)


def finding(fid: str, title: str = "operations page has concentrated branching and elevated change risk") -> dict:
    return {
        "finding_id": fid,
        "category": "architecture",
        "title": title,
        "location": "apps/web/app/operations/page.tsx:177",
        "acceptance_criteria": [
            "Complexity is <= 30 [method: metric_comparison] [target commit: abc]",
            "Tests pass [method: automated_test] [target commit: abc]",
        ],
    }


def test_clean_report_passes() -> None:
    report = {"approval_state": "FINAL-PENDING-APPROVAL", "canonical_findings": [finding("RISK-1")]}
    result = assert_production_report(report, filename="assessment-FINAL-PENDING-APPROVAL.pdf")
    assert result["valid"] is True


def test_duplicate_semantic_finding_fails() -> None:
    report = {"canonical_findings": [finding("RISK-1"), finding("RISK-2")]}
    result = validate_production_report(report)
    assert result["valid"] is False
    assert result["duplicate_finding_keys"]


def test_duplicate_acceptance_fails_after_metadata_normalization() -> None:
    item = finding("RISK-1")
    item["acceptance_criteria"].append("Complexity is <= 30 [method: exact_sha_rerun] [target commit: def]")
    result = validate_production_report({"canonical_findings": [item]})
    assert result["duplicate_acceptance"]


def test_generic_title_fails_and_contextual_title_repairs() -> None:
    item = finding("RISK-1", "High-complexity code hotspot")
    result = validate_production_report({"canonical_findings": [item]})
    assert result["generic_title_findings"] == ["RISK-1"]
    assert "operations page" in contextual_title(item)


def test_terminal_filename_is_idempotent() -> None:
    assert normalized_filename(
        "assessment-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf",
        "FINAL-PENDING-APPROVAL",
    ) == "assessment-FINAL-PENDING-APPROVAL.pdf"


def test_placeholder_fails_closed() -> None:
    item = finding("RISK-1")
    item["recommendation"] = "TODO"
    with pytest.raises(RuntimeError):
        assert_production_report({"canonical_findings": [item]})
