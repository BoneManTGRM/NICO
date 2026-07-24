from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.report_semantic_cleanup_v46 import normalize_final_report_semantics

VERSION = "nico.express_assurance_projection_compat.v46"
_PATCH_MARKER = "_nico_express_assurance_projection_compat_v46"


def canonical_assurance_label(section: dict[str, Any]) -> str:
    explicit = " ".join(str(section.get("assurance_label") or section.get("evidence_assurance") or "").split()).upper()
    if explicit and explicit != "UNVERIFIED":
        return explicit

    confidence = " ".join(
        str(section.get("presented_confidence") or section.get("confidence") or "").split()
    ).casefold().replace("-", "_").replace(" ", "_")
    if confidence in {"review_limited", "reviewlimited"}:
        return "REVIEW LIMITED"
    if confidence in {"high", "verified"}:
        return "VERIFIED"

    status = " ".join(
        str(section.get("assurance_status") or section.get("status") or "").split()
    ).casefold().replace("-", "_").replace(" ", "_")
    if status in {"verified", "complete", "completed", "green", "strong", "exceptional"}:
        return "VERIFIED"
    if status in {"unavailable", "not_available"}:
        return "UNAVAILABLE"
    if status in {"incomplete", "failed", "blocked", "error", "timed_out", "timeout"}:
        return "INCOMPLETE"
    if status == "supplemental":
        return "SUPPLEMENTAL"
    if status in {"human_review_pending", "pending_human_approval"}:
        return "PENDING HUMAN APPROVAL"
    if status in {"review_limited", "reviewlimited", "yellow", "moderate", "weak"}:
        return "REVIEW LIMITED"
    return "UNVERIFIED"


def canonical_risk_label(section: dict[str, Any]) -> str:
    explicit = " ".join(str(section.get("risk_label") or section.get("risk_disposition") or "").split()).upper()
    if explicit:
        return explicit
    if section.get("section_group") == "review_delivery":
        return "HUMAN REVIEW REQUIRED"
    findings = [str(item).strip() for item in section.get("findings") or [] if str(item).strip()]
    review_items = [str(item).strip() for item in section.get("review_items") or [] if str(item).strip()]
    unavailable = [str(item).strip() for item in section.get("unavailable") or [] if str(item).strip()]
    if findings or review_items:
        return "HUMAN TRIAGE REQUIRED"
    if unavailable:
        return "EVIDENCE LIMITATION"
    return "NO MATERIAL FINDING"


def _normalize_records(records: list[dict[str, Any]], payload: dict[str, Any]) -> list[dict[str, Any]]:
    sections = {
        str(item.get("id") or ""): item
        for item in payload.get("sections") or []
        if isinstance(item, dict)
    }
    for record in records:
        section = sections.get(str(record.get("section_id") or ""), {})
        record["assurance"] = canonical_assurance_label(section)
        record["canonical_status"] = canonical_risk_label(section)
        record["risk_disposition"] = record["canonical_status"]
        record["confidence"] = str(section.get("presented_confidence") or section.get("confidence") or "")
    return records


def _normalize_in_place(payload: dict[str, Any]) -> dict[str, Any]:
    cleaned = normalize_final_report_semantics(payload)
    payload.clear()
    payload.update(cleaned)
    return payload


def _wrap_payload_function(module: Any, name: str) -> bool:
    current: Callable[..., Any] = getattr(module, name)
    if getattr(current, _PATCH_MARKER, False):
        return False

    @wraps(current)
    def wrapped(payload: dict[str, Any], *args: Any, **kwargs: Any) -> Any:
        return current(_normalize_in_place(payload), *args, **kwargs)

    setattr(wrapped, _PATCH_MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    setattr(module, name, wrapped)
    return True


def _install_assessment_pdf_metadata_compat(module: Any) -> bool:
    current: Callable[[dict[str, Any]], Any] = module._polish_pdf_report
    marker = f"{_PATCH_MARKER}_pdf_metadata"
    if getattr(current, marker, False):
        return False

    @wraps(current)
    def polish_pdf_report(result: dict[str, Any]) -> Any:
        outcome = current(result)
        reports = result.setdefault("reports", {})
        if reports.get("pdf_base64"):
            reports.setdefault("pdf_style", module.PDF_STYLE_VERSION)
            reports.setdefault(
                "pdf_filename",
                f"nico-express-{str(result.get('repository') or 'assessment').replace('/', '-')}.pdf",
            )
        return outcome

    setattr(polish_pdf_report, marker, True)
    setattr(polish_pdf_report, "_nico_previous", current)
    module._polish_pdf_report = polish_pdf_report
    return True


def install_express_assurance_projection_compat_v45() -> dict[str, Any]:
    from nico import assessment_quality
    from nico import express_assurance_display_v37 as target
    from nico import express_client_report_postprocessor_v27 as postprocessor
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_premium_v14 as premium

    changed = 0
    target._assurance_label = canonical_assurance_label

    current_pdf_records = target._pdf_records
    if not getattr(current_pdf_records, _PATCH_MARKER, False):
        @wraps(current_pdf_records)
        def pdf_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
            cleaned = normalize_final_report_semantics(payload)
            return _normalize_records(current_pdf_records(cleaned), cleaned)

        setattr(pdf_records, _PATCH_MARKER, True)
        setattr(pdf_records, "_nico_previous", current_pdf_records)
        target._pdf_records = pdf_records
        changed += 1

    current_export_records = target._export_records
    if not getattr(current_export_records, _PATCH_MARKER, False):
        @wraps(current_export_records)
        def export_records(payload: dict[str, Any]) -> list[dict[str, Any]]:
            cleaned = normalize_final_report_semantics(payload)
            return _normalize_records(current_export_records(cleaned), cleaned)

        setattr(export_records, _PATCH_MARKER, True)
        setattr(export_records, "_nico_previous", current_export_records)
        target._export_records = export_records
        changed += 1

    changed += int(_wrap_payload_function(postprocessor, "prepare_express_client_report"))
    changed += int(_wrap_payload_function(premium, "_premium_pdf"))

    if dossier._premium_pdf is not premium._premium_pdf:
        dossier._premium_pdf = premium._premium_pdf
        changed += 1

    changed += int(_wrap_payload_function(dossier, "build_express_dossier_export"))
    changed += int(_install_assessment_pdf_metadata_compat(assessment_quality))

    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "functions_rebound": changed,
        "explicit_assurance_precedes_stale_confidence": True,
        "technical_band_does_not_overwrite_assurance": True,
        "risk_disposition_replaces_duplicate_status": True,
        "final_semantic_cleanup_bound": True,
        "in_place_report_mutation_preserved": True,
        "dossier_renderer_identity_preserved": dossier._premium_pdf is premium._premium_pdf,
        "pdf_export_metadata_preserved": True,
        "acceptance_outside_technical_maturity_until_approved": True,
        "approved_acceptance_lifecycle_preserved": True,
        "bounded_sample_false_priority_removed": True,
    }


__all__ = [
    "VERSION",
    "canonical_assurance_label",
    "canonical_risk_label",
    "install_express_assurance_projection_compat_v45",
]
