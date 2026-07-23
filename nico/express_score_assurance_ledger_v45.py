from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_score_assurance_ledger.v45"
_PATCH_MARKER = "_nico_express_score_assurance_ledger_v45"
_SCANNER_SECTION_IDS = {"scanner_worker_evidence", "scanner_evidence"}
_ACCEPTANCE_SECTION_IDS = {"client_acceptance", "client_human_acceptance"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _number(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return max(0, min(100, number))


def _band(score: int) -> tuple[str, str, str]:
    if score >= 90:
        return "exceptional", "EXCEPTIONAL", "green"
    if score >= 80:
        return "strong", "STRONG", "green"
    if score >= 70:
        return "moderate", "MODERATE", "yellow"
    if score >= 55:
        return "weak", "WEAK", "red"
    return "critical", "CRITICAL", "red"


def _assurance(section: dict[str, Any], previous_status: str) -> tuple[str, str, str]:
    raw = _text(
        section.get("assurance_status")
        or section.get("presented_confidence")
        or section.get("confidence")
        or previous_status
    ).casefold().replace("-", "_").replace(" ", "_")
    if raw in {"verified", "complete", "completed", "green", "strong", "exceptional"}:
        return "verified", "VERIFIED", "green"
    if raw in {"unavailable", "not_available"}:
        return "unavailable", "UNAVAILABLE", "gray"
    if raw in {"incomplete", "failed", "blocked", "error", "timed_out", "timeout"}:
        return "incomplete", "INCOMPLETE", "red"
    return "review_limited", "REVIEW LIMITED", "yellow"


def _risk(section: dict[str, Any]) -> tuple[str, str, str]:
    findings = [_text(item) for item in section.get("findings") or [] if _text(item)]
    if not findings:
        return "no_material_finding", "NO MATERIAL FINDING", "green"
    combined = " ".join(findings).casefold()
    if any(token in combined for token in ("confirmed critical", "confirmed high", "verified exposure", "material finding", "verified vulnerability")):
        return "material_findings", "MATERIAL FINDINGS", "red"
    if any(token in combined for token in ("candidate", "triage", "unverified", "review", "timeout", "failed", "unavailable")):
        return "human_triage_required", "HUMAN TRIAGE REQUIRED", "yellow"
    return "advisory_findings", "ADVISORY FINDINGS", "yellow"


def _structured_scanner_records(value: Any, *, depth: int = 0) -> list[dict[str, Any]]:
    if depth > 5:
        return []
    if isinstance(value, list):
        output: list[dict[str, Any]] = []
        for item in value:
            output.extend(_structured_scanner_records(item, depth=depth + 1))
        return output
    if not isinstance(value, dict):
        return []
    output: list[dict[str, Any]] = []
    tool = _text(value.get("tool") or value.get("scanner") or value.get("name")).casefold()
    status = _text(value.get("status") or value.get("lifecycle_status")).casefold()
    if tool and status:
        output.append(value)
    for key, item in value.items():
        if key in {"evidence", "findings", "unavailable", "source_statements"}:
            continue
        if isinstance(item, (dict, list)):
            output.extend(_structured_scanner_records(item, depth=depth + 1))
    return output


def _lifecycle(disposition: dict[str, Any]) -> str:
    status = _text(disposition.get("status")).casefold()
    sources = " ".join(_text(item).casefold() for item in disposition.get("source_statements") or [])
    if status == "timeout":
        return "timed_out"
    if status == "unavailable" and ("no eslint configuration" in sources or "not configured" in sources):
        return "not_configured"
    if status in {"completed_findings", "completed_triaged"}:
        return "completed_with_candidates"
    return status or "unknown"


def _candidate_count(disposition: dict[str, Any], structured: dict[str, Any]) -> int:
    values = [
        disposition.get("findings"),
        structured.get("raw_candidate_count"),
        structured.get("findings_count"),
        structured.get("candidate_count"),
    ]
    counts = [int(value) for value in values if isinstance(value, int) and not isinstance(value, bool)]
    return max(counts) if counts else 0


def _build_scanner_ledger(result: dict[str, Any], section: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    dispositions = section.get("scanner_dispositions")
    if not isinstance(dispositions, dict):
        dispositions = result.get("scanner_dispositions") if isinstance(result.get("scanner_dispositions"), dict) else {}

    structured_records = _structured_scanner_records(
        {
            "scanner_worker": result.get("scanner_worker"),
            "scanner_evidence": result.get("scanner_evidence"),
            "scanner_worker_evidence": result.get("scanner_worker_evidence"),
            "scanner_artifact": result.get("scanner_artifact"),
            "worker_artifact": result.get("worker_artifact"),
        }
    )
    structured_by_tool: dict[str, dict[str, Any]] = {}
    for record in structured_records:
        tool = _text(record.get("tool") or record.get("scanner") or record.get("name")).casefold()
        if tool:
            structured_by_tool[tool] = record

    tool_names = sorted(set(dispositions) | set(structured_by_tool))
    ledger: list[dict[str, Any]] = []
    counts = {
        "total": len(tool_names),
        "completed": 0,
        "failed": 0,
        "timed_out": 0,
        "not_configured": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    for tool in tool_names:
        disposition = dispositions.get(tool) if isinstance(dispositions.get(tool), dict) else {}
        structured = structured_by_tool.get(tool, {})
        lifecycle = _lifecycle(disposition) if disposition else _text(structured.get("status")).casefold() or "unknown"
        if lifecycle.startswith("completed"):
            counts["completed"] += 1
        elif lifecycle in counts:
            counts[lifecycle] += 1
        else:
            counts["unknown"] += 1

        raw_candidates = _candidate_count(disposition, structured)
        clean_eligible = lifecycle in {"completed_clean", "completed_triaged"} and raw_candidates == 0
        source_statements = [
            _text(item) for item in disposition.get("source_statements") or [] if _text(item)
        ]
        ledger.append(
            {
                "tool": tool,
                "requested": True,
                "in_scope": lifecycle != "not_configured",
                "lifecycle_result": lifecycle,
                "command": _text(structured.get("command")),
                "version": _text(structured.get("version") or structured.get("tool_version")),
                "run_id": _text(structured.get("run_id") or result.get("run_id")),
                "commit_sha": _text(structured.get("commit_sha") or result.get("commit_sha")),
                "raw_candidate_count": raw_candidates,
                "deduplicated_candidate_count": int(structured.get("deduplicated_candidate_count") or raw_candidates),
                "triaged_count": int(structured.get("triaged_count") or 0),
                "confirmed_count": int(structured.get("confirmed_count") or 0),
                "false_positive_count": int(structured.get("false_positive_count") or 0),
                "clean_claim_eligible": clean_eligible,
                "artifact_digest": _text(structured.get("artifact_digest") or structured.get("sha256") or structured.get("digest")),
                "parser_status": _text(structured.get("parser_status") or ("parsed" if source_statements else "not_recorded")),
                "source_statement_count": len(source_statements),
            }
        )
    return ledger, counts


def _normalize_scanner_section(result: dict[str, Any], section: dict[str, Any]) -> None:
    ledger, counts = _build_scanner_ledger(result, section)
    review_items = []
    for field in ("findings", "unavailable"):
        for item in section.get(field) or []:
            text = _text(item)
            if text and text not in review_items:
                review_items.append(text)

    for key in ("score", "source_score", "presented_score", "presented", "score_value"):
        section[key] = None
    section.update(
        {
            "directly_scored": False,
            "exclude_from_maturity": True,
            "included_in_maturity": False,
            "technical_section": False,
            "section_group": "assurance_ledger",
            "status": "supplemental",
            "presented_status": "supplemental",
            "display_status": "SUPPLEMENTAL · NOT SCORED",
            "technical_score_display": "SUPPLEMENTAL · NOT SCORED",
            "score_kind": "not_scored",
            "assurance_status": "review_limited" if any(counts[key] for key in ("failed", "timed_out", "unavailable", "unknown")) else "verified",
            "assurance_label": "REVIEW LIMITED" if any(counts[key] for key in ("failed", "timed_out", "unavailable", "unknown")) else "VERIFIED",
            "assurance_tone": "yellow" if any(counts[key] for key in ("failed", "timed_out", "unavailable", "unknown")) else "green",
            "scanner_execution_coverage_percent": round(100 * counts["completed"] / counts["total"]) if counts["total"] else 0,
            "scanner_execution_denominator": counts["total"],
            "scanner_execution_summary": counts,
            "analyzer_ledger": ledger,
            "review_items": review_items,
            "findings": [],
            "summary": (
                f"Analyzer assurance ledger: {counts['completed']} completed · {counts['failed']} failed · "
                f"{counts['timed_out']} timed out · {counts['not_configured']} not configured · "
                f"{counts['unavailable']} unavailable · {counts['unknown']} unknown; "
                f"{counts['total']} observed analyzers. This control is not scored and is excluded from technical maturity."
            ),
            "score_treatment": "structured_scanner_assurance_ledger_not_scored_v45",
        }
    )
    result["scanner_assurance_ledger"] = {
        "version": VERSION,
        "counts": counts,
        "analyzers": ledger,
        "technical_maturity_effect": "excluded_to_prevent_double_counting",
    }


def _normalize_acceptance_section(result: dict[str, Any], section: dict[str, Any]) -> None:
    review_items = []
    for field in ("findings", "unavailable"):
        for item in section.get(field) or []:
            text = _text(item)
            if text and text not in review_items:
                review_items.append(text)
    for key in ("score", "source_score", "presented_score", "presented", "score_value"):
        section[key] = None
    section.update(
        {
            "label": "Review and delivery",
            "technical_section": False,
            "section_group": "review_delivery",
            "directly_scored": False,
            "exclude_from_maturity": True,
            "included_in_maturity": False,
            "status": "human_review_pending",
            "presented_status": "human_review_pending",
            "display_status": "PENDING HUMAN APPROVAL · NOT SCORED",
            "technical_score_display": "NOT SCORED",
            "assurance_status": "pending_human_approval",
            "assurance_label": "PENDING HUMAN APPROVAL",
            "assurance_tone": "gray",
            "risk_disposition": "delivery_blocked_pending_approval",
            "risk_label": "DELIVERY BLOCKED PENDING APPROVAL",
            "risk_tone": "gray",
            "review_items": review_items,
            "findings": [],
            "unavailable": [],
            "summary": "The final report is complete. Delivery remains blocked until an authorized human approves the exact immutable report and evidence package.",
        }
    )
    result["review_and_delivery"] = {
        "status": "pending_human_approval",
        "client_delivery_allowed": False,
        "human_review_required": True,
        "section": section,
    }


def apply_express_score_assurance_ledger_v45(result: dict[str, Any]) -> dict[str, Any]:
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id")).casefold()
        if section_id in _SCANNER_SECTION_IDS:
            _normalize_scanner_section(result, section)
            continue
        if section_id in _ACCEPTANCE_SECTION_IDS:
            _normalize_acceptance_section(result, section)
            continue

        score = _number(section.get("presented_score", section.get("score")))
        if score is None or section.get("exclude_from_maturity") is True:
            continue
        previous_status = _text(section.get("presented_status") or section.get("status"))
        band_key, band_label, band_tone = _band(score)
        assurance_key, assurance_label, assurance_tone = _assurance(section, previous_status)
        risk_key, risk_label, risk_tone = _risk(section)
        section.update(
            {
                "technical_band": band_key,
                "technical_band_label": band_label,
                "technical_tone": band_tone,
                "technical_score_display": f"{band_label} · {score}/100",
                "status": band_key,
                "presented_status": band_key,
                "display_status": f"{band_label} · {score}/100",
                "assurance_status": assurance_key,
                "assurance_label": assurance_label,
                "assurance_tone": assurance_tone,
                "risk_disposition": risk_key,
                "risk_label": risk_label,
                "risk_tone": risk_tone,
                "status_before_dimension_split": previous_status,
                "score_assurance_risk_separated": True,
            }
        )

    result["score_assurance_risk_contract"] = {
        "status": "complete",
        "version": VERSION,
        "technical_score_controls_color": True,
        "assurance_is_independent": True,
        "risk_is_independent": True,
        "scanner_ledger_not_scored": True,
        "acceptance_outside_technical_maturity": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def install_express_score_assurance_ledger_v45() -> dict[str, Any]:
    from nico import express_truth_calibration_v36 as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target.calibrate_express_truth
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def calibrate(result: dict[str, Any]) -> dict[str, Any]:
        return apply_express_score_assurance_ledger_v45(current(result))

    setattr(calibrate, _PATCH_MARKER, True)
    setattr(calibrate, "_nico_previous", current)
    target.calibrate_express_truth = calibrate
    return {
        "status": "installed",
        "version": VERSION,
        "scanner_ledger_not_scored": True,
        "technical_score_assurance_risk_separated": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "apply_express_score_assurance_ledger_v45",
    "install_express_score_assurance_ledger_v45",
]
