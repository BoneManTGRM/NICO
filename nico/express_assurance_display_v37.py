from __future__ import annotations

from typing import Any

VERSION = "nico.express_assurance_display.v37"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    result.clear()
    result.update(normalized)
    if isinstance(existing_reports, dict) and isinstance(result.get("reports"), dict):
        replacement = result["reports"]
        existing_reports.clear()
        existing_reports.update(replacement)
        result["reports"] = existing_reports


def _pdf_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    from nico import express_pdf_score_assurance_v1 as target

    normalized = target.reconcile_section_status_truth(result)
    _apply_in_place(result, normalized)
    output: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
        assurance = _text(section.get("assurance_label") or "UNVERIFIED")
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "score": score,
                "score_label": "NOT SCORED" if score is None else f"{int(score)}/100",
                "band": _text(section.get("score_band_label") or "NOT SCORED"),
                "score_tone": _text(section.get("score_tone") or "gray").casefold(),
                "assurance": assurance,
                "assurance_tone": _text(section.get("assurance_tone") or "gray").casefold(),
                # Do not expose legacy GREEN/YELLOW/RED as if it were a second
                # technical result. The canonical state shown to clients is the
                # evidence-assurance disposition.
                "canonical_status": assurance,
                "confidence": _text(section.get("presented_confidence") or section.get("confidence") or "unknown"),
                "rationale": _text(section.get("score_rationale") or section.get("status_reason") or "No material score constraint retained."),
                "directly_scored": section.get("directly_scored") is not False and score is not None,
            }
        )
    return output


def _export_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    from nico import express_score_assurance_export_v1 as target

    normalized = target.reconcile_section_status_truth(result)
    _apply_in_place(result, normalized)
    output: list[dict[str, Any]] = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
        assurance = _text(section.get("assurance_label") or "UNVERIFIED")
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "technical_score": score,
                "technical_score_label": "NOT SCORED" if score is None else f"{int(score)}/100",
                "technical_band": _text(section.get("score_band") or "not_scored"),
                "technical_band_label": _text(section.get("score_band_label") or "NOT SCORED"),
                "score_tone": _text(section.get("score_tone") or "gray"),
                "assurance_status": _text(section.get("assurance_status") or "unverified"),
                "assurance_label": assurance,
                "assurance_tone": _text(section.get("assurance_tone") or "gray"),
                "canonical_status": assurance,
                "directly_scored": section.get("directly_scored") is not False and score is not None,
            }
        )
    return output


def install_express_assurance_display_v37() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as pdf_target
    from nico import express_score_assurance_export_v1 as export_target

    pdf_target._records = _pdf_records
    export_target._records = _export_records
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_traffic_light_status_hidden_from_client_tables": True,
        "technical_band_and_assurance_are_independent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_assurance_display_v37"]
