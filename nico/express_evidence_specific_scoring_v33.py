from __future__ import annotations

import re
from dataclasses import dataclass
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_evidence_specific_scoring.v33.1"
_PATCH_MARKER = "_nico_express_evidence_specific_scoring_v33"
_NOT_SCORED_IDS = {
    "scanner_worker",
    "scanner_worker_evidence",
    "client_acceptance",
    "client_human_acceptance",
}


@dataclass(frozen=True)
class EvidenceDeduction:
    rule_id: str
    reason: str
    points: int
    evidence: str


@dataclass(frozen=True)
class EvidenceScoreRecord:
    section_id: str
    label: str
    source_score: int
    presented_score: int
    status: str
    deductions: tuple[tuple[str, int], ...]
    deduction_details: tuple[EvidenceDeduction, ...]
    confidence: str
    rationale: str


def _text(value: Any, limit: int = 1000) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= limit else text[: limit - 3].rstrip() + "..."


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _unique(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in _list(values):
        text = _text(value)
        key = text.casefold()
        if text and key not in seen:
            seen.add(key)
            output.append(text)
    return output


def _section_id(section: dict[str, Any]) -> str:
    return _text(section.get("id"), 80).casefold()


def _client_acceptance_approved(section: dict[str, Any]) -> bool:
    status = _text(section.get("status") or section.get("acceptance_status")).casefold()
    score = section.get("source_score", section.get("score"))
    return bool(section.get("approved") or section.get("accepted") or status in {"approved", "accepted", "green", "verified"}) and isinstance(score, (int, float)) and score > 0


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _section_id(section)
    if section_id in {"scanner_worker", "scanner_worker_evidence"}:
        return True
    if section_id in {"client_acceptance", "client_human_acceptance"}:
        return not _client_acceptance_approved(section)
    return section.get("directly_scored") is False and section.get("presented_score", section.get("score")) is None


def _first_matching(values: list[str], terms: tuple[str, ...]) -> str:
    for value in values:
        lowered = value.casefold()
        if any(term in lowered for term in terms):
            return value
    return ""


def _add_deduction(
    deductions: list[EvidenceDeduction],
    *,
    rule_id: str,
    reason: str,
    points: int,
    evidence: str,
) -> None:
    if not evidence or any(item.rule_id == rule_id for item in deductions):
        return
    deductions.append(
        EvidenceDeduction(
            rule_id=rule_id,
            reason=reason,
            points=max(0, int(points)),
            evidence=_text(evidence, 360),
        )
    )


def _deductions(section: dict[str, Any]) -> tuple[EvidenceDeduction, ...]:
    findings = _unique(section.get("findings"))
    unavailable = _unique(section.get("unavailable"))
    limitations = _unique(section.get("limitations"))
    evidence = _unique(section.get("evidence"))
    decision_text = [*findings, *unavailable, *limitations]
    all_text = [*decision_text, *evidence]
    deductions: list[EvidenceDeduction] = []

    timeout = _first_matching(all_text, ("timeout", "timed out", "timed_out"))
    _add_deduction(
        deductions,
        rule_id="ANALYZER_TIMEOUT",
        reason="A required analyzer did not complete within its execution boundary.",
        points=8,
        evidence=timeout,
    )

    failure = _first_matching(
        all_text,
        (
            "status=failed",
            "status failed",
            "ended with status failed",
            " returned failed",
            "reported failure",
            " failed during",
        ),
    )
    _add_deduction(
        deductions,
        rule_id="ANALYZER_FAILURE",
        reason="A required analyzer reported a failed execution state.",
        points=10,
        evidence=failure,
    )

    unavailable_evidence = _first_matching(
        [*unavailable, *limitations],
        ("unavailable", "missing required", "not available", "incomplete", "access limitation"),
    )
    _add_deduction(
        deductions,
        rule_id="EVIDENCE_UNAVAILABLE",
        reason="Material evidence needed to close the control is unavailable or limited.",
        points=min(8, 4 + max(1, len(unavailable) + len(limitations))),
        evidence=unavailable_evidence,
    )

    triage = _first_matching(
        [*findings, *evidence],
        (
            "requires human triage",
            "requiring human triage",
            "requires review",
            "requiring immediate human review",
            "human disposition",
        ),
    )
    _add_deduction(
        deductions,
        rule_id="HUMAN_TRIAGE_REQUIRED",
        reason="Unresolved analyzer candidates require an authorized human disposition.",
        points=min(10, 4 + max(1, len(findings))),
        evidence=triage,
    )

    if findings and not triage:
        _add_deduction(
            deductions,
            rule_id="OPEN_FINDING",
            reason="One or more retained findings remain unresolved.",
            points=min(8, 2 + len(findings)),
            evidence=findings[0],
        )

    return tuple(deductions)


def _source_score(section: dict[str, Any]) -> int:
    raw = section.get("source_score", section.get("score"))
    try:
        return max(0, min(100, int(raw or 0)))
    except (TypeError, ValueError):
        return 0


def evidence_score_record(section: dict[str, Any]) -> EvidenceScoreRecord:
    source = _source_score(section)
    details = _deductions(section)
    total = sum(item.points for item in details)
    presented = max(0, source - total)
    unresolved = bool(details)
    status = "green" if presented >= 75 and not unresolved else "yellow" if presented >= 45 else "red"
    confidence = "high" if not unresolved else "review-limited"
    rationale = (
        "No evidence-specific deduction rule was triggered for this control."
        if not details
        else "; ".join(f"{item.rule_id} (-{item.points}): {item.reason}" for item in details)
    )
    compatibility = tuple(
        (
            f"{item.rule_id} — {item.reason} Evidence: {item.evidence}",
            item.points,
        )
        for item in details
    )
    return EvidenceScoreRecord(
        section_id=_text(section.get("id"), 80),
        label=_text(section.get("label") or section.get("title") or section.get("id"), 160),
        source_score=source,
        presented_score=presented,
        status=status,
        deductions=compatibility,
        deduction_details=details,
        confidence=confidence,
        rationale=rationale,
    )


def _deduction_payload(record: EvidenceScoreRecord) -> list[dict[str, Any]]:
    return [
        {
            "rule_id": item.rule_id,
            "reason": item.reason,
            "points": item.points,
            "evidence": item.evidence,
        }
        for item in record.deduction_details
    ]


def _apply_record(section: dict[str, Any], record: EvidenceScoreRecord) -> None:
    # Source scoring remains untouched so existing evidence and finalization logic
    # keep their original contract. Client-facing formats consume only the
    # explicit presented_* fields below.
    section["source_score"] = record.source_score
    section["presented_score"] = record.presented_score
    section["presented_status"] = record.status
    section["presented_confidence"] = record.confidence
    section["display_status"] = f"{record.status.upper()} · {record.presented_score}/100"
    section["directly_scored"] = True
    section["score_deductions"] = _deduction_payload(record)
    section["score_rationale"] = record.rationale
    section["score_treatment"] = "source_preserved_evidence_specific_presentation"


def _normalize_not_scored(section: dict[str, Any]) -> None:
    raw_score = section.get("source_score", section.get("score"))
    if isinstance(raw_score, (int, float)):
        section.setdefault("diagnostic_source_score", raw_score)
    section["presented_score"] = None
    section["presented_status"] = "supplemental" if _section_id(section) in {"scanner_worker", "scanner_worker_evidence"} else "gray"
    section["presented_confidence"] = "review-limited"
    section["directly_scored"] = False
    section["exclude_from_maturity"] = True
    section["score_label"] = "NOT SCORED"
    section["score_deductions"] = []
    section["score_rationale"] = "This control is excluded from automated maturity scoring."
    section["display_status"] = f"{section['presented_status'].upper()} · NOT SCORED"


def reconcile_express_scores(result: dict[str, Any]) -> tuple[list[EvidenceScoreRecord], int]:
    records: list[EvidenceScoreRecord] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if _not_scored(section):
            _normalize_not_scored(section)
            continue
        record = evidence_score_record(section)
        _apply_record(section, record)
        records.append(record)

    scored = [item.presented_score for item in records]
    overall = round(sum(scored) / len(scored)) if scored else 0
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source_maturity = maturity.get("source_score", maturity.get("score"))
    if isinstance(maturity, dict):
        maturity["source_score"] = source_maturity
        maturity["presented_score"] = overall
        maturity["score_treatment"] = "source_score_preserved_with_evidence_adjusted_presented_score"
    result["evidence_adjusted_score"] = overall
    result["express_score_transparency"] = {
        "version": VERSION,
        "overall_presented_score": overall,
        "source_maturity_score": source_maturity,
        "method": "Each section preserves its source score and subtracts only listed evidence-specific deductions. Unresolved evidence constrains presented status without mutating source scoring.",
        "blanket_score_cap_applied": False,
        "records": [
            {
                "section_id": item.section_id,
                "label": item.label,
                "source_score": item.source_score,
                "presented_score": item.presented_score,
                "status": item.status,
                "confidence": item.confidence,
                "deductions": _deduction_payload(item),
                "rationale": item.rationale,
            }
            for item in records
        ],
        "source_scores_preserved": True,
        "not_scored_controls_excluded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return records, overall


def _rewrite_markdown(markdown: str, result: dict[str, Any]) -> str:
    output = markdown
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = _text(section.get("label") or section.get("title"))
        if not label:
            continue
        status = _text(section.get("presented_status") or section.get("status") or "unknown").upper()
        score = section.get("presented_score")
        value = f"{status} (NOT SCORED)" if score is None else f"{status} ({int(score)}/100)"
        output = re.sub(
            rf"(###\s+{re.escape(label)}\s+—\s+)[A-Z]+\s*\((?:None|0|\d+|NOT SCORED)(?:/100)?\)",
            rf"\1{value}",
            output,
            flags=re.I,
        )
    return output


def _rewrite_html(html: str, result: dict[str, Any]) -> str:
    output = html
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        label = _text(section.get("label") or section.get("title"))
        if not label:
            continue
        status = _text(section.get("presented_status") or section.get("status") or "unknown").upper()
        score = section.get("presented_score")
        value = f"{status} (NOT SCORED)" if score is None else f"{status} ({int(score)}/100)"
        output = re.sub(
            rf"({re.escape(label)}\s*[—-]\s*)[A-Z]+\s*\((?:None|0|\d+|NOT SCORED)(?:/100)?\)",
            rf"\1{value}",
            output,
            flags=re.I,
        )
    return output


def rewrite_cross_format_scores(result: dict[str, Any]) -> None:
    reports = result.get("reports")
    if not isinstance(reports, dict):
        return
    if isinstance(reports.get("markdown"), str):
        reports["markdown"] = _rewrite_markdown(reports["markdown"], result)
    if isinstance(reports.get("html"), str):
        reports["html"] = _rewrite_html(reports["html"], result)


def install_express_evidence_specific_scoring_v33() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_report_premium_v14 as premium

    premium.reconcile_express_scores = reconcile_express_scores
    premium.VERSION = VERSION

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        reconcile_express_scores(result)
        rewrite_cross_format_scores(result)
        payload = current(result)
        reconcile_express_scores(result)
        rewrite_cross_format_scores(result)
        result["express_evidence_specific_scoring"] = {
            "status": "complete",
            "version": VERSION,
            "blanket_score_cap_removed": True,
            "deductions_include_rule_and_evidence": True,
            "source_scores_preserved": True,
            "presented_score_fields_canonical": True,
            "markdown_score_parity": True,
            "html_score_parity": True,
            "pdf_score_parity": True,
            "not_scored_controls_excluded": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return payload

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "blanket_score_cap_removed": True,
        "source_scores_preserved": True,
        "cross_format_parity_bound": True,
        "human_review_required": True,
    }


__all__ = [
    "EvidenceDeduction",
    "EvidenceScoreRecord",
    "VERSION",
    "evidence_score_record",
    "install_express_evidence_specific_scoring_v33",
    "reconcile_express_scores",
    "rewrite_cross_format_scores",
]
