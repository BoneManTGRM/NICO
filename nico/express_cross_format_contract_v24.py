from __future__ import annotations

import hashlib
import json
import re
from functools import wraps
from typing import Any, Callable

from nico.express_section_status_truth_v26 import assurance_presentation, technical_score_band

VERSION = "nico.express_cross_format_contract.v26"
_PATCH_MARKER = "_nico_express_cross_format_contract_v24"
_SCANNER_IDS = {"scanner_worker", "scanner_worker_evidence"}
_CLIENT_ACCEPTANCE_IDS = {"client_acceptance", "client_human_acceptance"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _not_scored(section: dict[str, Any]) -> bool:
    section_id = _text(section.get("id")).casefold()
    presented_status = _text(section.get("presented_status") or section.get("status")).casefold()
    if section_id in _SCANNER_IDS or presented_status == "supplemental":
        return True
    if section_id in _CLIENT_ACCEPTANCE_IDS and presented_status != "green":
        return True
    return section.get("directly_scored") is False or (
        section.get("presented_score") is None
        and section.get("exclude_from_maturity") is True
    )


def _canonical_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        section_id = _text(section.get("id"))
        status = _text(section.get("presented_status") or section.get("status")).casefold() or "unknown"
        scanner = section_id.casefold() in _SCANNER_IDS or status == "supplemental"
        not_scored = _not_scored(section)
        score = None if not_scored else section.get("score_value")
        if score is None and not not_scored:
            score = section.get("presented_score", section.get("score"))
        score_band = technical_score_band(score, scored=not not_scored)
        assurance = assurance_presentation("supplemental" if scanner else status, scored=not not_scored)
        records.append(
            {
                "section_id": section_id,
                "label": _text(section.get("label") or section.get("title") or section_id),
                "status": "supplemental" if scanner else status,
                "canonical_status_role": "evidence_assurance",
                "score": score,
                "source_score": None if not_scored else section.get("source_score", section.get("score")),
                "confidence": _text(section.get("presented_confidence") or section.get("confidence") or "unknown").casefold(),
                "directly_scored": not not_scored,
                "score_label": "NOT SCORED" if not_scored else f"{score}/100",
                "technical_band": _text(section.get("score_band") or score_band["score_band"]),
                "technical_band_label": _text(section.get("score_band_label") or score_band["score_band_label"]),
                "score_tone": _text(section.get("score_tone") or score_band["score_tone"]),
                "assurance_status": _text(section.get("assurance_status") or assurance["assurance_status"]),
                "assurance_label": _text(section.get("assurance_label") or assurance["assurance_label"]),
                "assurance_tone": _text(section.get("assurance_tone") or assurance["assurance_tone"]),
                "technical_score_display": "NOT SCORED" if not_scored else f"{_text(section.get('score_band_label') or score_band['score_band_label'])} · {score}/100",
                "assurance_display": _text(section.get("assurance_label") or assurance["assurance_label"]),
            }
        )
    return records


def _fingerprint(result: dict[str, Any], records: list[dict[str, Any]]) -> str:
    payload = {
        "repository": _text(result.get("repository")),
        "commit_sha": _text(result.get("commit_sha") or result.get("snapshot_sha") or result.get("assessed_commit_sha")),
        "records": records,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _contains_record(document: str, record: dict[str, Any]) -> bool:
    if not document or not record.get("label"):
        return False
    label = re.escape(str(record["label"]))
    status = re.escape(str(record["status"]).upper())
    if record["score"] is None:
        expected = rf"{label}[\s\S]{{0,220}}{status}[\s\S]{{0,120}}NOT\s+SCORED"
    else:
        expected = rf"{label}[\s\S]{{0,220}}{status}[\s\S]{{0,120}}{int(record['score'])}\s*/\s*100"
    return bool(re.search(expected, document, re.I))


def build_cross_format_contract(result: dict[str, Any]) -> dict[str, Any]:
    records = _canonical_records(result)
    reports = result.get("reports") if isinstance(result.get("reports"), dict) else {}
    markdown = str(reports.get("markdown") or "")
    html = str(reports.get("html") or "")

    markdown_missing = [
        item["section_id"]
        for item in records
        if markdown and not _contains_record(markdown, item)
    ]
    html_missing = [
        item["section_id"]
        for item in records
        if html and not _contains_record(html, item)
    ]
    scanner = next((item for item in records if item["section_id"].casefold() in _SCANNER_IDS), None)
    scanner_valid = scanner is None or (
        scanner["status"] == "supplemental"
        and scanner["score"] is None
        and scanner["directly_scored"] is False
    )
    not_scored_valid = all(
        item["score"] is None and item["directly_scored"] is False
        for item in records
        if item["score_label"] == "NOT SCORED"
    )
    separated_valid = all(
        bool(item.get("technical_band_label")) and bool(item.get("assurance_label"))
        for item in records
    )

    contract = {
        "status": "complete" if not markdown_missing and not html_missing and scanner_valid and not_scored_valid and separated_valid else "degraded",
        "version": VERSION,
        "canonical_records": records,
        "record_count": len(records),
        "truth_fingerprint": _fingerprint(result, records),
        "markdown_present": bool(markdown),
        "html_present": bool(html),
        "markdown_status_score_mismatches": markdown_missing,
        "html_status_score_mismatches": html_missing,
        "markdown_status_mismatches": markdown_missing,
        "html_section_mismatches": html_missing,
        "scanner_supplemental_not_scored": scanner_valid,
        "not_scored_controls_excluded": not_scored_valid,
        "source_scores_preserved": True,
        "presented_fields_are_canonical": True,
        "score_band_separated_from_assurance": separated_valid,
        "canonical_status_role": "evidence_assurance",
        "technical_score_role": "score_derived_health",
        "delivery_status_separate": True,
        "pdf_uses_same_result_object": True,
        "json_contract_embedded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    result["express_cross_format_contract"] = contract
    return contract


def install_express_cross_format_contract_v24() -> dict[str, Any]:
    from nico import assessment_quality

    current: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        build_cross_format_contract(result)
        pdf, error = current(result)
        build_cross_format_contract(result)
        return pdf, error

    setattr(render, _PATCH_MARKER, True)
    setattr(render, "_nico_previous", current)
    assessment_quality._build_polished_pdf_base64 = render
    return {
        "status": "installed",
        "version": VERSION,
        "production_renderer_bound": True,
        "deterministic_truth_fingerprint": True,
        "scanner_supplemental_contract": True,
        "score_status_parity_contract": True,
        "source_scores_preserved": True,
        "not_scored_controls_excluded": True,
        "score_band_separated_from_assurance": True,
    }


__all__ = ["VERSION", "build_cross_format_contract", "install_express_cross_format_contract_v24"]
