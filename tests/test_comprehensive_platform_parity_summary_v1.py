from __future__ import annotations

import io
from pathlib import Path

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate

from nico import client_report_completion_v2 as completion
from nico import comprehensive_client_ready_projection_v1 as projection
from nico.comprehensive_platform_parity_summary_v1 import (
    canonical_platform_parity_line,
    canonical_platform_parity_status,
    install_comprehensive_platform_parity_summary,
    overlay_platform_parity_summary,
)

ROOT = Path(__file__).resolve().parents[1]


def _pdf() -> bytes:
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    SimpleDocTemplate(buffer, pagesize=letter, invariant=1).build(
        [
            Paragraph("Client Evidence Summary", styles["Heading1"]),
            Paragraph("Existing evidence package content.", styles["BodyText"]),
        ]
    )
    return buffer.getvalue()


def _complete_canonical() -> dict:
    return {
        "stage_results": {
            "platform_parity": {
                "stage_id": "platform_parity",
                "status": "complete",
                "human_evidence_status": "not_assessed",
            }
        }
    }


def _extracted(pdf: bytes) -> str:
    return "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )


def test_platform_parity_status_is_repository_only_when_stage_completed() -> None:
    canonical = _complete_canonical()

    assert canonical_platform_parity_status(canonical) == "complete_repository_only"
    assert canonical_platform_parity_line(canonical, spanish=False) == (
        "Platform Parity: Complete (repository evidence only); "
        "human-context validation: Not assessed - human input required"
    )


def test_unassessed_platform_parity_never_implies_completion() -> None:
    canonical = {"human_evidence_status": "not_assessed"}

    assert canonical_platform_parity_status(canonical) == "not_assessed"
    assert canonical_platform_parity_line(canonical, spanish=False) == (
        "Platform Parity: Not assessed - human input required"
    )


def test_pdf_overlay_retains_layout_page_count_and_canonical_marker() -> None:
    original = _pdf()
    rendered = overlay_platform_parity_summary(
        original,
        _complete_canonical(),
        spanish=False,
    )

    assert len(PdfReader(io.BytesIO(rendered)).pages) == len(
        PdfReader(io.BytesIO(original)).pages
    )
    extracted = _extracted(rendered)
    assert "Platform Parity: Complete (repository evidence only)" in extracted
    assert "Not assessed - human input required" in extracted


def test_spanish_pdf_keeps_localized_and_canonical_labels() -> None:
    rendered = overlay_platform_parity_summary(
        _pdf(),
        _complete_canonical(),
        spanish=True,
    )
    extracted = _extracted(rendered)

    assert "Paridad de plataforma: Completo" in extracted
    assert "Platform Parity: Complete (repository evidence only)" in extracted


def test_installer_binds_projection_and_completion_pdf_aliases() -> None:
    state = install_comprehensive_platform_parity_summary()

    assert state["pdf_bound"] is True
    assert state["completion_pdf_alias_bound"] is True
    assert (
        completion.render_evidence_review_gate_pdf
        is projection.render_evidence_review_gate_pdf
    )


def test_phase17_installs_platform_summary_after_incomplete_metric() -> None:
    source = (
        ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
    ).read_text(encoding="utf-8")

    assert "install_comprehensive_platform_parity_summary" in source
    assert "_PLATFORM_PARITY_SUMMARY" in source
    assert source.index("_INCOMPLETE_ANALYZER_SUMMARY =") < source.index(
        "_PLATFORM_PARITY_SUMMARY ="
    )
    assert source.index("_PLATFORM_PARITY_SUMMARY =") < source.index(
        "_COMPACT_DESIGN_MARKER_GATE ="
    )
    assert '"canonical_platform_parity_summary_retained": True' in source
