from __future__ import annotations

from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-report-semantic-content-gate.v66"
_MARKER = "_nico_comprehensive_semantic_content_gate_v66"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value or "0").strip()))
    except (TypeError, ValueError):
        return 0


def validate_retained_decision_content(package: Mapping[str, Any]) -> dict[str, Any]:
    """Fail publication when retained decision content disappears from client formats."""

    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    findings = [
        item
        for item in canonical.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]
    hotspots = [
        item
        for item in canonical.get("architecture_hotspots") or []
        if isinstance(item, Mapping)
    ]
    review_summary = (
        canonical.get("review_candidate_summary")
        if isinstance(canonical.get("review_candidate_summary"), Mapping)
        else assessment.get("review_candidate_summary")
        if isinstance(assessment.get("review_candidate_summary"), Mapping)
        else {}
    )
    ci_context = (
        canonical.get("ci_operational_context")
        if isinstance(canonical.get("ci_operational_context"), Mapping)
        else assessment.get("ci_operational_context")
        if isinstance(assessment.get("ci_operational_context"), Mapping)
        else {}
    )
    combined = "\n".join(
        (
            str(package.get("markdown") or ""),
            str(package.get("html") or ""),
        )
    )
    lowered = combined.casefold()

    finding_count = len(findings)
    if finding_count:
        false_zero_markers = (
            "no unresolved priority finding retained",
            "contains 0 unique decision-grade findings",
            "exact-source findings: 0",
            "canonical findings: 0",
            "no canonical actionable finding was retained",
        )
        retained_false_zero = [marker for marker in false_zero_markers if marker in lowered]
        if retained_false_zero:
            raise ValueError(
                "client report suppressed retained canonical findings: "
                + ", ".join(retained_false_zero)
            )
        missing_ids = [
            identifier
            for item in findings
            if (identifier := _text(item.get("finding_id") or item.get("id")))
            and identifier.casefold() not in lowered
        ]
        if missing_ids:
            raise ValueError(
                "client report omitted retained canonical finding identifiers: "
                + ", ".join(missing_ids[:10])
            )
        if "detailed canonical findings" not in lowered and "hallazgos canónicos detallados" not in lowered:
            raise ValueError("client report omitted the detailed canonical finding register")

    if hotspots and not findings:
        raise ValueError(
            "client report declared zero canonical findings despite actionable exact-SHA complexity hotspots"
        )

    review_total = _integer(review_summary.get("review_required_total"))
    material_total = _integer(review_summary.get("verified_material_total"))
    if review_total:
        required_markers = (
            f"review-required candidates: {review_total}",
            f"confirmed material findings: {material_total}",
            "score effect: assurance-only until triaged",
            "review-required candidate register",
        )
        missing = [marker for marker in required_markers if marker.casefold() not in lowered]
        if missing:
            raise ValueError(
                "client report omitted review-candidate truth: " + ", ".join(missing)
            )

    if ci_context and "ci/cd operational readiness and historical health" not in lowered:
        raise ValueError(
            "client report omitted CI/CD operational health that must remain separate from configuration maturity"
        )

    return {
        "version": VERSION,
        "canonical_finding_count_rendered": finding_count,
        "architecture_hotspot_count_checked": len(hotspots),
        "review_required_candidate_count_rendered": review_total,
        "confirmed_material_candidate_count_rendered": material_total,
        "ci_operational_context_rendered": bool(ci_context),
        "false_zero_finding_claim_absent": True,
        "retained_finding_identifiers_present": True,
        "review_candidate_truth_present": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_comprehensive_report_semantic_content_gate_v66() -> dict[str, Any]:
    from nico import comprehensive_client_report_render_v60 as client_render

    current = client_render.validate_existing_report_accuracy
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current)
    def validate(package: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(current(package))
        content = validate_retained_decision_content(package)
        result["semantic_content_gate"] = content
        result.update(
            {
                "canonical_decision_content_verified": True,
                "review_candidate_truth_verified": True,
                "ci_operational_context_verified": True,
            }
        )
        return result

    setattr(validate, _MARKER, True)
    setattr(validate, "_nico_previous", current)
    client_render.validate_existing_report_accuracy = validate
    return {
        "status": "installed",
        "version": VERSION,
        "bound": client_render.validate_existing_report_accuracy is validate,
        "false_zero_finding_publication_blocked": True,
        "review_candidate_omission_blocked": True,
        "ci_operational_context_omission_blocked": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_report_semantic_content_gate_v66",
    "validate_retained_decision_content",
]
