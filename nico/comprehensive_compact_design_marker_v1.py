from __future__ import annotations

import base64
import io
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

VERSION = "nico.comprehensive-compact-design-marker.v1"
_MARKER = "_nico_comprehensive_compact_design_marker_v1"

_DESIGN_MARKER_GROUPS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "NICO assessment identity",
        (
            "NICO COMPREHENSIVE",
            "NICO Comprehensive Technical Assessment",
            "Evaluación Técnica Integral NICO",
        ),
    ),
    (
        "canonical technical scorecard",
        ("Canonical Technical Scorecard",),
    ),
    (
        "client evidence summary",
        (
            "Evidence Package Summary",
            "Client Evidence Summary",
            "Resumen del paquete de evidencia",
            "Resumen de evidencia para revisión",
            "Resumen de evidencia para revision",
        ),
    ),
    (
        "human review and acceptance gate",
        (
            "Human Review and Acceptance Gate",
            "Puerta de revisión humana y aceptación",
            "Puerta de revision humana y aceptacion",
            "Puerta de revisión y entrega",
            "Puerta de revision y entrega",
        ),
    ),
)


def _combined_client_text(package: Mapping[str, Any]) -> str:
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    try:
        pdf = base64.b64decode(str(package.get("pdf_base64") or ""))
    except Exception as exc:
        raise ValueError("client report did not retain a decodable PDF") from exc
    if not pdf.startswith(b"%PDF"):
        raise ValueError("client report did not retain a valid final PDF")
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    return "\n".join((markdown, rendered_html, extracted))


def validate_compact_design_markers(package: Mapping[str, Any]) -> dict[str, Any]:
    """Require the bounded report's real decision sections, not a removed appendix."""

    combined = _combined_client_text(package)
    normalized = combined.casefold()
    missing: list[str] = []
    observed: dict[str, str] = {}
    for section, alternatives in _DESIGN_MARKER_GROUPS:
        matched = next(
            (marker for marker in alternatives if marker.casefold() in normalized),
            "",
        )
        if not matched:
            missing.append(section)
        else:
            observed[section] = matched
    if missing:
        raise ValueError(
            "approved compact NICO report design sections were not preserved: "
            + ", ".join(missing)
        )
    if "Evidence Appendix" in combined or "Apéndice de evidencia" in combined:
        raise ValueError(
            "compact client report restored the retired raw evidence appendix"
        )
    return {
        "version": VERSION,
        "compact_design_sections_verified": True,
        "observed_design_markers": observed,
        "retired_evidence_appendix_absent": True,
        "bounded_evidence_summary_present": True,
        "human_review_gate_present": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_compact_design_marker_gate() -> dict[str, Any]:
    from nico import comprehensive_client_report_render_v60 as client_render

    current = client_render.validate_existing_report_accuracy
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "retired_evidence_appendix_not_required": True,
            "compact_evidence_summary_required": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    # The legacy validator required the raw Evidence Appendix that the approved
    # bounded client package deliberately removes. Preserve every score, scanner,
    # maturity, identity, and malformed-content check in the delegate, and move
    # only the visual-section contract to the grouped compact marker gate below.
    client_render._DESIGN_MARKERS = ()

    @wraps(current)
    def validate(package: Mapping[str, Any]) -> dict[str, Any]:
        result = dict(current(package))
        compact = validate_compact_design_markers(package)
        result["compact_design_marker_gate"] = compact
        result.update(
            {
                "existing_visual_design_preserved": True,
                "compact_evidence_summary_verified": True,
                "retired_evidence_appendix_absent": True,
            }
        )
        return result

    setattr(validate, _MARKER, True)
    setattr(validate, "_nico_previous", current)
    client_render.validate_existing_report_accuracy = validate
    return {
        "status": "installed",
        "version": VERSION,
        "bound": client_render.validate_existing_report_accuracy is validate,
        "legacy_design_marker_tuple_disabled": client_render._DESIGN_MARKERS == (),
        "retired_evidence_appendix_not_required": True,
        "compact_evidence_summary_required": True,
        "bilingual_marker_groups_required": True,
        "score_scanner_maturity_and_identity_delegate_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_compact_design_marker_gate",
    "validate_compact_design_markers",
]
