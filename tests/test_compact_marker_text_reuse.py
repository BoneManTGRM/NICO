"""Owned valid PDFs isolate repeated marker reads; no production report claim."""
from __future__ import annotations
import base64
import io
import pytest
from pypdf import PdfReader
from pypdf._page import PageObject
from reportlab.pdfgen import canvas
from nico import comprehensive_compact_design_marker_v1 as marker
from nico.report_pdf_text import extract_pdf_page_texts, pdf_text_cache_scope

def _pdf(lines=("Owned cover", "", "Owned evidence summary")):
    out = io.BytesIO()
    pdf = canvas.Canvas(out, invariant=1, pageCompression=0)
    for index, line in enumerate(lines):
        pdf.setPageSize((420 + index, 620))
        if line: pdf.drawString(36, 580, line)
        pdf.showPage()
    pdf.save()
    return out.getvalue()

def _package(raw):
    return {"pdf_base64": base64.b64encode(raw).decode("ascii"), "markdown": "", "html": ""}

def test_retired_marker_warm_read_reuses_complete_same_byte_text(monkeypatch):
    raw = _pdf()
    calls = []
    original = PageObject.extract_text
    def observed(page, *args, **kwargs):
        calls.append(int(page.mediabox.width))
        return original(page, *args, **kwargs)
    monkeypatch.setattr(PageObject, "extract_text", observed)
    with pdf_text_cache_scope():
        assert extract_pdf_page_texts(raw) == ("Owned cover\n", "", "Owned evidence summary\n")
        calls.clear()
        assert marker._retired_appendix_section_present(_package(raw)) is False
        assert calls == [], "The preceding compact text validation already extracted these exact bytes"

def test_retired_marker_changed_pdf_never_reuses_clean_verdict(monkeypatch):
    first = _pdf()
    changed = _pdf(("Owned cover", "", "Evidence Appendix"))
    with pdf_text_cache_scope():
        extract_pdf_page_texts(first)
        assert marker._retired_appendix_section_present(_package(first)) is False
        assert marker._retired_appendix_section_present(_package(changed)) is True
    assert first != changed

@pytest.mark.parametrize("texts", [(), ("owned",)*4])
def test_wrong_snapshot_cardinality_independently_reads_real_pages(monkeypatch, texts):
    raw = _pdf(("Owned cover", "", "Evidence Appendix"))
    monkeypatch.setattr(marker, "extract_pdf_page_texts", lambda unused: texts)
    assert marker._retired_appendix_section_present(_package(raw)) is True

def test_early_retired_heading_keeps_legacy_result_if_later_extraction_fails(monkeypatch):
    raw = _pdf(("Evidence Appendix", "Owned unreadable later page", "Owned last page"))
    original = PageObject.extract_text
    def observed(page, *args, **kwargs):
        if int(page.mediabox.width) == 421:
            raise RuntimeError("owned later page failure")
        return original(page, *args, **kwargs)
    monkeypatch.setattr(PageObject, "extract_text", observed)
    with pdf_text_cache_scope():
        assert marker._retired_appendix_section_present(_package(raw)) is True

def test_extraction_failure_before_any_heading_still_propagates_and_does_not_cache(monkeypatch):
    raw = _pdf()
    original = PageObject.extract_text
    def failing(page, *args, **kwargs):
        raise RuntimeError("owned first page failure")
    monkeypatch.setattr(PageObject, "extract_text", failing)
    with pdf_text_cache_scope():
        with pytest.raises(RuntimeError, match="owned first page failure"):
            marker._retired_appendix_section_present(_package(raw))
        monkeypatch.setattr(PageObject, "extract_text", original)
        assert marker._retired_appendix_section_present(_package(raw)) is False

@pytest.mark.parametrize("key, value", [
    ("markdown", "# Evidence Appendix"),
    ("html", "<h2>Apéndice de evidencia</h2>"),
])
def test_non_pdf_retired_heading_keeps_original_early_return(key, value):
    package = {"pdf_base64": "not-decodable", key: value}
    assert marker._retired_appendix_section_present(package) is True

def test_cached_retired_heading_is_still_rejected_in_real_marker_validator():
    raw = _pdf(("NICO COMPREHENSIVE", "Evidence Appendix", "Human Review and Acceptance Gate"))
    package = _package(raw)
    package["markdown"] = "NICO COMPREHENSIVE\nEvidence Package Summary\nHuman Review and Acceptance Gate"
    with pdf_text_cache_scope():
        extract_pdf_page_texts(raw)
        with pytest.raises(ValueError, match="retired raw evidence appendix"):
            marker.validate_compact_design_markers(package)
