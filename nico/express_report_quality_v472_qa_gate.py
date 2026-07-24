from __future__ import annotations

import io
from typing import Any, Callable

from pypdf import PdfReader

VERSION = "nico.express_report_quality.v47.2_qa_gate"


def _rendered_premium_report(pdf_bytes: bytes) -> bool:
    text = "\n".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(io.BytesIO(pdf_bytes)).pages
    )
    return (
        "Technical Score and Evidence Assurance" in text
        and "Score Contribution and Assurance Constraints" in text
    )


def install_express_report_quality_v472_qa_gate() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as dossier
    from nico import express_report_visual_qa_v16 as visual

    current: Callable[[bytes, dict[str, Any]], dict[str, Any]] = dossier.validate_express_pdf
    if getattr(current, "_nico_express_report_quality_v472_qa_gate", False):
        return {"status": "already_installed", "version": VERSION}

    base_validator: Callable[[bytes, dict[str, Any]], dict[str, Any]] = getattr(
        current,
        "_nico_base_validator",
        visual.validate_express_pdf,
    )

    def gated_validator(pdf_bytes: bytes, result: dict[str, Any]) -> dict[str, Any]:
        if not _rendered_premium_report(pdf_bytes):
            return base_validator(pdf_bytes, result)
        return current(pdf_bytes, result)

    setattr(gated_validator, "_nico_express_report_quality_v472_qa_gate", True)
    setattr(gated_validator, "_nico_previous", current)
    setattr(gated_validator, "_nico_base_validator", base_validator)
    dossier.validate_express_pdf = gated_validator
    return {
        "status": "installed",
        "version": VERSION,
        "premium_checks_require_rendered_premium_structure": True,
        "legacy_visual_qa_contract_preserved": True,
        "premium_visual_qa_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_report_quality_v472_qa_gate",
]
