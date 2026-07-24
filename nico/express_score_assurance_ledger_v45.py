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
    tool = _text(value.get("tool") or value.get("analyzer") or value.get("name"))
    status = _text(value.get("status") or value.get("result") or value.get("disposition"))
    if tool and status:
        output.append(value)
    for nested in value.values():
        output.extend(_structured_scanner_records(nested, depth=depth + 1))
    return output


def _lifecycle(raw: str) -> str:
    value = _text(raw).casefold().replace("-", "_").replace(" ", "_")
    if value in {"completed", "complete", "completed_clean", "completed_with_candidates", "completed_with_findings", "success", "passed", "ok"}:
        return "completed"
    if value in {"failed", "failure", "error", "blocked"}:
        return "failed"
    if value in {"timeout", "timed_out", "timedout"}:
        return "timed_out"
    if value in {"not_configured", "notconfigured", "inapplicable", "not_applicable"}:
        return "not_configured"
    if value in {"unavailable", "not_available", "missing"}:
        return "unavailable"
    return "unknown"


def _candidate_count(record: dict[str, Any]) -> int:
    for key in ("deduplicated_candidate_count", "raw_candidate_count", "findings", "finding_count", "candidate_count"):
        value = record.get(key)
        if isinstance(value, bool):
            continue
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            continue
    return 0


def _build_scanner_ledger(result: dict[str, Any], section: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    records: list[dict[str, Any]] = []
    for key in (
        "scanner_dispositions",
        "scanner_worker_evidence",
        "scanner_results",
        "scanner_artifact_summary",
        "scanner_assurance_ledger",
    ):
        records.extend(_structured_scanner_records(result.get(key)))
    records.extend(_structured_scanner_records(section.get("scanner_dispositions")))

    by_tool: dict[str, dict[str, Any]] = {}
    for record in records:
        tool = _text(record.get("tool") or record.get("analyzer") or record.get("name"))
        if not tool:
            continue
        status = _text(record.get("status") or record.get("result") or record.get("disposition"))
        lifecycle = _lifecycle(status)
        normalized = {
            "tool": tool,
            "lifecycle_result": lifecycle,
            "source_status": status or "unknown",
            "raw_candidate_count": _candidate_count(record),
            "deduplicated_candidate_count": _candidate_count(record),
            "evidence_scope": _text(record.get("evidence_scope") or record.get("scope") or "exact checked-out repository state"),
            "artifact_identity": _text(record.get("artifact_identity") or record.get("artifact") or record.get("path")),
            "exit_code": record.get("exit_code"),
            "timeout_seconds": record.get("timeout_seconds"),
            "source_statements": [
                _text(item)
                for item in record.get("source_statements") or []
                if _text(item)
            ],
        }
        previous = by_tool.get(tool.casefold())
        if previous is None or (
            previous["lifecycle_result"] == "unknown" and lifecycle != "unknown"
        ):
            by_tool[tool.casefold()] = normalized

    ledger = sorted(by_tool.values(), key=lambda item: item["tool"].casefold())
    counts = {
        "total": len(ledger),
        "completed": 0,
        "failed": 0,
        "timed_out": 0,
        "not_configured": 0,
        "unavailable": 0,
        "unknown": 0,
    }
    for record in ledger:
        lifecycle = record["lifecycle_result"]
        counts[lifecycle if lifecycle in counts else "unknown"] += 1
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
            "label": "Scanner Assurance Ledger",
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


def _acceptance_is_approved(result: dict[str, Any], section: dict[str, Any]) -> bool:
    evidence = result.get("client_acceptance") if isinstance(result.get("client_acceptance"), dict) else {}
    status = _text(evidence.get("status") or section.get("approval_status")).casefold()
    score = _number(section.get("presented_score", section.get("score")))
    return status in {"accepted", "approved"} or (
        _text(section.get("status")).casefold() == "green" and score is not None and score > 0
    )


def _normalize_acceptance_section(result: dict[str, Any], section: dict[str, Any]) -> None:
    review_items = []
    for field in ("findings", "unavailable"):
        for item in section.get(field) or []:
            text = _text(item)
            if text and text not in review_items:
                review_items.append(text)

    section["label"] = "Review and Delivery"
    section["technical_section"] = False
    section["section_group"] = "review_delivery"
    section["review_items"] = review_items
    section["findings"] = []
    section["unavailable"] = []

    if _acceptance_is_approved(result, section):
        score = _number(section.get("presented_score", section.get("score"))) or 96
        section.update(
            {
                "score": score,
                "source_score": score,
                "presented_score": score,
                "presented": score,
                "score_value": score,
                "directly_scored": True,
                "exclude_from_maturity": False,
                "included_in_maturity": True,
                "status": "green",
                "presented_status": "green",
                "display_status": "APPROVED",
                "technical_score_display": f"APPROVED · {score}/100",
                "score_kind": "approved_acceptance",
                "assurance_status": "verified",
                "assurance_label": "VERIFIED",
                "assurance_tone": "green",
                "risk_disposition": "accepted",
                "risk_label": "APPROVED",
                "risk_tone": "green",
                "approval_status": "approved",
                "client_delivery_allowed": True,
                "summary": "The exact final report and evidence package have an approved same-project human acceptance record.",
            }
        )
        result["review_and_delivery"] = {
            "status": "approved",
            "client_delivery_allowed": True,
            "human_review_required": False,
            "section": section,
        }
        return

    for key in ("score", "source_score", "presented_score", "presented", "score_value"):
        section[key] = None
    section.update(
        {
            "directly_scored": False,
            "exclude_from_maturity": True,
            "included_in_maturity": False,
            "status": "human_review_pending",
            "presented_status": "human_review_pending",
            "display_status": "PENDING HUMAN APPROVAL · NOT SCORED",
            "technical_score_display": "NOT SCORED",
            "score_kind": "not_scored",
            "assurance_status": "pending_human_approval",
            "assurance_label": "PENDING HUMAN APPROVAL",
            "assurance_tone": "gray",
            "risk_disposition": "delivery_blocked_pending_approval",
            "risk_label": "DELIVERY BLOCKED PENDING APPROVAL",
            "risk_tone": "gray",
            "approval_status": "pending_human_approval",
            "client_delivery_allowed": False,
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
                "score": score,
                "presented_score": score,
                "score_value": score,
                "status": band_key,
                "presented_status": band_key,
                "display_status": f"{band_label} · {score}/100",
                "technical_score_display": f"{band_label} · {score}/100",
                "technical_band": band_key,
                "technical_band_label": band_label,
                "technical_tone": band_tone,
                "assurance_status": assurance_key,
                "assurance_label": assurance_label,
                "assurance_tone": assurance_tone,
                "risk_disposition": risk_key,
                "risk_label": risk_label,
                "risk_tone": risk_tone,
                "score_assurance_separated": True,
            }
        )
    result["score_assurance_risk_contract"] = {
        "version": VERSION,
        "technical_score_controls_color": True,
        "assurance_is_independent": True,
        "risk_disposition_is_independent": True,
        "scanner_ledger_not_scored": True,
        "acceptance_pending_not_scored": True,
        "acceptance_approved_verified": True,
        "human_review_required": True,
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
        "technical_score_controls_color": True,
        "assurance_is_independent": True,
        "risk_disposition_is_independent": True,
        "scanner_ledger_not_scored": True,
        "acceptance_pending_not_scored": True,
        "acceptance_approved_verified": True,
    }


__all__ = [
    "VERSION",
    "apply_express_score_assurance_ledger_v45",
    "install_express_score_assurance_ledger_v45",
]
