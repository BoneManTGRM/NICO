from __future__ import annotations

import io

import pytest
from pypdf import PdfReader
from pypdf._page import PageObject
from reportlab.pdfgen import canvas

from nico import comprehensive_commercial_ship_projection_v3 as commercial
from nico import comprehensive_semantic_navigation_v1 as semantic
from nico.report_pdf_text import pdf_text_cache_scope


def _pdf(spanish=False, repository=False):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1, pageCompression=0)
    for heading in ["BORRADOR AUTOMATIZADO" if spanish else "Cover", "Tabla de contenido" if spanish else "Table of Contents",
                    "Auditoría de código" if spanish else "Code Audit",
                    "Repository and Delivery Evidence" if repository else "Source evidence"]:
        pdf.drawString(40, 720, heading)
        pdf.showPage()
    pdf.save()
    return buffer.getvalue()


@pytest.mark.parametrize("spanish", [False, True])
def test_repository_section_inspection_uses_its_exact_toc_stripped_snapshot(monkeypatch, spanish):
    pdf = _pdf(spanish)
    original = semantic.semantic_entry_records
    observations = []
    def inspect(reader, *, page_texts=None):
        assert page_texts is not None
        assert len(page_texts) == len(reader.pages) == 3
        assert page_texts[0].strip() == ("BORRADOR AUTOMATIZADO" if spanish else "Cover")
        assert page_texts[1].strip() == ("Auditoría de código" if spanish else "Code Audit")
        records, locale = original(reader, page_texts=page_texts)
        assert locale is spanish
        assert [(r["section_id"], r["source_page_index"]) for r in records] == [("code_audit", 1)]
        observations.append(page_texts)
        return records, locale
    monkeypatch.setattr(semantic, "semantic_entry_records", inspect)
    monkeypatch.setattr(commercial, "_repository_delivery_stage", lambda canonical: None)
    calls = []
    extract = PageObject.extract_text
    def counted(page, *args, **kwargs):
        calls.append(page)
        return extract(page, *args, **kwargs)
    monkeypatch.setattr(PageObject, "extract_text", counted)
    with pdf_text_cache_scope():
        assert commercial._ensure_repository_delivery_section(pdf, {}) == (pdf, False)
        first = len(calls)
        assert commercial._ensure_repository_delivery_section(pdf, {}) == (pdf, False)
        second = len(calls) - first
    assert len(observations) == 2
    assert observations[0] == observations[1]
    # TOC removal still checks the TOC and first body page on every invocation.
    assert first == 5
    assert second == 2
    assert len(PdfReader(io.BytesIO(pdf)).pages) == 4

def _one_page(heading):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, invariant=1)
    pdf.drawString(40, 720, heading)
    pdf.showPage()
    pdf.save()
    return buffer.getvalue()


def test_recovered_section_uses_new_bytes_and_independent_navigation_identity(monkeypatch):
    pdf = _pdf()
    monkeypatch.setattr(commercial, "_repository_delivery_stage",
                        lambda canonical: {"stage_id": "repository_delivery_evidence"})
    monkeypatch.setattr(commercial, "_render_repository_delivery_supplement",
                        lambda canonical, stage, *, spanish: _one_page("Repository and Delivery Evidence"))
    original = semantic.semantic_entry_records
    populations = []
    def inspected(reader, *, page_texts=None):
        assert page_texts is not None
        assert len(page_texts) == len(reader.pages)
        populations.append(len(page_texts))
        return original(reader, page_texts=page_texts)
    monkeypatch.setattr(semantic, "semantic_entry_records", inspected)
    with pdf_text_cache_scope():
        recovered, changed = commercial._ensure_repository_delivery_section(pdf, {})
    assert changed is True and recovered != pdf
    assert populations == [3, 4]
    records, _ = original(PdfReader(io.BytesIO(recovered)))
    assert [(r["section_id"], r["source_page_index"]) for r in records] == [
        ("code_audit", 1), ("repository_delivery_evidence", 3),
    ]


def test_changed_bytes_with_same_page_count_do_not_reuse_old_text(monkeypatch):
    monkeypatch.setattr(commercial, "_repository_delivery_stage",
                        lambda canonical: {"stage_id": "repository_delivery_evidence"}
                        if canonical.get("requires_repository_stage") else None)
    def unexpected_supplement(*args, **kwargs):
        raise AssertionError("A genuine existing repository section must not be recovered from stale text")
    monkeypatch.setattr(commercial, "_render_repository_delivery_supplement", unexpected_supplement)
    with pdf_text_cache_scope():
        first = commercial._ensure_repository_delivery_section(_pdf(), {})
        second_pdf = _pdf(repository=True)
        second = commercial._ensure_repository_delivery_section(
            second_pdf, {"requires_repository_stage": True},
        )
    assert first[0] != second[0]
    assert len(PdfReader(io.BytesIO(first[0])).pages) == len(PdfReader(io.BytesIO(second_pdf)).pages) == 4
    assert second == (second_pdf, False)


def test_extraction_failure_is_propagated_and_retry_is_revalidated(monkeypatch):
    pdf = _pdf()
    original = commercial.extract_pdf_page_texts
    error = ValueError("synthetic extraction failure")
    with pdf_text_cache_scope():
        monkeypatch.setattr(commercial, "extract_pdf_page_texts",
                            lambda body: (_ for _ in ()).throw(error))
        with pytest.raises(ValueError) as caught:
            commercial._ensure_repository_delivery_section(pdf, {})
        assert caught.value is error
        monkeypatch.setattr(commercial, "extract_pdf_page_texts", original)
        assert commercial._ensure_repository_delivery_section(pdf, {}) == (pdf, False)


def test_parser_stage_timing_distinguishes_cache_lookup_from_parse_without_pdf_body(caplog):
    import json
    import logging

    from nico.report_delivery_timing_v1 import report_delivery_timing
    from nico.report_pdf_text import extract_pdf_page_texts

    pdf = _one_page("PRIVATE_SYNTHETIC_PDF_BODY")
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    with report_delivery_timing("comprun_" + "a" * 32, "en"):
        with pdf_text_cache_scope():
            assert extract_pdf_page_texts(pdf) == extract_pdf_page_texts(pdf)
    records = [json.loads(record.getMessage().split("=", 1)[1])
               for record in caplog.records if record.getMessage().startswith("NICO_REPORT_TIMING=")]
    assert len(records) == 1
    assert records[0]["phases"]["pdf_text_lookup"]["calls"] == 2
    assert records[0]["phases"]["pdf_text_parse"]["calls"] == 1
    assert records[0]["http_transfer_completion_inferred"] is False
    assert "PRIVATE_SYNTHETIC_PDF_BODY" not in caplog.text
