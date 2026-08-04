from __future__ import annotations

import base64
import html
import io
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-client-truth-canonical.v2"
_NORMALIZE_MARKER = "__nico_comprehensive_client_truth_canonical_v2__"
_VALIDATE_MARKER = "__nico_comprehensive_client_truth_validation_v2__"
_POSTURE_MARKER = "__nico_comprehensive_cover_posture_v2__"
_TIMESTAMP = re.compile(r"\b20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z\b")
_GENERATED_LABEL = re.compile(
    r"\bGenerated(?:\s+at)?\s*:?[\s<>&a-zA-Z0-9;/=\"'-]{0,80}?"
    r"(20\d{2}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z)",
    re.IGNORECASE,
)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _visible_html(value: str) -> str:
    without_tags = re.sub(r"<[^>]+>", " ", str(value or ""))
    return _text(html.unescape(without_tags), 200000)


def _pdf_text(package: Mapping[str, Any]) -> str:
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""), validate=True)
        return "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    except Exception as exc:
        raise ValueError("Comprehensive client package has no valid PDF") from exc


def _canonical_generated_at(canonical: Mapping[str, Any]) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    value = _text(
        identity.get("generated_at")
        or identity.get("generation_timestamp")
        or canonical.get("generated_at")
        or canonical.get("generation_timestamp"),
        180,
    )
    match = _TIMESTAMP.fullmatch(value)
    return match.group(0) if match else ""


def _clean_stage_evidence(values: Any) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values or []:
        item = _text(raw, 1200)
        if not item or not re.search(r"[A-Za-z0-9]", item):
            continue
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _normalize_stage_truth(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(canonical))
    stages: list[dict[str, Any]] = []
    for raw in output.get("stage_summaries") or []:
        if not isinstance(raw, Mapping):
            continue
        stage = deepcopy(dict(raw))
        stage_id = _text(stage.get("stage_id"), 120)
        stage["evidence"] = _clean_stage_evidence(stage.get("evidence"))
        if stage_id == "risk_reduction_and_executive_briefing":
            stage["status"] = "review_required"
            stage["summary"] = (
                "The automated executive briefing and bounded priority register are complete for review; "
                "finding acceptance, residual-risk ownership, remediation commitment, and delivery authorization remain pending human disposition."
            )
        elif stage_id == "six_month_roadmap":
            stage["status"] = "framework_only"
            stage["summary"] = (
                "A six-month roadmap framework was derived from canonical technical findings. Dates, owners, "
                "sequencing, staffing, cost, business priority, and delivery commitments remain pending authorized stakeholder validation."
            )
        elif stage_id == "staffing_sequencing_and_cost":
            stage["status"] = "framework_only"
            stage["summary"] = (
                "Role sequencing is advisory. Named people, capacity, rates, contract structure, geographic mix, "
                "budget, and commercial commitments remain pending authorized stakeholder validation."
            )
        stages.append(stage)
    output["stage_summaries"] = stages
    assessment = (
        deepcopy(dict(output.get("assessment")))
        if isinstance(output.get("assessment"), Mapping)
        else {}
    )
    assessment["stage_summaries"] = deepcopy(stages)
    output["assessment"] = assessment
    return output


def _validate_generated_labels(surface_name: str, surface: str, generated_at: str) -> None:
    values = [match.group(1) for match in _GENERATED_LABEL.finditer(surface)]
    if not values:
        raise ValueError(f"{surface_name} omitted the canonical generated_at label")
    stale = sorted({value for value in values if value != generated_at})
    if stale:
        raise ValueError(
            f"{surface_name} rendered a non-canonical generated_at value: {', '.join(stale)}"
        )


def _validate_final_cross_format_truth(package: Mapping[str, Any]) -> None:
    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    generated_at = _canonical_generated_at(canonical)
    if not generated_at:
        raise ValueError("canonical Comprehensive package is missing a valid generated_at")

    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    pdf_text = _pdf_text(package)
    surfaces = {
        "Markdown": _text(markdown, 200000),
        "HTML": _visible_html(rendered_html),
        "PDF": _text(pdf_text, 200000),
    }
    for name, value in surfaces.items():
        _validate_generated_labels(name, value, generated_at)

    summary = _text(assessment.get("executive_summary"), 12000)
    if not summary:
        raise ValueError("canonical executive summary is missing")
    for name, value in surfaces.items():
        if summary not in value:
            raise ValueError(
                f"{name} does not render the exact canonical executive summary"
            )

    combined = "\n".join(surfaces.values())
    forbidden = (
        "completed an authorized Comprehensive Technical Assessment",
        "completó una evaluación técnica integral autorizada",
        "Six-Month Roadmap · COMPLETE",
        "Stage ID: six_month_roadmap · Status: COMPLETE",
        "Platform Parity: Complete",
        "Decision-Grade Technical Assessment",
    )
    retained = [marker for marker in forbidden if marker.casefold() in combined.casefold()]
    if retained:
        raise ValueError(
            "Comprehensive client package retained contradictory lifecycle or stage language: "
            + ", ".join(retained)
        )

    for stage in canonical.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        for item in stage.get("evidence") or []:
            if not re.search(r"[A-Za-z0-9]", _text(item)):
                raise ValueError("client stage evidence retained a punctuation-only blank value")


def install_comprehensive_client_truth_canonical_v2() -> dict[str, Any]:
    from nico import comprehensive_client_truth_final_v1 as truth
    from nico import v2_dark_branded_cover as cover

    current_normalize = truth.normalize_client_truth
    if not getattr(current_normalize, _NORMALIZE_MARKER, False):

        @wraps(current_normalize)
        def normalize_client_truth(canonical: Mapping[str, Any]) -> dict[str, Any]:
            return _normalize_stage_truth(current_normalize(canonical))

        setattr(normalize_client_truth, _NORMALIZE_MARKER, True)
        setattr(normalize_client_truth, "_nico_previous", current_normalize)
        truth.normalize_client_truth = normalize_client_truth

    current_validate = truth._validate_surfaces
    if not getattr(current_validate, _VALIDATE_MARKER, False):

        @wraps(current_validate)
        def _validate_surfaces(package: Mapping[str, Any]) -> None:
            current_validate(package)
            _validate_final_cross_format_truth(package)

        setattr(_validate_surfaces, _VALIDATE_MARKER, True)
        setattr(_validate_surfaces, "_nico_previous", current_validate)
        truth._validate_surfaces = _validate_surfaces

    current_posture = cover._executive_posture
    if not getattr(current_posture, _POSTURE_MARKER, False):

        @wraps(current_posture)
        def _executive_posture(
            canonical: Mapping[str, Any],
            technical: str,
            adjusted: str,
            *,
            spanish: bool,
        ) -> str:
            identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
            repository = _text(identity.get("repository"), 300)
            if spanish:
                return (
                    f"NICO generó un borrador automatizado de evaluación técnica integral para {repository}. "
                    f"La madurez técnica ponderada es {technical} y la preparación ajustada por evidencia es {adjusted}. "
                    "El paquete conserva salud del repositorio, hallazgos con ubicación exacta, evidencia de arquitectura, "
                    "un marco de hoja de ruta y exportaciones estructuradas para revisión humana; no constituye aprobación ni autorización de entrega."
                )
            return (
                f"NICO generated an automated Comprehensive Technical Assessment draft for {repository}. "
                f"Weighted technical maturity is {technical}; independently evidence-adjusted readiness is {adjusted}. "
                "The evidence-bound package retains repository health, exact-location findings, architecture evidence, "
                "a roadmap framework, and structured exports for human review; it is not approval or client-delivery authorization."
            )

        setattr(_executive_posture, _POSTURE_MARKER, True)
        setattr(_executive_posture, "_nico_previous", current_posture)
        cover._executive_posture = _executive_posture

    return {
        "status": "installed",
        "version": VERSION,
        "canonical_truth_precedes_rendering": True,
        "generated_at_equal_across_formats": True,
        "executive_summary_equal_across_formats": True,
        "roadmap_status_is_framework_only": True,
        "executive_briefing_requires_human_disposition": True,
        "punctuation_only_stage_evidence_removed": True,
        "authorized_automation_claims_blocked": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_client_truth_canonical_v2",
]
