from __future__ import annotations

from dataclasses import replace
from functools import wraps
from typing import Any

VERSION = "nico.express_assurance_display.v37"
_STATIC_ASSURANCE_PATCH = "_nico_static_candidate_assurance_only_v37"


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


def _install_static_candidate_assurance_patch() -> None:
    """Keep unverified static candidates in assurance without lowering technical health."""
    from nico import express_truth_calibration_v36 as v36

    current = v36.calibrated_score_records
    if getattr(current, _STATIC_ASSURANCE_PATCH, False):
        return

    @wraps(current)
    def calibrated_score_records(result: dict[str, Any]):
        records, overall = current(result)
        static = next(
            (
                section
                for section in result.get("sections") or []
                if isinstance(section, dict) and _text(section.get("id")).casefold() == "static_analysis"
            ),
            None,
        )
        if not static or static.get("exclude_from_maturity") is True:
            return records, overall

        updated = []
        changed = False
        rationale = (
            "Evidence assurance remains review-limited; unverified static-analysis candidates and incomplete analyzer "
            "acceptance require human disposition but do not reduce the bounded technical-health score."
        )
        for record in records:
            if record.section_id != "static_analysis":
                updated.append(record)
                continue
            details = tuple(record.deduction_details)
            candidate_only = bool(details) and all(
                item.rule_id == "OPEN_FINDING"
                and any(
                    token in _text(item.evidence).casefold()
                    for token in ("unverified candidate", "candidate volume", "exact-location triage")
                )
                for item in details
            )
            if not candidate_only:
                updated.append(record)
                continue
            source = int(record.source_score)
            band_key, _band_label, _tone = v36._band(source)
            updated.append(
                replace(
                    record,
                    presented_score=source,
                    status=band_key,
                    deductions=(),
                    deduction_details=(),
                    confidence="review-limited",
                    rationale=rationale,
                )
            )
            static["presented_score"] = source
            static["presented"] = source
            static["score_value"] = source
            static["score_rationale"] = rationale
            static["score_deductions"] = []
            static["presented_confidence"] = "review-limited"
            changed = True

        if not changed:
            return records, overall

        v36._recompute_maturity(result)
        transparency = result.get("express_score_transparency")
        if isinstance(transparency, dict):
            transparency["overall_presented_score"] = result.get("evidence_adjusted_score")
            for item in transparency.get("records") or []:
                if isinstance(item, dict) and item.get("section_id") == "static_analysis":
                    item.update(
                        {
                            "presented_score": static.get("score_value"),
                            "status": static.get("score_band"),
                            "confidence": "review-limited",
                            "deductions": [],
                            "rationale": rationale,
                        }
                    )
        return updated, int(result.get("evidence_adjusted_score") or 0)

    setattr(calibrated_score_records, _STATIC_ASSURANCE_PATCH, True)
    setattr(calibrated_score_records, "_nico_previous", current)
    v36.calibrated_score_records = calibrated_score_records


_install_static_candidate_assurance_patch()


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

    _install_static_candidate_assurance_patch()
    pdf_target._records = _pdf_records
    export_target._records = _export_records
    return {
        "status": "installed",
        "version": VERSION,
        "legacy_traffic_light_status_hidden_from_client_tables": True,
        "technical_band_and_assurance_are_independent": True,
        "static_unverified_candidates_are_assurance_only": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_assurance_display_v37"]
