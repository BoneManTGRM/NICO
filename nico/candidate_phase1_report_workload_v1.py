from __future__ import annotations

import sys
from functools import wraps
from typing import Any

from nico.candidate_phase1_report_workload_pdf_v1 import (
    VERSION as PDF_VERSION,
    render_phase1_evidence_review_gate_pdf,
)
from nico.candidate_phase1_report_workload_text_v1 import (
    VERSION as TEXT_VERSION,
    rewrite_compact_markdown,
)

VERSION = "nico.candidate-phase1-report-workload.v1"
_PDF_MARKER = "_nico_phase1_workload_pdf_v1"
_MARKDOWN_MARKER = "_nico_phase1_workload_markdown_v1"


def _replace_aliases(name: str, original: Any, replacement: Any) -> None:
    for module in list(sys.modules.values()):
        if module is None:
            continue
        try:
            if getattr(module, name, None) is original:
                setattr(module, name, replacement)
        except Exception:
            continue


def install_phase1_report_workload_patch() -> dict[str, Any]:
    from nico import comprehensive_client_ready_projection_v1 as projection

    current_pdf = projection.render_evidence_review_gate_pdf
    if not getattr(current_pdf, _PDF_MARKER, False):
        replacement_pdf = render_phase1_evidence_review_gate_pdf
        setattr(replacement_pdf, _PDF_MARKER, True)
        setattr(replacement_pdf, "_nico_previous", current_pdf)
        projection.render_evidence_review_gate_pdf = replacement_pdf
        _replace_aliases("render_evidence_review_gate_pdf", current_pdf, replacement_pdf)

    current_markdown = projection.compact_client_markdown
    if not getattr(current_markdown, _MARKDOWN_MARKER, False):
        @wraps(current_markdown)
        def compact_with_workload(existing, canonical, register, *, spanish):
            rendered = current_markdown(existing, canonical, register, spanish=spanish)
            return rewrite_compact_markdown(rendered, canonical, spanish=spanish)

        setattr(compact_with_workload, _MARKDOWN_MARKER, True)
        setattr(compact_with_workload, "_nico_previous", current_markdown)
        projection.compact_client_markdown = compact_with_workload
        _replace_aliases("compact_client_markdown", current_markdown, compact_with_workload)

    return {
        "status": "installed",
        "version": VERSION,
        "pdf_schema": PDF_VERSION,
        "text_schema": TEXT_VERSION,
        "evidence_review_gate_pdf_bound": getattr(projection.render_evidence_review_gate_pdf, _PDF_MARKER, False),
        "compact_client_markdown_bound": getattr(projection.compact_client_markdown, _MARKDOWN_MARKER, False),
        "technical_triage_distinguished_from_human_disposition": True,
        "grouped_review_workload_disclosed": True,
        "human_approval_created": False,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_phase1_report_workload_patch",
    "render_phase1_evidence_review_gate_pdf",
]
