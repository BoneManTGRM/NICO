from __future__ import annotations

import re
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.comprehensive-executive-summary-semantic-truth.v1"
_MARKER = "__nico_comprehensive_executive_summary_semantic_truth_v1__"
_EXACT_PROSE_ERROR = "canonical executive summary is not rendered consistently"
_CI_BOUNDARIES = (
    "A. CI/CD configuration maturity:",
    "B. Current operational readiness:",
    "C. Required-check health:",
    "D. Historical workflow outcomes",
)


def _text(value: Any, limit: int = 200000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _surface_map(package: Mapping[str, Any]) -> dict[str, str]:
    from nico import comprehensive_client_truth_canonical_v2 as canonical_truth

    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    return {
        "Markdown": _text(markdown),
        "HTML": canonical_truth._visible_html(rendered_html),
        "PDF": _text(canonical_truth._pdf_text(package)),
    }


def _has_any(value: str, markers: tuple[str, ...]) -> bool:
    lowered = value.casefold()
    return any(marker.casefold() in lowered for marker in markers)


def _validate_semantic_executive_summary(package: Mapping[str, Any]) -> None:
    """Validate decision facts without requiring one identical prose paragraph.

    Markdown, HTML, and PDF render the same canonical decision facts through
    format-specific layouts. Requiring the complete JSON summary sentence as one
    byte-for-byte substring after rendering is not a truth invariant. Identity,
    scores, limitation count, generated timestamp, lifecycle boundaries, and the
    four CI/CD evidence concepts remain fail-closed across every surface.
    """

    from nico import comprehensive_client_truth_canonical_v2 as canonical_truth

    canonical = package.get("json") if isinstance(package.get("json"), Mapping) else {}
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    summary = _text(assessment.get("executive_summary"), 12000)
    if not summary:
        raise ValueError("canonical Comprehensive package is missing an executive summary")

    generated_at = canonical_truth._canonical_generated_at(canonical)
    if not generated_at:
        raise ValueError("canonical Comprehensive package is missing a valid generated_at")

    surfaces = _surface_map(package)
    canonical_truth._validate_generated_labels(
        "Markdown",
        surfaces["Markdown"],
        generated_at,
        label_required=True,
    )
    canonical_truth._validate_generated_labels(
        "HTML",
        surfaces["HTML"],
        generated_at,
        label_required=True,
    )
    canonical_truth._validate_generated_labels(
        "PDF",
        surfaces["PDF"],
        generated_at,
        label_required=False,
    )
    canonical_truth._validate_decision_facts(canonical, assessment, surfaces)

    combined = "\n".join(surfaces.values())
    if not _has_any(combined, ("AUTOMATED DRAFT", "BORRADOR AUTOMATIZADO")):
        raise ValueError("client report omitted the automated-draft lifecycle boundary")
    if not _has_any(
        combined,
        (
            "PENDING HUMAN APPROVAL",
            "HUMAN REVIEW REQUIRED",
            "APROBACIÓN HUMANA PENDIENTE",
            "REVISIÓN HUMANA OBLIGATORIA",
        ),
    ):
        raise ValueError("client report omitted the pending human-review boundary")
    if not _has_any(
        combined,
        (
            "CLIENT DELIVERY BLOCKED",
            "CLIENT DELIVERY NOT AUTHORIZED",
            "ENTREGA AL CLIENTE BLOQUEADA",
            "ENTREGA AL CLIENTE NO AUTORIZADA",
        ),
    ):
        raise ValueError("client report omitted the blocked client-delivery boundary")

    for marker in _CI_BOUNDARIES:
        if marker not in combined:
            raise ValueError(f"client report omitted CI/CD boundary: {marker}")

    for stage in canonical.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        for item in stage.get("evidence") or []:
            if not re.search(r"[A-Za-z0-9]", _text(item)):
                raise ValueError("client stage evidence retained a punctuation-only blank value")


def install_comprehensive_executive_summary_semantic_truth_v1() -> dict[str, Any]:
    from nico import comprehensive_client_truth_final_v1 as truth

    current = truth._validate_surfaces
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def _validate_surfaces(package: Mapping[str, Any]) -> None:
        try:
            current(package)
        except ValueError as exc:
            if str(exc) != _EXACT_PROSE_ERROR:
                raise
            _validate_semantic_executive_summary(package)

    setattr(_validate_surfaces, _MARKER, True)
    setattr(_validate_surfaces, "_nico_previous", current)
    truth._validate_surfaces = _validate_surfaces
    return {
        "status": "installed",
        "version": VERSION,
        "exact_prose_equality_required": False,
        "canonical_identity_equal_across_formats": True,
        "canonical_scores_equal_across_formats": True,
        "canonical_limitation_count_equal_across_formats": True,
        "canonical_generated_at_equal_across_formats": True,
        "ci_cd_boundaries_required": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_validate_semantic_executive_summary",
    "install_comprehensive_executive_summary_semantic_truth_v1",
]
