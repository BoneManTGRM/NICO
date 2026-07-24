from __future__ import annotations

import io
from typing import Any, Callable

from pypdf import PdfReader

VERSION = "nico.express_report_quality.v47.2_qa_gate"
_GATE_MARKER = "_nico_express_report_quality_v472_qa_gate"
_INSTALL_MARKER = "_nico_express_report_quality_v472_durable_install"


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
    from nico import express_report_quality_v47 as quality
    from nico import express_report_visual_qa_v16 as visual

    changed = 0
    current: Callable[[bytes, dict[str, Any]], dict[str, Any]] = dossier.validate_express_pdf
    if not getattr(current, _GATE_MARKER, False):
        base_validator: Callable[[bytes, dict[str, Any]], dict[str, Any]] = getattr(
            current,
            "_nico_base_validator",
            visual.validate_express_pdf,
        )

        def gated_validator(pdf_bytes: bytes, result: dict[str, Any]) -> dict[str, Any]:
            if not _rendered_premium_report(pdf_bytes):
                return base_validator(pdf_bytes, result)
            return current(pdf_bytes, result)

        setattr(gated_validator, _GATE_MARKER, True)
        setattr(gated_validator, "_nico_previous", current)
        setattr(gated_validator, "_nico_base_validator", base_validator)
        dossier.validate_express_pdf = gated_validator
        changed += 1

    quality_install: Callable[[], dict[str, Any]] = quality.install_express_report_quality_v47
    if not getattr(quality_install, _INSTALL_MARKER, False):
        previous_install = quality_install

        def durable_install() -> dict[str, Any]:
            base = previous_install()
            gate = install_express_report_quality_v472_qa_gate()
            return {
                **base,
                "qa_gate_install": gate,
                "version": VERSION,
                "premium_qa_requires_rendered_structure": True,
                "legacy_visual_qa_contract_preserved": True,
            }

        setattr(durable_install, _INSTALL_MARKER, True)
        setattr(durable_install, "_nico_previous", previous_install)
        quality.install_express_report_quality_v47 = durable_install
        changed += 1

    return {
        "status": "installed" if changed else "already_installed",
        "version": VERSION,
        "functions_rebound": changed,
        "premium_checks_require_rendered_premium_structure": True,
        "gate_reapplied_after_every_quality_install": True,
        "legacy_visual_qa_contract_preserved": True,
        "premium_visual_qa_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_express_report_quality_v472_qa_gate",
]
