from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.canonical-section-status.v1"
_SCORE_BANDS = {"STRONG", "MODERATE", "WEAK", "CRITICAL"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _numeric(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return max(0, min(100, int(round(value))))


def score_band(value: Any) -> str:
    score = _numeric(value)
    if score is None:
        return "NOT_SCORED"
    if score >= 85:
        return "STRONG"
    if score >= 70:
        return "MODERATE"
    if score >= 50:
        return "WEAK"
    return "CRITICAL"


def normalize_scored_sections(assessment: Mapping[str, Any]) -> dict[str, Any]:
    """Give every numeric section one score band while preserving assurance limits.

    A section may have review-limited assurance and still carry a numeric evidence-bound
    score. The score band is the presentation status; assurance limitations remain in a
    separate field and are never converted into verified scanner evidence.
    """

    result = deepcopy(dict(assessment))
    normalized: list[dict[str, Any]] = []
    repaired = 0
    for raw in result.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        section = deepcopy(dict(raw))
        score = _numeric(section.get("presented_score", section.get("score")))
        if score is not None:
            prior = _text(section.get("presented_status") or section.get("status")).upper()
            band = score_band(score)
            assurance = _text(section.get("assurance_status")).casefold()
            review_limited = bool(
                "REVIEW_LIMITED" in prior
                or "NOT_SCORED" in prior
                or assurance == "review_limited"
                or any(section.get("unavailable") or [])
            )
            if prior and prior not in _SCORE_BANDS:
                section.setdefault("source_assurance_status", prior.casefold())
            if prior != band or _text(section.get("status")).casefold() != band.casefold():
                repaired += 1
            section["score"] = score
            section["presented_score"] = score
            section["status"] = band.casefold()
            section["presented_status"] = band
            section["assurance_status"] = (
                "review_limited" if review_limited else "verified_with_completed_scanners"
            )
            section["score_status_consistent"] = True
        normalized.append(section)

    result["sections"] = normalized
    contract = deepcopy(dict(result.get("section_status_contract") or {}))
    contract.update(
        {
            "version": VERSION,
            "numeric_sections_use_score_bands": True,
            "assurance_status_is_separate": True,
            "scored_sections_never_labeled_not_scored": True,
            "sections_repaired": repaired,
        }
    )
    result["section_status_contract"] = contract
    return result


def normalize_report_package(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {}))
    if canonical:
        canonical["assessment"] = normalize_scored_sections(
            canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
        )
        pipeline = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
        pipeline.update(
            {
                "canonical_section_status_version": VERSION,
                "scored_sections_never_labeled_not_scored": True,
                "section_assurance_separated_from_score_band": True,
            }
        )
        canonical["v2_pipeline_contract"] = pipeline
        result["json"] = canonical
    return result


def assessment_semantic_payload(assessment: Mapping[str, Any]) -> dict[str, Any]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}
    truth = assessment.get("comprehensive_score_truth") if isinstance(assessment.get("comprehensive_score_truth"), Mapping) else {}
    technical = next(
        (
            score
            for value in (
                truth.get("technical_score"),
                assessment.get("technical_score"),
                maturity.get("technical_score"),
                maturity.get("presented_score"),
                maturity.get("score"),
            )
            if (score := _numeric(value)) is not None
        ),
        None,
    )
    adjusted = next(
        (
            score
            for value in (
                truth.get("canonical_evidence_adjusted_score"),
                truth.get("evidence_adjusted_score"),
                assessment.get("canonical_evidence_adjusted_score"),
                assessment.get("evidence_adjusted_score"),
                maturity.get("canonical_evidence_adjusted_score"),
                maturity.get("evidence_adjusted_score"),
                technical,
            )
            if (score := _numeric(value)) is not None
        ),
        None,
    )

    sections = []
    for raw in assessment.get("sections") or []:
        if not isinstance(raw, Mapping):
            continue
        sections.append(
            {
                "id": _text(raw.get("id") or raw.get("label")).casefold(),
                "label": _text(raw.get("label") or raw.get("id")),
                "score": _numeric(raw.get("presented_score", raw.get("score"))),
                "status": _text(raw.get("presented_status") or raw.get("status")).upper(),
                "assurance_status": _text(raw.get("assurance_status")).casefold(),
            }
        )

    scanners = []
    for raw in assessment.get("scanner_execution_records") or []:
        if not isinstance(raw, Mapping):
            continue
        scanners.append(
            {
                "scanner_name": _text(raw.get("scanner_name") or raw.get("tool")).casefold().replace("_", "-"),
                "status": _text(raw.get("status") or raw.get("state")).casefold().replace("-", "_"),
                "completed": raw.get("completed") is True,
                "verified_complete": raw.get("verified_complete") is True,
                "findings_count": len(raw.get("findings") or []),
            }
        )

    return {
        "technical_score": technical,
        "evidence_adjusted_score": adjusted,
        "sections": sorted(sections, key=lambda item: (item["id"], item["label"])),
        "scanners": sorted(scanners, key=lambda item: item["scanner_name"]),
    }


def assessment_semantic_sha256(assessment: Mapping[str, Any]) -> str:
    payload = json.dumps(
        assessment_semantic_payload(assessment),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


__all__ = [
    "VERSION",
    "assessment_semantic_payload",
    "assessment_semantic_sha256",
    "normalize_report_package",
    "normalize_scored_sections",
    "score_band",
]
