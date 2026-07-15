from __future__ import annotations

from typing import Any

TRIAGE_AWARE_SCANNER_TRUTH_VERSION = "nico.triage_aware_scanner_finding_truth.v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _append_unique(items: list[Any], value: str) -> None:
    if value and value not in items:
        items.append(value)


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _category_counts(summary: dict[str, Any], category: str) -> dict[str, int]:
    by_category = _dict(summary.get("by_category"))
    value = by_category.get(category)
    if isinstance(value, dict):
        return {
            "raw": _int(value.get("raw")),
            "material": _int(value.get("material")),
            "review_required": _int(value.get("review_required")),
            "approved_or_nonblocking": _int(value.get("approved_or_nonblocking")),
            "excluded_test_only": _int(value.get("excluded_test_only")),
        }

    # Legacy scanner summaries exposed a single raw count plus severity buckets.
    raw = _int(value)
    severities = _dict(_dict(summary.get("severity_by_category")).get(category))
    material = _int(severities.get("critical")) + _int(severities.get("high"))
    return {
        "raw": raw,
        "material": material,
        "review_required": max(0, raw - material),
        "approved_or_nonblocking": 0,
        "excluded_test_only": 0,
    }


def apply_triage_aware_scanner_finding_truth(
    assessment: dict[str, Any],
    scanner_evidence: dict[str, Any],
) -> dict[str, Any]:
    """Apply score caps only to material findings, not raw or test-only counts.

    Review-required findings remain visible and affect confidence, but they do not
    automatically receive the same score cap as confirmed high-risk production
    findings. This function never upgrades missing scanner evidence to clean proof.
    """

    from nico import full_assessment_scanner_contract as contract

    summary = _dict(scanner_evidence.get("finding_summary"))
    sections = _section_map(assessment)
    changed = False
    material_total = 0
    review_total = 0
    excluded_total = 0

    for category, section_id in contract._SECTION_BY_CATEGORY.items():
        counts = _category_counts(summary, category)
        material = counts["material"]
        review_required = counts["review_required"]
        excluded = counts["excluded_test_only"]
        material_total += material
        review_total += review_required
        excluded_total += excluded
        section = sections.get(section_id)
        if not section:
            continue

        evidence = section.setdefault("evidence", [])
        findings = section.setdefault("findings", [])
        breakdown = section.setdefault("score_evidence_breakdown", {})
        previous = _int(section.get("score"))

        if counts["raw"] or excluded:
            _append_unique(
                evidence,
                (
                    f"Snapshot scanner triage for {category}: raw={counts['raw']}, material={material}, "
                    f"review_required={review_required}, approved_or_nonblocking={counts['approved_or_nonblocking']}, "
                    f"excluded_test_only={excluded}."
                ),
            )

        if material:
            cap = 54
            revised = min(previous, cap)
            section["score"] = revised
            section["status"] = "green" if revised >= 80 else "yellow" if revised >= 55 else "red"
            section["confidence"] = "material-scanner-findings-require-human-triage"
            _append_unique(
                findings,
                f"Triage {material} material {category} finding(s) before treating this section as clean or client-ready.",
            )
            breakdown.update(
                {
                    "scanner_finding_pre_cap_score": previous,
                    "scanner_finding_cap": cap,
                    "scanner_finding_final_score": revised,
                    "scanner_material_finding_count": material,
                    "scanner_review_required_count": review_required,
                    "scanner_excluded_test_only_count": excluded,
                    "raw_finding_count_not_used_as_material": True,
                }
            )
            changed = changed or revised != previous
        elif review_required:
            section["confidence"] = "scanner-review-items-disclosed"
            _append_unique(
                findings,
                f"Review {review_required} non-material or not-yet-confirmed {category} scanner item(s); these were not scored as confirmed production defects.",
            )
            breakdown.update(
                {
                    "scanner_finding_pre_cap_score": previous,
                    "scanner_finding_cap": None,
                    "scanner_finding_final_score": previous,
                    "scanner_material_finding_count": 0,
                    "scanner_review_required_count": review_required,
                    "scanner_excluded_test_only_count": excluded,
                    "raw_finding_count_not_used_as_material": True,
                }
            )
        elif excluded:
            _append_unique(
                evidence,
                f"{excluded} {category} scanner item(s) were classified as test/example-only evidence and excluded from production score caps.",
            )

        section["verified_claims"] = list(evidence)

    scorecard = assessment.setdefault("scorecard", {})
    scorecard["scanner_finding_summary"] = summary
    scorecard["scanner_finding_truth_version"] = TRIAGE_AWARE_SCANNER_TRUTH_VERSION
    scorecard["scanner_finding_truth_applied"] = bool(material_total or review_total or excluded_total)
    scorecard["scanner_material_finding_count"] = material_total
    scorecard["scanner_review_required_count"] = review_total
    scorecard["scanner_excluded_test_only_count"] = excluded_total
    scorecard["raw_scanner_counts_used_as_material"] = False

    if material_total:
        top_findings = assessment.setdefault("findings", [])
        _append_unique(
            top_findings,
            f"Snapshot scanners reported {material_total} material item(s) requiring human triage; raw, review-only, approved, and test-only counts were not treated as confirmed production defects.",
        )
    if changed:
        contract._recompute_score(assessment)
    return assessment


def install_triage_aware_scanner_finding_truth() -> dict[str, Any]:
    from nico import full_assessment_scanner_contract as contract

    current = contract.apply_scanner_finding_truth
    if getattr(current, "_nico_triage_aware_scanner_truth_v1", False):
        return {"status": "already_installed", "version": TRIAGE_AWARE_SCANNER_TRUTH_VERSION}
    setattr(apply_triage_aware_scanner_finding_truth, "_nico_triage_aware_scanner_truth_v1", True)
    setattr(apply_triage_aware_scanner_finding_truth, "_nico_previous", current)
    contract.apply_scanner_finding_truth = apply_triage_aware_scanner_finding_truth
    return {
        "status": "installed",
        "version": TRIAGE_AWARE_SCANNER_TRUTH_VERSION,
        "raw_finding_counts_used_as_material": False,
        "test_only_findings_score_blocking": False,
        "human_review_required": True,
    }


__all__ = [
    "TRIAGE_AWARE_SCANNER_TRUTH_VERSION",
    "apply_triage_aware_scanner_finding_truth",
    "install_triage_aware_scanner_finding_truth",
]
