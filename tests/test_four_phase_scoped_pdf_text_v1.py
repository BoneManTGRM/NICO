from __future__ import annotations

import io

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject

from nico.comprehensive_four_phase_pdf_v1 import assert_four_phase_pdf
from nico.comprehensive_four_phase_report_v1 import apply_four_phase_pdf, apply_four_phase_program
from nico.report_pdf_text import extract_pdf_page_texts, pdf_text_cache_scope
from tests.test_comprehensive_four_phase_report_v1 import _canonical, _pdf


@pytest.mark.parametrize("language", ("en", "es-MX"))
def test_repeated_four_phase_validation_reuses_text_of_exact_bytes(language, monkeypatch):
    canonical = apply_four_phase_program(_canonical(language=language))
    body = apply_four_phase_pdf(_pdf(), canonical)
    expected = assert_four_phase_pdf(body, canonical)
    calls = 0
    original = PageObject.extract_text
    def counted(self, *args, **kwargs):
        nonlocal calls
        calls += 1
        return original(self, *args, **kwargs)
    with pdf_text_cache_scope():
        extract_pdf_page_texts(body)
        monkeypatch.setattr(PageObject, "extract_text", counted)
        assert assert_four_phase_pdf(body, canonical) == expected
        assert assert_four_phase_pdf(body, canonical) == expected
    assert calls == 0


def test_warm_text_does_not_authorize_missing_matrix_or_changed_bytes():
    canonical = apply_four_phase_program(_canonical())
    valid = apply_four_phase_pdf(_pdf(), canonical)
    changed = _pdf()
    with pdf_text_cache_scope():
        assert_four_phase_pdf(valid, canonical)
        extract_pdf_page_texts(changed)
        with pytest.raises(ValueError, match="table-of-contents publication omitted"):
            assert_four_phase_pdf(changed, canonical)


def test_warm_text_keeps_missing_bookmark_rejection():
    canonical = apply_four_phase_program(_canonical())
    valid = apply_four_phase_pdf(_pdf(), canonical)
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(valid)).pages:
        writer.add_page(page)
    stream = io.BytesIO()
    writer.write(stream)
    without_bookmarks = stream.getvalue()
    with pdf_text_cache_scope():
        extract_pdf_page_texts(without_bookmarks)
        with pytest.raises(ValueError, match="bookmarks omitted"):
            assert_four_phase_pdf(without_bookmarks, canonical)


def test_warm_text_keeps_duplicate_matrix_rejection():
    canonical = apply_four_phase_program(_canonical())
    valid = apply_four_phase_pdf(_pdf(), canonical)
    reader = PdfReader(io.BytesIO(valid))
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    writer.add_page(reader.pages[1])
    stream = io.BytesIO()
    writer.write(stream)
    duplicate = stream.getvalue()
    with pdf_text_cache_scope():
        extract_pdf_page_texts(duplicate)
        with pytest.raises(ValueError, match="matrix must appear exactly once"):
            assert_four_phase_pdf(duplicate, canonical)


def test_cached_text_page_population_must_match_fresh_pdf_reader(monkeypatch):
    from nico import comprehensive_four_phase_pdf_v1 as four_phase
    canonical = apply_four_phase_program(_canonical())
    valid = apply_four_phase_pdf(_pdf(), canonical)
    monkeypatch.setattr(four_phase, "extract_pdf_page_texts", lambda _: ("forged single page",))
    with pytest.raises(ValueError, match="page population"):
        four_phase.assert_four_phase_pdf(valid, canonical)


@pytest.mark.parametrize("changed", ("phase_title", "locale"))
def test_warm_exact_bytes_do_not_reuse_a_canonical_validation_verdict(changed):
    from copy import deepcopy
    canonical = apply_four_phase_program(_canonical())
    valid = apply_four_phase_pdf(_pdf(), canonical)
    requirements = deepcopy(canonical)
    with pdf_text_cache_scope():
        assert_four_phase_pdf(valid, canonical)
        if changed == "phase_title":
            requirements["four_phase_program"]["phases"][0]["title_en"] = "Absent required phase title"
            action = lambda: assert_four_phase_pdf(valid, requirements)
        else:
            action = lambda: assert_four_phase_pdf(valid, requirements, spanish=True)
        with pytest.raises(ValueError, match="table-of-contents publication omitted"):
            action()
