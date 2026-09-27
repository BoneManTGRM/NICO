from __future__ import annotations

import io
import sys
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from nico import report_pdf_text as text_cache


def _pdf(*pages: str) -> bytes:
    output = io.BytesIO()
    canvas = Canvas(output, invariant=True)
    for text in pages:
        if text:
            canvas.drawString(40, 700, text)
        canvas.showPage()
    canvas.save()
    return output.getvalue()


def _spy_reader(monkeypatch):
    calls = []

    def reader(stream, *args, **kwargs):
        calls.append((stream.getvalue(), args, kwargs))
        return PdfReader(stream, *args, **kwargs)

    monkeypatch.setattr(text_cache, "PdfReader", reader)
    return calls


def test_default_path_is_uncached_and_preserves_original_page_text(monkeypatch):
    pdf = _pdf("first", "", "last")
    expected = tuple(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    calls = _spy_reader(monkeypatch)
    first = text_cache.extract_pdf_page_texts(pdf)
    second = text_cache.extract_pdf_page_texts(pdf)
    assert first == second == expected
    assert len(first) == 3 and first[1] == ""
    assert isinstance(first, tuple)
    assert len(calls) == 2
    assert all(args == () and kwargs == {} for _, args, kwargs in calls)


def test_scope_reuses_equal_exact_bytes_but_not_different_bytes(monkeypatch):
    pdf = _pdf("unchanged")
    equal_pdf = bytes(bytearray(pdf))
    assert equal_pdf == pdf and equal_pdf is not pdf
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        first = text_cache.extract_pdf_page_texts(pdf)
        assert text_cache.extract_pdf_page_texts(equal_pdf) is first
        # One added legal PDF whitespace byte has different exact identity.
        assert text_cache.extract_pdf_page_texts(pdf + b"\n") == first
        assert len(calls) == 2
        with pytest.raises(TypeError):
            first[0] = "changed"


def test_caller_identity_and_review_checks_are_never_cached(monkeypatch):
    pdf = _pdf("run-one pending human approval")
    calls = _spy_reader(monkeypatch)

    def validate(required):
        extracted = "\n".join(text_cache.extract_pdf_page_texts(pdf))
        if required not in extracted:
            raise ValueError("identity missing")
        if "pending human approval" not in extracted:
            raise ValueError("review boundary missing")

    with text_cache.pdf_text_cache_scope():
        validate("run-one")
        with pytest.raises(ValueError, match="identity missing"):
            validate("run-two")
        validate("run-one")
    assert len(calls) == 1


def test_blank_none_pages_and_control_glyph_errors_remain_literal(monkeypatch):
    calls = []

    class Page:
        def __init__(self, text):
            self.text = text

        def extract_text(self, *args, **kwargs):
            assert not args and not kwargs
            calls.append(self.text)
            return self.text

    class Reader:
        pages = [Page(None), Page(""), Page("before\x7fafter")]

    monkeypatch.setattr(text_cache, "PdfReader", lambda stream: Reader())
    with text_cache.pdf_text_cache_scope():
        for _ in range(2):
            pages = text_cache.extract_pdf_page_texts(b"fake reader control")
            assert pages == ("", "", "before\x7fafter")
            with pytest.raises(ValueError, match="control glyph"):
                if "\x7f" in "\n".join(pages):
                    raise ValueError("control glyph")
    assert calls == [None, "", "before\x7fafter"]


def test_malformed_pdf_errors_are_propagated_and_not_cached(monkeypatch):
    calls = _spy_reader(monkeypatch)
    with pytest.raises(Exception) as original:
        PdfReader(io.BytesIO(b"not a PDF"))
    with text_cache.pdf_text_cache_scope():
        for _ in range(2):
            with pytest.raises(type(original.value)) as actual:
                text_cache.extract_pdf_page_texts(b"not a PDF")
            assert str(actual.value) == str(original.value)
        assert not text_cache._ATTEMPT_CACHE.get().entries
    assert len(calls) == 2


def test_partial_extraction_failure_never_retains_prefix(monkeypatch):
    calls = []

    class Page:
        def __init__(self, broken=False):
            self.broken = broken

        def extract_text(self, *args, **kwargs):
            assert args == () and kwargs == {}
            calls.append(self.broken)
            if self.broken:
                raise ValueError("page extraction failed")
            return "complete first page"

    class Reader:
        pages = [Page(), Page(True)]

    monkeypatch.setattr(text_cache, "PdfReader", lambda stream: Reader())
    with text_cache.pdf_text_cache_scope():
        for _ in range(2):
            with pytest.raises(ValueError, match="page extraction failed"):
                text_cache.extract_pdf_page_texts(b"fake reader control")
        assert not text_cache._ATTEMPT_CACHE.get().entries
    assert calls == [False, True, False, True]


def test_scope_reset_exception_cleanup_and_fresh_attempt(monkeypatch):
    pdf = _pdf("scope")
    calls = _spy_reader(monkeypatch)
    assert text_cache._ATTEMPT_CACHE.get() is None
    with pytest.raises(RuntimeError, match="end attempt"):
        with text_cache.pdf_text_cache_scope():
            retained_cache = text_cache._ATTEMPT_CACHE.get()
            text_cache.extract_pdf_page_texts(pdf)
            assert retained_cache.entries
            raise RuntimeError("end attempt")
    assert text_cache._ATTEMPT_CACHE.get() is None
    assert not retained_cache.entries and retained_cache.retained_bytes == 0
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(pdf)
    text_cache.extract_pdf_page_texts(pdf)
    assert len(calls) == 3


def test_nested_scope_restores_outer_cache_without_sharing_entries(monkeypatch):
    pdf = _pdf("nested")
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        outer = text_cache._ATTEMPT_CACHE.get()
        pages = text_cache.extract_pdf_page_texts(pdf)
        with text_cache.pdf_text_cache_scope():
            inner = text_cache._ATTEMPT_CACHE.get()
            assert inner is not outer
            assert text_cache.extract_pdf_page_texts(pdf) == pages
        assert not inner.entries
        assert text_cache._ATTEMPT_CACHE.get() is outer
        assert text_cache.extract_pdf_page_texts(pdf) is pages
    assert len(calls) == 2


def test_copied_context_cannot_repopulate_a_closed_attempt(monkeypatch):
    pdf = _pdf("closed scope")
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        cache = text_cache._ATTEMPT_CACHE.get()
        text_cache.extract_pdf_page_texts(pdf)
        context = copy_context()
    for _ in range(2):
        context.run(text_cache.extract_pdf_page_texts, pdf)
    assert not cache.entries and cache.retained_bytes == 0
    assert len(calls) == 3


def test_threads_do_not_share_cache_even_when_context_is_copied(monkeypatch):
    pdf = _pdf("thread")
    calls = _spy_reader(monkeypatch)

    def worker():
        with text_cache.pdf_text_cache_scope():
            first = text_cache.extract_pdf_page_texts(pdf)
            assert text_cache.extract_pdf_page_texts(pdf) is first
        return first

    with text_cache.pdf_text_cache_scope():
        outer = text_cache.extract_pdf_page_texts(pdf)
        context = copy_context()
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(text_cache.extract_pdf_page_texts, pdf).result() == outer
            assert pool.submit(context.run, text_cache.extract_pdf_page_texts, pdf).result() == outer
            assert pool.submit(worker).result() == outer
        assert text_cache.extract_pdf_page_texts(pdf) is outer
    assert len(calls) == 4


def test_lru_cache_evicts_oldest_not_recently_reused_entry(monkeypatch):
    pdfs = [_pdf(str(number)) for number in range(5)]
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        for pdf in pdfs[:4]:
            text_cache.extract_pdf_page_texts(pdf)
        text_cache.extract_pdf_page_texts(pdfs[0])
        text_cache.extract_pdf_page_texts(pdfs[4])
        cache = text_cache._ATTEMPT_CACHE.get()
        assert len(cache.entries) == 4
        assert pdfs[0] in cache.entries and pdfs[1] not in cache.entries
        text_cache.extract_pdf_page_texts(pdfs[1])
    assert len(calls) == 6


def test_retained_size_includes_python_pdf_page_tuple_and_text_storage(monkeypatch):
    pdf = _pdf("size á")
    with text_cache.pdf_text_cache_scope():
        pages = text_cache.extract_pdf_page_texts(pdf)
        expected = sys.getsizeof(pdf) + sys.getsizeof(pages) + sum(sys.getsizeof(page) for page in pages)
        cache = text_cache._ATTEMPT_CACHE.get()
        assert cache.retained_bytes == expected
        assert cache.entries[pdf].retained_bytes == expected
        assert cache.retained_bytes <= 16 * 1024 * 1024


def test_same_key_replacement_and_concurrent_accounting_stay_consistent():
    cache = text_cache._AttemptCache()
    cache.put(b"pdf", ("first",))
    cache.put(b"pdf", ("second",))
    assert len(cache.entries) == 1
    assert cache.retained_bytes == sum(entry.retained_bytes for entry in cache.entries.values())

    def worker(number):
        for offset in range(20):
            pdf = str((number + offset) % 6).encode()
            cache.put(pdf, (str(offset), ""))
            cache.get(pdf)

    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(worker, range(4)))
    assert len(cache.entries) <= 4
    assert cache.retained_bytes == sum(entry.retained_bytes for entry in cache.entries.values())
    assert cache.retained_bytes <= 16 * 1024 * 1024


def test_size_budget_evicts_and_oversized_entries_still_extract_in_full(monkeypatch):
    first, second = _pdf("one"), _pdf("two")
    pages = text_cache.extract_pdf_page_texts(first)
    size = sys.getsizeof(first) + sys.getsizeof(pages) + sum(sys.getsizeof(page) for page in pages)
    monkeypatch.setattr(text_cache, "_MAX_RETAINED_BYTES", size + 30)
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(first)
        text_cache.extract_pdf_page_texts(second)
        cache = text_cache._ATTEMPT_CACHE.get()
        assert len(cache.entries) == 1 and first not in cache.entries
        assert cache.retained_bytes <= size + 30
        oversized = _pdf("complete content " * 10)
        expected = tuple(page.extract_text() or "" for page in PdfReader(io.BytesIO(oversized)).pages)
        assert text_cache.extract_pdf_page_texts(oversized) == expected
        assert text_cache.extract_pdf_page_texts(oversized) == expected
        assert oversized not in cache.entries
    assert len(calls) == 4


def test_mutable_buffer_and_bytes_subclasses_keep_uncached_behavior(monkeypatch):
    class CustomBytes(bytes):
        def __hash__(self):
            raise AssertionError("custom hash must not run")

    pdf = _pdf("buffer")
    expected = text_cache.extract_pdf_page_texts(pdf)
    calls = _spy_reader(monkeypatch)
    with text_cache.pdf_text_cache_scope():
        for value in (bytearray(pdf), CustomBytes(pdf)):
            assert text_cache.extract_pdf_page_texts(value) == expected
            assert text_cache.extract_pdf_page_texts(value) == expected
        assert not text_cache._ATTEMPT_CACHE.get().entries
    assert len(calls) == 4
