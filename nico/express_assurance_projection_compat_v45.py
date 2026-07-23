from __future__ import annotations

from typing import Any

VERSION = "nico.express_assurance_projection_compat.v45"


def canonical_assurance_label(section: dict[str, Any]) -> str:
    confidence = " ".join(
        str(section.get("presented_confidence") or section.get("confidence") or "").split()
    ).casefold().replace("-", "_").replace(" ", "_")
    if confidence in {"review_limited", "reviewlimited"}:
        return "REVIEW LIMITED"
    if confidence in {"high", "verified"}:
        return "VERIFIED"

    explicit = " ".join(str(section.get("assurance_label") or "").split()).upper()
    if explicit and explicit != "UNVERIFIED":
        return explicit

    status = " ".join(
        str(section.get("assurance_status") or section.get("status") or "").split()
    ).casefold().replace("-", "_").replace(" ", "_")
    if status in {"verified", "complete", "completed", "green"}:
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


def install_express_assurance_projection_compat_v45() -> dict[str, Any]:
    from nico import express_assurance_display_v37 as target

    already = target._assurance_label is canonical_assurance_label
    target._assurance_label = canonical_assurance_label
    return {
        "status": "already_installed" if already else "installed",
        "version": VERSION,
        "retained_confidence_precedes_score_band_status": True,
        "technical_band_does_not_overwrite_assurance": True,
    }


__all__ = [
    "VERSION",
    "canonical_assurance_label",
    "install_express_assurance_projection_compat_v45",
]
