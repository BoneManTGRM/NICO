from __future__ import annotations

import re
from copy import deepcopy
from typing import Any, Callable

VERSION = "nico.express_report_final_polish.v41"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _static_section(result: dict[str, Any]) -> dict[str, Any] | None:
    return next(
        (
            item
            for item in result.get("sections") or []
            if isinstance(item, dict) and _text(item.get("id")).casefold() == "static_analysis"
        ),
        None,
    )


def _remove_name(value: str, name: str) -> str:
    prefix, separator, suffix = value.partition(":")
    if not separator:
        return value
    names = [
        re.sub(r"[^a-z0-9_-]+$", "", item.strip(), flags=re.I)
        for item in re.split(r"[,/]", suffix)
        if item.strip()
    ]
    names = [item for item in names if item.casefold() != name.casefold()]
    return f"{prefix}: {', '.join(names)}" if names else ""


def _reconcile_static_assurance(result: dict[str, Any]) -> dict[str, Any]:
    from nico.express_truth_calibration_v38_compat import _uses_v36_truth_model

    if not _uses_v36_truth_model(result):
        return result
    section = _static_section(result)
    if not section:
        return result

    values = [
        *list(section.get("evidence") or []),
        *list(section.get("findings") or []),
        *list(section.get("unavailable") or []),
    ]
    eslint_inapplicable = any(
        "no eslint configuration exists" in _text(item).casefold()
        or "eslint is not applicable" in _text(item).casefold()
        for item in values
    )

    evidence: list[str] = []
    for raw in section.get("evidence") or []:
        value = _text(raw)
        if eslint_inapplicable and "static artifacts were observed for:" in value.casefold():
            value = _remove_name(value, "eslint")
        if value:
            evidence.append(value)
    if eslint_inapplicable:
        evidence.append(
            "ESLint is not applicable for this snapshot because the repository has no ESLint configuration and its lint script does not execute ESLint; TypeScript was evaluated independently."
        )

    unavailable: list[str] = []
    for raw in section.get("unavailable") or []:
        value = _text(raw)
        lowered = value.casefold()
        if eslint_inapplicable and (
            "no eslint configuration exists" in lowered
            or lowered.startswith("eslint was unavailable")
        ):
            continue
        if eslint_inapplicable and (
            "accepted clean execution evidence unavailable for:" in lowered
            or "accepted current-run execution evidence remains unresolved for:" in lowered
        ):
            value = _remove_name(value, "eslint")
        if value:
            unavailable.append(value)

    section["evidence"] = list(dict.fromkeys(evidence))
    section["unavailable"] = list(dict.fromkeys(unavailable))
    section["status"] = "yellow"
    section["presented_status"] = "yellow"
    section["assurance_status"] = "review_limited"
    section["assurance_label"] = "REVIEW LIMITED"
    section["assurance_display"] = "REVIEW LIMITED"
    section["assurance_tone"] = "yellow"
    section["canonical_status_role"] = "evidence_assurance"
    return result


def _normalize_repairs(repairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for index, raw in enumerate(repairs, 1):
        item = dict(raw)
        item["source_rank"] = item.get("rank")
        item["rank"] = f"P{index}"
        severity = _text(item.get("severity") or "unclassified").casefold()
        if severity in {"review", "review required", "needs review"}:
            item["severity"] = "review required"
        output.append(item)
    return output


def _compact_decision_pdf(result: dict[str, Any], section_id: str, title: str) -> bytes:
    from nico import express_pdf_score_assurance_v1 as target
    from nico.express_truth_calibration_v38_compat import _uses_v36_truth_model

    original = getattr(_compact_decision_pdf, "_nico_original")
    if not _uses_v36_truth_model(result):
        return original(result, section_id, title)
    section = target._section(result, section_id)
    if not section:
        return original(result, section_id, title)

    # Keep client decision pages dense enough to remain single-page while the
    # complete evidence set remains available in JSON, HTML, Markdown, and the
    # finding dossier. Velocity previously spilled one assurance sentence onto an
    # otherwise empty page.
    limits = {
        "static_analysis": (6, 3, 1),
        "architecture_debt": (7, 5, 1),
        "velocity_complexity": (5, 0, 1),
        "dependency_health": (7, 3, 1),
        "secrets_review": (7, 3, 1),
    }
    evidence_limit, finding_limit, unavailable_limit = limits.get(section_id, (7, 5, 2))
    saved = {
        "evidence": deepcopy(section.get("evidence")),
        "findings": deepcopy(section.get("findings")),
        "unavailable": deepcopy(section.get("unavailable")),
    }
    section["evidence"] = list(section.get("evidence") or [])[:evidence_limit]
    section["findings"] = list(section.get("findings") or [])[:finding_limit]
    section["unavailable"] = list(section.get("unavailable") or [])[:unavailable_limit]
    try:
        return original(result, section_id, title)
    finally:
        section.update(saved)


def install_express_report_final_polish_v41() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_report_premium_v14 as premium
    from nico import express_score_assurance_export_v1 as score_export
    from nico import express_section_status_truth_v26 as truth
    from nico import express_truth_calibration_v38_compat as compat
    from nico.express_pdf_score_assurance_layout_v39 import _compact_decision_pdf as v39_decision

    previous_truth: Callable[[dict[str, Any]], dict[str, Any]] = compat._selective_truth

    def polished_truth(result: dict[str, Any]) -> dict[str, Any]:
        return _reconcile_static_assurance(previous_truth(result))

    setattr(polished_truth, "_nico_previous", previous_truth)
    compat._selective_truth = polished_truth
    truth.reconcile_section_status_truth = polished_truth
    pdf_score.reconcile_section_status_truth = polished_truth
    score_export.reconcile_section_status_truth = polished_truth

    previous_repairs = getattr(premium._clean_repairs, "_nico_original", premium._clean_repairs)

    def clean_repairs(result: dict[str, Any]) -> list[dict[str, Any]]:
        return _normalize_repairs(previous_repairs(result))

    setattr(clean_repairs, "_nico_original", previous_repairs)
    premium._clean_repairs = clean_repairs

    base_decision = getattr(v39_decision, "_nico_original", pdf_score._decision_pdf)
    setattr(_compact_decision_pdf, "_nico_original", base_decision)
    pdf_score._decision_pdf = _compact_decision_pdf

    return {
        "status": "installed",
        "version": VERSION,
        "static_not_scored_assurance": "review_limited",
        "eslint_inapplicability_removed_from_limitations": True,
        "repair_priorities_normalized": True,
        "velocity_orphan_page_prevented": True,
        "full_machine_readable_evidence_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_report_final_polish_v41",
]
