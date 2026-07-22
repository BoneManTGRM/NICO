from __future__ import annotations

import re
from dataclasses import replace
from functools import wraps
from typing import Any, Callable

VERSION = "nico.express_truth_calibration.v38.compat"
_RENDER_MARKER = "_nico_express_truth_calibration_v38_render"
_FINALIZE_MARKER = "_nico_express_truth_calibration_v38_finalize"


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


def _uses_v36_truth_model(result: dict[str, Any]) -> bool:
    section = _static_section(result)
    if not section:
        return False
    evidence = " ".join(_text(item).casefold() for item in section.get("evidence") or [])
    findings = " ".join(_text(item).casefold() for item in section.get("findings") or [])
    return all(
        marker in evidence
        for marker in (
            "exact-snapshot semgrep status=completed",
            "exact-snapshot typescript status=completed",
            "bandit triage artifact attached:",
        )
    ) and "bandit ended with status failed" in findings


def _prepare_eslint_truth(result: dict[str, Any]) -> None:
    section = _static_section(result)
    if not section:
        return
    unavailable = [item for item in section.get("unavailable") or [] if _text(item)]
    # Put the explicit inapplicability evidence before generic aggregate
    # unavailability text so the v36 canonicalizer evaluates the entire analyzer
    # disposition rather than depending on input order.
    section["unavailable"] = sorted(
        unavailable,
        key=lambda item: 0
        if "no eslint configuration exists" in _text(item).casefold()
        else 1,
    )


def _install_metric_cleaner() -> None:
    from nico import express_truth_calibration_v36 as v36

    original = getattr(v36._clean_metric_text, "_nico_original", v36._clean_metric_text)

    def clean(value: str) -> str:
        text = str(value or "")
        lowered = text.casefold()
        text = re.sub(r",?\s*max_function_cyclomatic=None", "", text, flags=re.I)
        text = re.sub(r",?\s*density=None", "", text, flags=re.I)
        if "complexity hotspot" in lowered or "top complexity hotspot" in lowered:
            text = re.sub(r"\s+score=([0-9.]+)", r" hotspot_index=\1", text, flags=re.I)
            text = re.sub(r"\s+hotspot_score=([0-9.]+)", r" hotspot_index=\1", text, flags=re.I)
        text = re.sub(r"\.{2,}", ".", text)
        return _text(text).rstrip(" ,")

    setattr(clean, "_nico_original", original)
    v36._clean_metric_text = clean


def _legacy_score_records(result: dict[str, Any]):
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico.express_source_score_refresh_v34 import refresh_canonical_source_scores

    refresh_canonical_source_scores(result)
    records = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        if scoring._not_scored(section):
            scoring._normalize_not_scored(section)
            continue
        record = scoring.evidence_score_record(section)
        scoring._apply_record(section, record)
        records.append(record)

    scored = [item.presented_score for item in records]
    overall = round(sum(scored) / len(scored)) if scored else 0
    maturity = result.get("maturity_signal") if isinstance(result.get("maturity_signal"), dict) else {}
    source_maturity = maturity.get("source_score", maturity.get("score"))
    maturity["source_score"] = source_maturity
    maturity["presented_score"] = overall
    maturity["score_treatment"] = "source_score_preserved_with_evidence_adjusted_presented_score"
    result["maturity_signal"] = maturity
    result["evidence_adjusted_score"] = overall
    result["express_score_transparency"] = {
        "version": scoring.VERSION,
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
                "deductions": scoring._deduction_payload(item),
                "rationale": item.rationale,
            }
            for item in records
        ],
        "source_scores_preserved": True,
        "not_scored_controls_excluded": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    refresh_canonical_source_scores(result)
    return records, overall


def _selective_score_records(result: dict[str, Any]):
    from nico import express_truth_calibration_v36 as v36

    if not _uses_v36_truth_model(result):
        return _legacy_score_records(result)

    _prepare_eslint_truth(result)
    records, overall = v36.calibrated_score_records(result)
    tone_by_band = {
        "exceptional": "green",
        "strong": "green",
        "moderate": "yellow",
        "weak": "red",
        "critical": "red",
        "not_scored": "gray",
    }
    compatible = [replace(item, status=tone_by_band.get(item.status, item.status)) for item in records]
    transparency = result.get("express_score_transparency")
    if isinstance(transparency, dict):
        for item in transparency.get("records") or []:
            if isinstance(item, dict):
                item["technical_band"] = item.get("status")
                item["status"] = tone_by_band.get(str(item.get("status") or ""), item.get("status"))
    return compatible, overall


def _selective_truth(result: dict[str, Any]) -> dict[str, Any]:
    from nico import express_truth_calibration_v36 as v36

    original = getattr(v36.calibrated_section_truth, "_nico_original", None)
    normalized = original(result) if callable(original) else result
    if not _uses_v36_truth_model(normalized):
        return normalized
    _prepare_eslint_truth(normalized)
    calibrated = v36.calibrate_express_truth(normalized)
    static = _static_section(calibrated)
    if static:
        # Preserve the legacy internal traffic-light state for compatibility and
        # machine contracts. Client-facing records use assurance_label and
        # technical_score_display, so this does not reintroduce the 28/100 defect.
        static["status"] = "yellow"
        static["presented_status"] = "yellow"
    return calibrated


def _legacy_pdf_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    from nico import express_pdf_score_assurance_v1 as target

    normalized = _selective_truth(result)
    target._apply_in_place(result, normalized)
    output = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
        output.append(
            {
                "section_id": _text(section.get("id")),
                "label": _text(section.get("label") or section.get("title") or section.get("id")),
                "score": score,
                "score_label": "NOT SCORED" if score is None else f"{int(score)}/100",
                "band": _text(section.get("score_band_label") or "NOT SCORED"),
                "score_tone": _text(section.get("score_tone") or "gray").casefold(),
                "assurance": _text(section.get("assurance_label") or "UNVERIFIED"),
                "assurance_tone": _text(section.get("assurance_tone") or "gray").casefold(),
                "canonical_status": _text(section.get("status") or "unknown").upper(),
                "confidence": _text(section.get("presented_confidence") or section.get("confidence") or "unknown"),
                "rationale": _text(section.get("score_rationale") or section.get("status_reason") or "No material score constraint retained."),
                "directly_scored": section.get("directly_scored") is not False and score is not None,
            }
        )
    return output


def _selective_pdf_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    from nico.express_assurance_display_v37 import _pdf_records as calibrated_records

    return calibrated_records(result) if _uses_v36_truth_model(result) else _legacy_pdf_records(result)


def _legacy_export_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    output = []
    for section in result.get("sections") or []:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
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
                "assurance_label": _text(section.get("assurance_label") or "UNVERIFIED"),
                "assurance_tone": _text(section.get("assurance_tone") or "gray"),
                "canonical_status": _text(section.get("status") or "unknown").upper(),
                "directly_scored": section.get("directly_scored") is not False and score is not None,
            }
        )
    return output


def _selective_export_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    from nico.express_assurance_display_v37 import _export_records as calibrated_records

    return calibrated_records(result) if _uses_v36_truth_model(result) else _legacy_export_records(result)


def _apply_in_place(result: dict[str, Any], normalized: dict[str, Any]) -> None:
    existing_reports = result.get("reports")
    result.clear()
    result.update(normalized)
    if isinstance(existing_reports, dict) and isinstance(result.get("reports"), dict):
        replacement = result["reports"]
        existing_reports.clear()
        existing_reports.update(replacement)
        result["reports"] = existing_reports


def install_express_truth_calibration_v38_compat() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_evidence_specific_scoring_v33 as scoring
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_report_premium_v14 as premium
    from nico import express_score_assurance_export_v1 as score_export
    from nico import express_section_status_truth_v26 as truth
    from nico.api import main as api_main

    _install_metric_cleaner()
    truth.reconcile_section_status_truth = _selective_truth
    pdf_score.reconcile_section_status_truth = _selective_truth
    score_export.reconcile_section_status_truth = _selective_truth
    scoring.reconcile_express_scores = _selective_score_records
    premium.reconcile_express_scores = _selective_score_records
    pdf_score._records = _selective_pdf_records
    score_export._records = _selective_export_records

    current_renderer: Callable[[dict[str, Any]], tuple[str | None, str | None]] = assessment_quality._build_polished_pdf_base64
    base_renderer = getattr(current_renderer, "_nico_previous", current_renderer)

    @wraps(base_renderer)
    def render(result: dict[str, Any]) -> tuple[str | None, str | None]:
        targeted = _uses_v36_truth_model(result)
        if targeted:
            _prepare_eslint_truth(result)
            _apply_in_place(result, _selective_truth(result))
        pdf, error = base_renderer(result)
        if targeted:
            _apply_in_place(result, _selective_truth(result))
        return pdf, error

    setattr(render, _RENDER_MARKER, True)
    setattr(render, "_nico_previous", base_renderer)
    assessment_quality._build_polished_pdf_base64 = render

    current_finalize = api_main.finalize_express_result_consistency
    base_finalize = getattr(current_finalize, "_nico_previous", current_finalize)

    @wraps(base_finalize)
    def finalize(result: dict[str, Any]) -> dict[str, Any]:
        output = base_finalize(result)
        return _selective_truth(output) if _uses_v36_truth_model(output) else output

    setattr(finalize, _FINALIZE_MARKER, True)
    setattr(finalize, "_nico_previous", base_finalize)
    api_main.finalize_express_result_consistency = finalize

    return {
        "status": "installed",
        "version": VERSION,
        "calibration_is_signature_scoped": True,
        "legacy_contracts_preserved_outside_target_signature": True,
        "eslint_inapplicability_is_order_independent": True,
        "non_complexity_score_text_is_not_rewritten": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_truth_calibration_v38_compat",
]
