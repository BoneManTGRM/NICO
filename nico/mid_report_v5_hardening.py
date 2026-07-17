from __future__ import annotations

from copy import deepcopy
from typing import Any


MID_REPORT_V5_HARDENING_VERSION = "nico.mid_report_v5_hardening.v1"
_PATCH_MARKER = "_nico_mid_report_v5_hardening"
_PARAGRAPH_PATCH_MARKER = "_nico_mid_report_heading_aliases_v1"
_WEIGHTS = {
    "code_audit": 20,
    "dependency_health": 15,
    "secrets_review": 10,
    "static_analysis": 15,
    "ci_cd": 15,
    "architecture_debt": 15,
    "velocity_complexity": 10,
}
_LIST_FIELDS = (
    "evidence",
    "findings",
    "unavailable",
    "missing_evidence_sources",
    "failed_evidence_tools",
    "scope_disclosures",
)


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _score(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return max(0, min(100, int(float(value))))
    except (TypeError, ValueError):
        return None


def _texts(value: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for item in _list(value):
        text = " ".join(str(item or "").split())
        key = text.lower()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _sections_by_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in _list(payload.get("sections"))
        if isinstance(item, dict)
    }


def _canonical_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    integrity = _dict(payload.get("score_integrity"))
    supplied_by_id: dict[str, dict[str, Any]] = {}
    for item in _list(integrity.get("weighted_rows")):
        if not isinstance(item, dict):
            continue
        section_id = str(item.get("section_id") or "")
        if section_id in _WEIGHTS and section_id not in supplied_by_id and _score(item.get("score")) is not None:
            supplied_by_id[section_id] = item

    sections = _sections_by_id(payload)
    rows: list[dict[str, Any]] = []
    for section_id, weight in _WEIGHTS.items():
        supplied = supplied_by_id.get(section_id, {})
        section = sections.get(section_id, {})
        score = _score(supplied.get("score"))
        if score is None:
            score = _score(section.get("score"))
        if score is None:
            continue
        rows.append({
            "section_id": section_id,
            "label": supplied.get("label") or section.get("label") or section_id.replace("_", " ").title(),
            "score": score,
            "weight": weight,
            "weighted_contribution": round(score * weight / 100, 2),
            "truth_status": supplied.get("truth_status") or section.get("truth_status") or section.get("status"),
        })
    return rows


def _fallback_score(payload: dict[str, Any]) -> int | None:
    decision = _dict(payload.get("decision_summary"))
    integrity = _dict(payload.get("score_integrity"))
    for value in (
        decision.get("technical_score"),
        integrity.get("final_report_score"),
        integrity.get("reported_score"),
        integrity.get("calculated_score"),
        payload.get("technical_score"),
    ):
        score = _score(value)
        if score is not None:
            return score
    return None


def _safe_canonical_score(payload: dict[str, Any]) -> int | None:
    rows = _canonical_rows(payload)
    if len(rows) == len(_WEIGHTS) and sum(int(row["weight"]) for row in rows) == 100:
        return round(sum(float(row["score"]) * int(row["weight"]) / 100 for row in rows))
    return _fallback_score(payload)


def _safe_section_limitations(section: dict[str, Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for field in ("unavailable", "missing_evidence_sources", "failed_evidence_tools", "scope_disclosures"):
        for text in _texts(section.get(field)):
            key = text.lower()
            if key not in seen:
                seen.add(key)
                output.append(text)
    return output


def _safe_primary_constraints(payload: dict[str, Any]) -> list[dict[str, Any]]:
    sections = _sections_by_id(payload)
    constraints: list[dict[str, Any]] = []
    rows = sorted(_canonical_rows(payload), key=lambda item: int(item["score"]))
    for row in rows:
        section = sections.get(str(row.get("section_id") or ""), {})
        score = _score(row.get("score"))
        findings = _texts(section.get("findings"))
        limitations = _safe_section_limitations(section)
        if score is None or (score >= 80 and not findings and not limitations):
            continue
        constraints.append({
            "section_id": row.get("section_id"),
            "label": row.get("label") or section.get("label"),
            "score": score,
            "primary_reason": findings[0] if findings else limitations[0] if limitations else "The evidence-supported score remains below the stronger-control range.",
        })
    return constraints[:3]


def _dedupe_section_lists(section: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(section)
    seen: set[str] = set()
    for field in _LIST_FIELDS:
        retained: list[str] = []
        for text in _texts(output.get(field)):
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            retained.append(text)
        output[field] = retained
    return output


def _sensitivity(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for row in rows:
        score = int(row["score"])
        weight = int(row["weight"])
        output.append({
            **row,
            "lift_to_80": round(max(0, 80 - score) * weight / 100, 2),
            "lift_to_90": round(max(0, 90 - score) * weight / 100, 2),
            "weighted_gap": round((100 - score) * weight / 100, 2),
        })
    return output


def harden_mid_report_payload(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    output["sections"] = [
        _dedupe_section_lists(item)
        for item in _list(output.get("sections"))
        if isinstance(item, dict)
    ]

    rows = _canonical_rows(output)
    score = _safe_canonical_score(output)
    complete = len(rows) == len(_WEIGHTS) and sum(int(row["weight"]) for row in rows) == 100
    decision = _dict(output.get("decision_summary"))
    integrity = _dict(output.get("score_integrity"))
    source_integrity = {
        "score_match": integrity.get("score_match"),
        "calculated_score": integrity.get("calculated_score"),
        "reported_score": integrity.get("reported_score"),
        "final_report_score": integrity.get("final_report_score"),
    }

    if score is not None:
        output["technical_score"] = score
        decision["technical_score"] = score
        integrity.update({
            "calculated_score": score,
            "reported_score": score,
            "final_report_score": score,
            "score_match": complete,
        })
    if rows:
        integrity["weighted_rows"] = rows
        output["score_sensitivity"] = _sensitivity(rows)

    integrity.update({
        "canonical_scorecard_complete": complete,
        "canonical_weight_total": sum(int(row["weight"]) for row in rows),
        "canonical_row_count": len(rows),
        "source_score_integrity": source_integrity,
        "score_reconciled": score is not None and any(
            _score(source_integrity.get(key)) not in {None, score}
            for key in ("calculated_score", "reported_score", "final_report_score")
        ),
    })
    decision["primary_score_constraints"] = _safe_primary_constraints(output)
    output["decision_summary"] = decision
    output["score_integrity"] = integrity
    output["mid_report_hardening"] = {
        "version": MID_REPORT_V5_HARDENING_VERSION,
        "canonical_scorecard_complete": complete,
        "duplicate_evidence_removed": True,
        "request_time_global_patch_used": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return output


def _install_stable_heading_aliases() -> None:
    from nico import report_flowable_safety as flowable_module

    if getattr(flowable_module, _PARAGRAPH_PATCH_MARKER, False):
        return
    original_paragraph = flowable_module._paragraph
    replacements = {
        "Priority controls": "Primary score constraints",
        "Weighted technical scorecard": "Weighted Technical Scorecard",
        "Repair Plan and Human-Context Requests": "Prioritized Repair Intelligence and Human-Context Modules",
        "Review Exceptions and Integrity": "Review by Exception and Integrity",
    }

    def paragraph_with_stable_alias(value: Any, *args: Any, **kwargs: Any):
        return original_paragraph(replacements.get(str(value), value), *args, **kwargs)

    flowable_module._paragraph = paragraph_with_stable_alias
    setattr(flowable_module, _PARAGRAPH_PATCH_MARKER, True)


def install_mid_report_v5_hardening() -> dict[str, Any]:
    from nico import mid_assessment_report as report_module
    from nico import mid_report_professional_v5 as v5_module

    if getattr(report_module, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": MID_REPORT_V5_HARDENING_VERSION}

    _install_stable_heading_aliases()
    v5_module._canonical_score = _safe_canonical_score
    v5_module._primary_constraints = _safe_primary_constraints
    v5_module._section_limitations = _safe_section_limitations

    current_payload = report_module._report_payload

    def hardened_payload(record: dict[str, Any], packet: dict[str, Any], identity: dict[str, Any], generated_at: str) -> dict[str, Any]:
        return harden_mid_report_payload(current_payload(record, packet, identity, generated_at))

    report_module._report_payload = hardened_payload
    setattr(report_module, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": MID_REPORT_V5_HARDENING_VERSION,
        "canonical_fixed_weights_enforced": True,
        "zero_score_preserved": True,
        "duplicate_rows_rejected": True,
        "duplicate_evidence_removed": True,
        "stable_pdf_heading_aliases": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "MID_REPORT_V5_HARDENING_VERSION",
    "harden_mid_report_payload",
    "install_mid_report_v5_hardening",
]
