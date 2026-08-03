from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import comprehensive_client_report_render_v60 as client_render
from nico.comprehensive_compact_design_marker_v1 import (
    install_compact_design_marker_gate,
    validate_compact_design_markers,
)

ROOT = Path(__file__).resolve().parents[1]


def _pdf(*lines: str) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    y = 740
    for line in lines:
        document.drawString(48, y, line)
        y -= 18
    document.showPage()
    document.save()
    return output.getvalue()


def _canonical() -> dict:
    return {
        "client_readiness_contract": {
            "analyzer_execution_coverage": 100,
            "coverage_denominator": 9,
            "maturity_label": "Exceptional",
        },
        "incomplete_applicable_analyzers": 0,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _package(*, spanish: bool = False, evidence: bool = True, appendix: bool = False) -> dict:
    if spanish:
        cover = "Evaluación Técnica Integral NICO"
        evidence_marker = "Resumen del paquete de evidencia"
        review = "Puerta de revisión humana y aceptación"
    else:
        cover = "NICO COMPREHENSIVE"
        evidence_marker = "Evidence Package Summary"
        review = "Human Review and Acceptance Gate"
    lines = [
        cover,
        "Canonical Technical Scorecard",
        "Analyzer execution coverage is 100%",
        "Incomplete applicable analyzers: 0",
        "Maturity Exceptional",
        review,
    ]
    if evidence:
        lines.insert(2, evidence_marker)
    if appendix:
        lines.append("Evidence Appendix")
    text = "\n".join(lines)
    return {
        "json": _canonical(),
        "markdown": text,
        "html": f"<main>{text}</main>",
        "pdf_base64": base64.b64encode(_pdf(*lines)).decode("ascii"),
    }


def test_installer_replaces_only_legacy_visual_marker_check() -> None:
    state = install_compact_design_marker_gate()

    assert state["bound"] is True
    assert state["legacy_design_marker_tuple_disabled"] is True
    assert state["retired_evidence_appendix_not_required"] is True
    assert state["compact_evidence_summary_required"] is True
    assert state["score_scanner_maturity_and_identity_delegate_preserved"] is True
    assert client_render._DESIGN_MARKERS == ()


def test_compact_report_passes_without_retired_evidence_appendix() -> None:
    install_compact_design_marker_gate()
    package = _package()

    compact = validate_compact_design_markers(package)
    result = client_render.validate_existing_report_accuracy(package)

    assert compact["compact_design_sections_verified"] is True
    assert compact["retired_evidence_appendix_absent"] is True
    assert result["production_pdf_validated"] is True
    assert result["compact_evidence_summary_verified"] is True
    assert result["retired_evidence_appendix_absent"] is True


def test_spanish_compact_report_uses_localized_marker_groups() -> None:
    install_compact_design_marker_gate()
    package = _package(spanish=True)

    result = client_render.validate_existing_report_accuracy(package)

    observed = result["compact_design_marker_gate"]["observed_design_markers"]
    assert observed["client evidence summary"] == "Resumen del paquete de evidencia"
    assert (
        observed["human review and acceptance gate"]
        == "Puerta de revisión humana y aceptación"
    )


def test_missing_compact_evidence_summary_remains_fail_closed() -> None:
    install_compact_design_marker_gate()

    with pytest.raises(ValueError, match="client evidence summary"):
        client_render.validate_existing_report_accuracy(_package(evidence=False))


def test_retired_raw_evidence_appendix_remains_blocked() -> None:
    install_compact_design_marker_gate()

    with pytest.raises(ValueError, match="retired raw evidence appendix"):
        client_render.validate_existing_report_accuracy(_package(appendix=True))


def test_delegate_still_blocks_scanner_truth_conflicts() -> None:
    install_compact_design_marker_gate()
    package = _package()
    package["markdown"] = package["markdown"].replace("100%", "88%")

    with pytest.raises(ValueError, match="conflicting analyzer coverage"):
        client_render.validate_existing_report_accuracy(package)


def test_phase17_installs_compact_design_marker_gate() -> None:
    source = (
        ROOT / "nico" / "phase17_canonical_artifact_rebuild_v1.py"
    ).read_text(encoding="utf-8")

    assert "install_compact_design_marker_gate" in source
    assert "_COMPACT_DESIGN_MARKER_GATE" in source
    assert '"compact_evidence_summary_design_marker_retained": True' in source
    assert '"retired_raw_evidence_appendix_absent": True' in source
