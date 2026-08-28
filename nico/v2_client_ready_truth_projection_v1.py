from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Mapping

from nico import v2_assessment_pipeline as _pipeline
from nico.comprehensive_client_ready_projection_v1 import (
    apply_automated_draft_truth,
    clean_finding_title,
    clean_identifier,
)
from nico.v2_authoritative_premium_report import _ORIGINAL_HASH

VERSION = "nico.v2.client-ready-truth-projection.v2"
_PATCHED = False

_ASSURANCE_DISCLOSURE_RE = re.compile(
    r"(?:\s*Confirmed material findings:\s*\d+\.\s*"
    r"Review-required candidates:\s*\d+\.\s*"
    r"Score effect:\s*assurance-only until triaged\.)+",
    re.IGNORECASE,
)


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


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


def _provisional_label(*, spanish: bool) -> str:
    return (
        "Fuerte provisional — Revisión humana requerida"
        if spanish
        else "Provisional Strong — Human Review Required"
    )


def _strip_assurance_disclosure(value: Any) -> str:
    cleaned = _ASSURANCE_DISCLOSURE_RE.sub(" ", _text(value))
    return " ".join(cleaned.split()).strip()


def _candidate_summary(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    candidates = [
        canonical.get("review_candidate_summary"),
        assessment.get("review_candidate_summary"),
        canonical.get("scanner_candidate_summary"),
        assessment.get("scanner_candidate_summary"),
    ]
    for value in candidates:
        if isinstance(value, Mapping) and value:
            return deepcopy(dict(value))

    category_counts: dict[str, dict[str, int]] = {}
    for stage in canonical.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        if _text(stage.get("stage_id")).casefold() != "review_required_candidate_register":
            continue
        for line in stage.get("evidence") or []:
            text = _text(line).casefold()
            for category in ("dependency", "secret", "static"):
                if not text.startswith(category):
                    continue
                values: dict[str, int] = {}
                for field in ("raw", "confirmed_material", "review_required", "approved_or_nonblocking"):
                    marker = f"{field}="
                    if marker in text:
                        token = text.split(marker, 1)[1].split(";", 1)[0].strip(" .")
                        values[field] = _integer(token)
                category_counts[category] = {
                    "raw": values.get("raw", 0),
                    "material": values.get("confirmed_material", 0),
                    "review_required": values.get("review_required", 0),
                    "approved_or_nonblocking": values.get("approved_or_nonblocking", 0),
                }
    if not category_counts:
        return {}
    return {
        "by_category": category_counts,
        "review_required_total": sum(item["review_required"] for item in category_counts.values()),
        "verified_material_total": sum(item["material"] for item in category_counts.values()),
        "unverified_candidate_score_effect": "assurance_only",
    }


def _sanitize_findings(canonical: dict[str, Any]) -> None:
    surfaces = (
        "canonical_findings",
        "findings_register",
        "findings",
        "decision_grade_findings_register",
        "executive_risk_register",
        "priority_findings",
    )
    normalized: dict[str, dict[str, Any]] = {}
    for surface in surfaces:
        output: list[dict[str, Any]] = []
        for raw in canonical.get(surface) or []:
            if not isinstance(raw, Mapping):
                continue
            item = deepcopy(dict(raw))
            title = clean_finding_title(item.get("title") or item.get("decision_title"))
            if title:
                item["title"] = title
                item["decision_title"] = title
            for field in ("symbol", "function", "component"):
                if item.get(field):
                    item[field] = clean_identifier(item[field])
            for field in (
                "fact",
                "evidence",
                "interpretation",
                "business_impact",
                "impact",
                "recommendation",
            ):
                if item.get(field):
                    item[field] = _text(item[field]).replace("<arrow>", "anonymous callback")
            identifier = _text(item.get("finding_id") or item.get("id"))
            if identifier:
                normalized[identifier] = item
            output.append(item)
        canonical[surface] = output


def _provisional_sections(canonical: dict[str, Any], summary: Mapping[str, Any]) -> None:
    assessment = deepcopy(dict(canonical.get("assessment") or {}))
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    categories = summary.get("by_category") if isinstance(summary.get("by_category"), Mapping) else {}
    category_aliases = {
        "dependency": ("dependency", "library"),
        "secret": ("secret",),
        "static": ("static",),
    }
    spanish = _is_spanish(canonical)
    output: list[Any] = []
    for raw in sections:
        if not isinstance(raw, Mapping):
            output.append(deepcopy(raw))
            continue
        item = deepcopy(dict(raw))
        identity = _text(item.get("section_id") or item.get("id") or item.get("name") or item.get("label")).casefold()
        matched = None
        for category, aliases in category_aliases.items():
            if any(alias in identity for alias in aliases):
                matched = category
                break
        counts = categories.get(matched) if matched and isinstance(categories.get(matched), Mapping) else {}
        review_required = _integer(counts.get("review_required"))
        if review_required:
            material = _integer(counts.get("material") or counts.get("confirmed_material"))
            label = _provisional_label(spanish=spanish)
            item.update(
                {
                    "status": "Provisional Strong",
                    "status_label": label,
                    "presented_status": label,
                    "assurance_status": "human_review_required",
                    "human_review_required": True,
                    "confirmed_material_findings": material,
                    "review_required_candidates": review_required,
                    "score_effect": "assurance-only until triaged",
                }
            )
            item["summary"] = _strip_assurance_disclosure(item.get("summary"))
        output.append(item)
    assessment["sections"] = output
    assessment["review_candidate_summary"] = deepcopy(dict(summary))
    canonical["assessment"] = assessment
    canonical["review_candidate_summary"] = deepcopy(dict(summary))


def project_client_ready_truth(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical = apply_automated_draft_truth(value)
    _sanitize_findings(canonical)
    summary = _candidate_summary(canonical)
    if summary:
        _provisional_sections(canonical, summary)
    contract = deepcopy(dict(canonical.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "client_ready_truth_projection_version": VERSION,
            "automated_draft_until_human_approval": True,
            "review_candidate_scores_presented_as_provisional": True,
            "review_candidate_status_requires_human_review_label": True,
            "review_candidate_summary_projection_idempotent": True,
            "scanner_execution_separated_from_candidate_disposition": True,
            "client_finding_identifiers_sanitized": True,
        }
    )
    canonical["v2_pipeline_contract"] = contract
    return canonical


def install_client_ready_truth_projection() -> None:
    global _PATCHED
    if _PATCHED:
        return
    previous_build = _pipeline.build_canonical_assessment

    def build(report: Mapping[str, Any]) -> dict[str, Any]:
        return project_client_ready_truth(previous_build(report))

    def canonical_hash(canonical: Mapping[str, Any]) -> str:
        # Use the original deterministic serializer so the hash binds the actual
        # stored automated-draft canonical object. Re-projecting here is unsafe:
        # project_client_ready_truth is a presentation projection and historical
        # canonical objects are not guaranteed to be idempotent under it.
        return _ORIGINAL_HASH(canonical)

    _pipeline.build_canonical_assessment = build
    _pipeline.canonical_truth_sha256 = canonical_hash
    _PATCHED = True


__all__ = [
    "VERSION",
    "install_client_ready_truth_projection",
    "project_client_ready_truth",
]
