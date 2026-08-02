from __future__ import annotations

import base64
import io
from pathlib import Path

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_client_report_render_v60 import (
    _assert_client_ready_surfaces,
    _client_projection,
    _strip_redundant_pdf_pages,
    install_comprehensive_client_report_render_v60,
)

ROOT = Path(__file__).resolve().parents[1]


def _pdf(*pages: str) -> bytes:
    stream = io.BytesIO()
    writer = canvas.Canvas(stream, pagesize=letter, invariant=1)
    for text in pages:
        writer.drawString(72, 720, text)
        writer.showPage()
    writer.save()
    return stream.getvalue()


def test_client_projection_moves_superseded_contract_diagnostics_out_of_stage_truth() -> None:
    canonical = {
        "human_review_required": True,
        "client_delivery_allowed": False,
        "stage_summaries": [
            {
                "stage_id": "decision_report_generation",
                "status": "complete",
                "report_contract_status": "blocked",
                "report_contract_reason": "executive_decision_brief_page_gate_failed",
                "core_artifact_generation_complete": True,
            }
        ],
    }

    projected = _client_projection(canonical)
    stage = projected["stage_summaries"][0]

    assert "report_contract_status" not in stage
    assert "report_contract_reason" not in stage
    assert stage["pre_finalization_diagnostics"] == {
        "report_contract_status": "blocked",
        "report_contract_reason": "executive_decision_brief_page_gate_failed",
    }
    assert stage["final_publication_contract_status"] == "reconciled_and_revalidated"
    assert projected["client_readiness_contract"][
        "rendered_from_final_reconciled_canonical_truth"
    ] is True
    assert projected["human_review_required"] is True
    assert projected["client_delivery_allowed"] is False


def test_redundant_nico_code_summary_pages_are_removed_before_final_register() -> None:
    original = _pdf(
        "Executive Decision Brief",
        "NICO-CODE-A33EF80F5728 legacy duplicate summary",
        "Evidence Appendix",
    )
    stripped = _strip_redundant_pdf_pages(original)
    texts = [page.extract_text() or "" for page in PdfReader(io.BytesIO(stripped)).pages]

    assert len(texts) == 2
    assert all("NICO-CODE-" not in text for text in texts)
    assert "Executive Decision Brief" in texts[0]
    assert "Evidence Appendix" in texts[1]


def test_client_ready_surface_validation_rejects_production_report_regressions() -> None:
    package = {
        "markdown": (
            "## Finding and Remediation Register\n"
            "- Completed applicable analyzers: 9\n"
            "- Incomplete applicable analyzers: 0\n"
            "- Analyzer execution coverage is 88%\n"
        ),
        "html": "<h2>Finding and Remediation Register</h2>",
        "pdf_base64": base64.b64encode(
            _pdf("Finding and Remediation Register")
        ).decode("ascii"),
    }

    with pytest.raises(ValueError, match="superseded truth"):
        _assert_client_ready_surfaces(package)


def test_final_runtime_binds_v60_after_v59_and_before_scoring() -> None:
    source = (
        ROOT / "nico" / "comprehensive_mobile_score_projection_v2.py"
    ).read_text(encoding="utf-8")

    readiness = source.index("install_comprehensive_client_readiness_v59()")
    render = source.index("install_comprehensive_client_report_render_v60()")
    scoring = source.index("install_comprehensive_scoring_manifest_v54()")

    assert readiness < render < scoring
    assert '"premium_core_rebuilt_after_reconciliation": True' in source
    assert '"production_pdf_is_acceptance_artifact": True' in source
    assert '"single_detailed_register_enforced": True' in source


def test_v60_installer_binds_real_finalizer() -> None:
    from nico import client_report_completion_v2 as completion

    result = install_comprehensive_client_report_render_v60()

    assert result["status"] in {"installed", "already_installed"}
    assert result["bound"] is True
    assert getattr(
        completion.finalize_client_report_package,
        "_nico_comprehensive_client_report_render_v60",
        False,
    ) is True
