from copy import deepcopy

import pytest

from nico.client_finding_remediation_register_v1 import _finding_location
from nico.client_finding_remediation_register_v3 import normalize_finding_remediation_register


@pytest.mark.parametrize(
    ("location", "expected"),
    [
        ("src/panel.tsx:10", ("src/panel.tsx", 10, None, None)),
        ("src/panel.tsx:10:4", ("src/panel.tsx", 10, 4, None)),
        ("src/panel.tsx:10-20", ("src/panel.tsx", 10, None, 20)),
        ("src/panel.tsx:10-20:4", ("src/panel.tsx", 10, 4, 20)),
    ],
)
def test_ranged_location_is_not_treated_as_a_filename(location, expected):
    assert _finding_location({"location": location, "line": 10}) == expected


def _record():
    return {
        "finding_id": "SYNTHETIC-REVIEW-ONLY",
        "path": "src/panel.tsx",
        "line": 10,
        "end_line": 20,
        "column": None,
        "location": "src/panel.tsx:10",
        "rule_id": "complexity_hotspot",
        "symbol": "panel",
        "category": "architecture",
        "status": "review_required",
        "priority": "P2",
        "technical_severity": "moderate",
        "measured_cyclomatic_complexity": 30,
        "human_disposition_required": True,
        "human_disposition": {"status": "needs_more_evidence", "rationale": "Synthetic pending review"},
        "verification": [
            "The exact-SHA rerun no longer reports cyclomatic complexity of 30 or greater at src/panel.tsx:10",
            "The exact-SHA rerun no longer reports this condition at src/panel.tsx:10-20:10",
            "The exact-SHA rerun no longer reports this condition at src/panel.tsx:10-20:10.",
            "Targeted tests and the repository's full required-check suite pass on the remediation commit",
            "Targeted tests and the repository's full required-check suite pass on the remediation commit.",
            "Check the exact text `value.`",
            "Check the exact text `value`",
        ],
    }


def test_retained_generated_references_are_repaired_without_losing_review_obligations():
    record = _record()
    original = deepcopy(record)
    canonical = {"identity": {"repository": "example/synthetic-service"}}
    result = normalize_finding_remediation_register({"code_findings": [record]}, canonical)
    item = result["code_findings"][0]
    verification = item["verification"]
    assert not any(":10-20:10" in value for value in verification)
    assert len(verification) == 5
    assert sum("full required-check suite" in value for value in verification) == 1
    assert any("30 or greater" in value for value in verification)
    assert any("src/panel.tsx:10-20" in value for value in verification)
    assert "Check the exact text `value.`" in verification
    assert "Check the exact text `value`" in verification
    for field in ("status", "priority", "technical_severity", "measured_cyclomatic_complexity", "human_disposition_required", "human_disposition"):
        assert item[field] == original[field]
    assert original["finding_id"] in item["finding_aliases"]
    assert record == original
    again = normalize_finding_remediation_register(result, canonical)
    assert again["code_findings"][0]["verification"] == verification
    assert again["code_findings"][0]["finding_id"] == item["finding_id"]


def test_explicit_column_and_distinct_source_reference_are_not_rewritten():
    record = _record()
    record["column"] = 10
    record["location"] = "src/panel.tsx:10-20:10"
    record["verification"] = [
        "The exact-SHA rerun no longer reports this condition at src/panel.tsx:10-20:10.",
        "The exact-SHA rerun no longer reports this condition at src/other.tsx:10-20:10.",
    ]
    result = normalize_finding_remediation_register(
        {"code_findings": [record]}, {"identity": {"repository": "example/synthetic-service"}}
    )
    assert result["code_findings"][0]["verification"] == record["verification"]


def test_custom_clause_with_generated_lead_in_keeps_significant_punctuation():
    record = _record()
    record["verification"] = [
        "The exact-SHA rerun no longer reports literal token abc.",
        "The exact-SHA rerun no longer reports literal token abc",
    ]
    result = normalize_finding_remediation_register(
        {"code_findings": [record]}, {"identity": {"repository": "example/synthetic-service"}}
    )
    assert result["code_findings"][0]["verification"] == record["verification"]


def test_cross_source_merge_preserves_distinct_requirements_and_bilingual_anchor():
    from nico import comprehensive_spanish_canonical_report_v87 as canonical_report
    from nico.comprehensive_spanish_canonical_acceptance_normalization_v96 import (
        install_comprehensive_spanish_canonical_acceptance_normalization_v96,
    )

    first = _record()
    second = deepcopy(first)
    second["finding_id"] = "SYNTHETIC-SECOND-SOURCE"
    second["verification"] = [value.removesuffix(".") + "." for value in first["verification"][:5]]
    second["verification"].append("Preserve the separately required characterization evidence")
    result = normalize_finding_remediation_register(
        {"code_findings": [first, second]}, {"identity": {"repository": "example/synthetic-service"}}
    )
    assert len(result["code_findings"]) == 1
    item = result["code_findings"][0]
    assert len(item["verification"]) == 6
    assert "SYNTHETIC-SECOND-SOURCE" in item["finding_aliases"]
    assert "Preserve the separately required characterization evidence" in item["verification"]
    install_comprehensive_spanish_canonical_acceptance_normalization_v96()
    reference = next(value for value in item["verification"] if "this condition at" in value)
    translated = canonical_report._translate_presentation_field(reference, "verification")
    assert "src/panel.tsx:10-20" in translated
    assert ":10-20:10" not in translated
    assert canonical_report._looks_like_untranslated_english(translated) is False
