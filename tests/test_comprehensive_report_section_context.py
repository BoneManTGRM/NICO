"""Physical-page regressions for the two self-assessment layout defects."""
import base64
from copy import deepcopy
import io

from pypdf import PdfReader

from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
from nico.comprehensive_report_package import _pdf
from nico.client_pdf_status_sanitizer_v1 import _drop_internal_page


def test_oversized_briefing_keeps_chapter_and_continuation_context():
    install_comprehensive_pdf_embedded_fonts_v1()
    identity = {"repository": "owned/layout", "run_id": "owned-layout", "commit_sha": "a" * 40}
    assessment = {"score": 93, "sections": [], "human_review_required": True,
                  "client_delivery_allowed": False}
    findings = [f"P1 · ITEM-{i:02d} · " + "Review the retained source and preserve behavior. " * 12
                for i in range(12)]
    stages = [{"stage_id": "risk_reduction_and_executive_briefing",
               "title": "Risk Reduction and Executive Briefing", "status": "review_required",
               "summary": "Automated priorities remain pending human disposition.",
               "evidence": [], "findings": findings, "unavailable": []},
              {"stage_id": "six_month_roadmap", "title": "Six-Month Roadmap",
               "status": "framework_only", "summary": "Planning awaits human review.",
               "evidence": [], "findings": [], "unavailable": []}]
    before = deepcopy((identity, assessment, stages))
    encoded, error, _ = _pdf(identity, assessment, stages, "2026-09-28T16:26:11Z")
    assert error is None
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(encoded))).pages]
    chapter_pages = [p for p in pages if "Roadmap, Resourcing, and Decision" in p]
    assert len(chapter_pages) == 1
    assert "Risk Reduction and Executive Briefing" in chapter_pages[0]
    assert "ITEM-00" in chapter_pages[0]
    appendix = next(i for i, p in enumerate(pages) if "Evidence Appendix" in p)
    finding_pages = [p for p in pages[appendix + 1:] if "ITEM-" in p]
    assert len(finding_pages) > 1
    assert all("Risk Reduction and Executive Briefing" in p for p in finding_pages)
    assert all(not _drop_internal_page(p) for p in finding_pages)
    # The client composer classifies whole pages: distinct appendix stages must
    # retain their page boundary even when a briefing continuation is short.
    assert "Six-Month Roadmap" not in finding_pages[-1]
    for i in range(12):
        assert "\n".join(finding_pages).count(f"ITEM-{i:02d}") == 1
    assert (identity, assessment, stages) == before
