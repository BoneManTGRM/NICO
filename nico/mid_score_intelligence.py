from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.full_assessment_scorecard import TECHNICAL_SECTION_WEIGHTS

MID_SCORE_INTELLIGENCE_VERSION = "nico.mid_score_intelligence.v1"
_TARGET_SCORE = 80


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _number(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0 <= parsed <= 100 else None


def _section_map(assessment: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(assessment.get("sections"))
        if isinstance(item, dict) and item.get("id")
    }


def _weighted_score(rows: list[dict[str, Any]]) -> int | None:
    total_weight = sum(int(row["weight"]) for row in rows)
    if not rows or total_weight <= 0:
        return None
    return round(sum(float(row["weighted_points"]) for row in rows) * 100 / total_weight)


def build_mid_score_intelligence(result: dict[str, Any]) -> dict[str, Any]:
    assessment = _dict(result.get("assessment")) or result
    sections = _section_map(assessment)
    rows: list[dict[str, Any]] = []

    for section_id, weight in TECHNICAL_SECTION_WEIGHTS.items():
        section = sections.get(section_id)
        if not section or str(section.get("status") or "").lower() == "gray":
            continue
        score = _number(section.get("score"))
        if score is None:
            continue
        weighted_points = round(score * weight / 100, 2)
        target = max(int(round(score)), _TARGET_SCORE)
        projected_lift = round(max(0, target - score) * weight / 100, 2)
        rows.append(
            {
                "section_id": section_id,
                "label": str(section.get("label") or section_id.replace("_", " ").title()),
                "score": int(round(score)),
                "status": str(section.get("status") or "unknown"),
                "weight": int(weight),
                "weighted_points": weighted_points,
                "maximum_weighted_points": int(weight),
                "weighted_gap_to_100": round(weight - weighted_points, 2),
                "bounded_target_score": target,
                "projected_lift_if_verified": projected_lift,
                "finding_count": len(_list(section.get("findings"))),
                "unavailable_count": len(_list(section.get("unavailable"))),
                "summary": str(section.get("summary") or ""),
            }
        )

    calculated_score = _weighted_score(rows)
    maturity = _dict(assessment.get("maturity_signal"))
    reported_score = _number(maturity.get("score"))
    constraints = sorted(
        rows,
        key=lambda row: (float(row["weighted_gap_to_100"]), -int(row["score"])),
        reverse=True,
    )[:4]
    projected_lift = round(sum(float(row["projected_lift_if_verified"]) for row in rows), 2)
    projected_score = None
    if calculated_score is not None:
        projected_score = min(100, round(calculated_score + projected_lift))

    report_status = str(result.get("report_generation_status") or _dict(result.get("mid_report")).get("status") or "pending")
    approval = _dict(result.get("approval_request"))
    review_status = str(approval.get("status") or result.get("approval_request_status") or "pending")
    reports = _dict(result.get("reports"))

    return {
        "version": MID_SCORE_INTELLIGENCE_VERSION,
        "status": "complete" if rows and calculated_score is not None else "pending",
        "score_contract": {
            "name": "Mid seven-section evidence-weighted technical score",
            "reported_score": int(round(reported_score)) if reported_score is not None else None,
            "calculated_score": calculated_score,
            "calculation_matches_reported_score": (
                calculated_score == int(round(reported_score)) if calculated_score is not None and reported_score is not None else None
            ),
            "express_directly_comparable": False,
            "express_comparison_note": (
                "Express is a faster baseline with a different evidence and scoring contract. "
                "Mid uses exact-snapshot repository evidence, scanner evidence, and seven fixed technical weights, so the numbers must not be read as the same test repeated."
            ),
            "gray_sections_excluded": True,
            "evidence_readiness_scored_separately": True,
            "score_forced_upward": False,
        },
        "weighted_sections": rows,
        "top_constraints": constraints,
        "bounded_improvement_scenario": {
            "target_policy": "Raise each scored section below 80 to 80 after verified remediation; leave stronger sections unchanged.",
            "current_score": calculated_score,
            "projected_score": projected_score,
            "projected_lift": projected_lift,
            "guaranteed": False,
            "requires_verified_reassessment": True,
            "new_findings_could_reduce_projection": True,
        },
        "report_lifecycle": {
            "draft_generation_status": report_status,
            "markdown_available": bool(reports.get("markdown")),
            "pdf_available": bool(reports.get("pdf_base64")),
            "human_review_status": review_status,
            "human_review_required": True,
            "client_delivery_allowed": False,
            "approved_final_report_available": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def attach_mid_score_intelligence(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    if str(output.get("assessment_type") or output.get("service_tier") or output.get("mode") or "mid").lower() not in {"mid", ""}:
        return output
    intelligence = build_mid_score_intelligence(output)
    output["mid_score_intelligence"] = intelligence
    assessment = _dict(output.get("assessment"))
    if assessment:
        assessment = deepcopy(assessment)
        assessment["score_intelligence"] = deepcopy(intelligence)
        output["assessment"] = assessment
    return output


__all__ = [
    "MID_SCORE_INTELLIGENCE_VERSION",
    "attach_mid_score_intelligence",
    "build_mid_score_intelligence",
]
