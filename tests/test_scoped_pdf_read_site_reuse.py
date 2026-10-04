"""Scoped reuse at measured PDF read sites, with fresh validation and legacy failures."""
from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader
from pypdf._page import PageObject
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import client_pdf_status_sanitizer_v1 as sanitizer
from nico import comprehensive_artifact_manifest_approval_v1 as manifest
from nico import comprehensive_client_report_render_v60 as accuracy
from nico import comprehensive_commercial_ship_projection_v1 as limitations
from nico import comprehensive_pdf_reflow_v1 as reflow
from nico import comprehensive_report_clarity_v1 as clarity
from nico import report_pdf_text as text_cache


def _pdf(*pages: tuple[str, ...]) -> bytes:
    output = io.BytesIO()
    document = canvas.Canvas(output, pagesize=letter, invariant=1)
    for lines in pages:
        for index, line in enumerate(lines):
            document.drawString(45, 740 - index * 16, line)
        document.showPage()
    document.save()
    return output.getvalue()


def _manifest_pdf(*, valid: bool = True) -> bytes:
    return _pdf(
        (("Client Artifact Manifest" if valid else "Different retained section"),
         "Retained structured artifacts", "SHA-256", "a" * 64),
        ("Human Review and Exact-Artifact Approval Record", "Human approval pending"),
    )


def _consume(kind: str, pdf: bytes):
    if kind == "sanitizer":
        return sanitizer.sanitize_client_pdf_status(pdf)
    if kind == "clarity":
        return clarity._combined_text({}, "", "", pdf)
    if kind == "accuracy":
        return accuracy.validate_existing_report_accuracy(
            {"pdf_base64": base64.b64encode(pdf).decode("ascii"), "json": {}}
        )
    if kind == "manifest":
        return manifest._refresh_visible_manifest(pdf, {}, [{"sha256": "a" * 64}])
    if kind == "limitations":
        return limitations.compact_sparse_limitation_pages(pdf)
    if kind == "reflow":
        return reflow.compact_sparse_stage_pages(pdf)
    raise AssertionError(kind)


@pytest.mark.parametrize("kind", ("sanitizer", "clarity", "accuracy", "manifest", "limitations", "reflow"))
def test_cached_text_is_reused_without_changing_consumer_output(kind, monkeypatch):
    pdf = _manifest_pdf() if kind == "manifest" else _pdf(
        ("Executive Decision Brief", "Owned public fixture sentinel zero"),
        ("Human Review and Acceptance Gate", "Human approval remains pending"),
    )
    expected = _consume(kind, pdf)
    calls = []
    original = PageObject.extract_text

    def extract(page, *args, **kwargs):
        calls.append(1)
        return original(page, *args, **kwargs)

    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(pdf)
        monkeypatch.setattr(PageObject, "extract_text", extract)
        actual = _consume(kind, pdf)
    assert actual == expected
    assert calls == [], "The same exact bytes were already completely extracted"


def test_changed_same_population_text_is_not_reused():
    first = _pdf(("Executive Decision Brief", "Owned sentinel zero"),
                 ("Human Review and Acceptance Gate",))
    second = _pdf(("Executive Decision Brief", "Owned sentinel one"),
                  ("Human Review and Acceptance Gate",))
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(first)
        actual = _consume("clarity", second)
    assert "Owned sentinel one" in actual
    assert "Owned sentinel zero" not in actual


def test_changed_canonical_truth_is_rejected_despite_warm_pdf_text():
    pdf = _pdf(("Analyzer execution coverage: 0%",),
               ("Human Review and Acceptance Gate",))
    package = {"pdf_base64": base64.b64encode(pdf).decode("ascii"),
               "json": {"analyzer_execution_coverage": 0}}
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(pdf)
        observed = accuracy.validate_existing_report_accuracy(package)
        assert observed["canonical_coverage_value"] == 0
        assert observed["client_delivery_allowed"] is False
        package["json"]["analyzer_execution_coverage"] = 1
        with pytest.raises(ValueError, match="conflicting analyzer coverage"):
            accuracy.validate_existing_report_accuracy(package)


def test_changed_same_population_internal_page_is_still_removed():
    first = _pdf(("Executive Decision Brief",),
                 ("Human Review and Acceptance Gate",))
    second = _pdf(("report_contract_reason: fixture internal diagnostic",),
                  ("Human Review and Acceptance Gate",))
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(first)
        result = sanitizer.sanitize_client_pdf_status(second)
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 1
    assert "Human Review and Acceptance Gate" in (reader.pages[0].extract_text() or "")


def test_changed_same_population_manifest_identity_is_still_rejected():
    with text_cache.pdf_text_cache_scope():
        first = _manifest_pdf()
        text_cache.extract_pdf_page_texts(first)
        assert _consume("manifest", first) == first
        with pytest.raises(ValueError, match="cannot be identified uniquely"):
            _consume("manifest", _manifest_pdf(valid=False))


@pytest.mark.parametrize("kind", ("limitations", "reflow"))
def test_compaction_of_changed_bytes_preserves_independent_source_expectations(kind):
    from tests.test_comprehensive_commercial_ship_projection_v1 import (
        _pdf_with_sparse_limitation_pair, _pdf_with_sparse_ordinary_sections,
    )
    changed = (_pdf_with_sparse_limitation_pair() if kind == "limitations"
               else _pdf_with_sparse_ordinary_sections())
    population = len(PdfReader(io.BytesIO(changed)).pages)
    original = _pdf(*(("Executive Decision Brief", "Do not compact this page"),) * population)
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(original)
        output, observed = _consume(kind, changed)
    assert observed["original_pages"] == population
    assert observed["pages_removed"] >= 1
    assert observed["truth_preserved"] is True
    rendered = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(output)).pages)
    expected = ("Validated roadmap evidence was not supplied." if kind == "limitations"
                else "Review-required dependency candidates: 21.")
    assert expected in rendered
    assert "Human Review and Acceptance Gate" in rendered


@pytest.mark.parametrize("kind,module", (("limitations", limitations), ("reflow", reflow)))
def test_partial_extraction_failure_keeps_original_per_page_fallback(kind, module, monkeypatch):
    pdf = _pdf(("Executive Decision Brief", "Readable first page"),
               ("Owned deliberately unreadable second page",))
    original = PageObject.extract_text
    calls = []
    parser_attempts = []
    original_parse = text_cache._parse_pdf_page_texts

    def parse(data):
        parser_attempts.append(1)
        return original_parse(data)

    monkeypatch.setattr(text_cache, "_parse_pdf_page_texts", parse)

    def extract(page, *args, **kwargs):
        if str(page.get("/V11Unreadable") or "") == "yes":
            calls.append("failed")
            raise ValueError("owned extraction fixture failure")
        return original(page, *args, **kwargs)

    reader = PdfReader(io.BytesIO(pdf))
    from pypdf import PdfWriter
    from pypdf.generic import NameObject, TextStringObject
    reader.pages[1][NameObject("/V11Unreadable")] = TextStringObject("yes")
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    broken = output.getvalue()
    monkeypatch.setattr(PageObject, "extract_text", extract)
    with text_cache.pdf_text_cache_scope():
        for _ in range(2):
            result, observed = _consume(kind, broken)
            assert result == broken
            assert observed["status"] == "unchanged"
            assert observed["truth_preserved"] is True
    assert len(calls) >= 2, "A failed extraction must be retried, never retained as complete text"
    assert parser_attempts == [1, 1], "Both requests must retry the real failed parser"


@pytest.mark.parametrize("snapshot_count", (1, 3))
@pytest.mark.parametrize("kind,module", (("limitations", limitations), ("reflow", reflow)))
def test_incomplete_snapshot_falls_back_to_fresh_page_population(kind, module, snapshot_count, monkeypatch):
    pdf = _pdf(("Executive Decision Brief", "Independent source first"),
               ("Human Review and Acceptance Gate", "Independent source second"))
    seen = []
    original = module._page_text
    monkeypatch.setattr(module, "extract_pdf_page_texts",
                        lambda data: ("wrong snapshot",) * snapshot_count)

    def page_text(page):
        value = original(page)
        seen.append(value)
        return value

    monkeypatch.setattr(module, "_page_text", page_text)
    result, observed = _consume(kind, pdf)
    assert result == pdf
    assert observed["original_pages"] == 2
    assert observed["status"] == "unchanged"
    assert len(seen) == 2
    assert "Independent source second" in seen[1]


@pytest.mark.parametrize("snapshot_count", (1, 3))
@pytest.mark.parametrize("kind,module", (("sanitizer", sanitizer), ("clarity", clarity),
                                        ("accuracy", accuracy), ("manifest", manifest)))
def test_validator_rejects_short_or_long_snapshot(kind, module, snapshot_count, monkeypatch):
    pdf = _manifest_pdf() if kind == "manifest" else _pdf(
        ("Executive Decision Brief",), ("Human Review and Acceptance Gate",),
    )
    monkeypatch.setattr(module, "extract_pdf_page_texts",
                        lambda data: ("wrong snapshot",) * snapshot_count)
    with pytest.raises(ValueError, match="text population mismatch"):
        _consume(kind, pdf)


def test_warm_text_preserves_literal_evidence_and_rechecks_page_marker():
    from pypdf import PdfWriter
    from pypdf.generic import BooleanObject, NameObject
    raw = _pdf(("report_contract_reason: quoted supplier evidence",
                "FINAL REPORT PENDING HUMAN APPROVAL"),
               ("Human Review and Acceptance Gate",))
    reader = PdfReader(io.BytesIO(raw))
    reader.pages[0][NameObject("/NICOSuppliedEvidence")] = BooleanObject(True)
    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    buffer = io.BytesIO()
    writer.write(buffer)
    literal = buffer.getvalue()
    with text_cache.pdf_text_cache_scope():
        text_cache.extract_pdf_page_texts(literal)
        preserved = sanitizer.sanitize_client_pdf_status(literal)
        unmarked = sanitizer.sanitize_client_pdf_status(raw)
    kept = PdfReader(io.BytesIO(preserved))
    assert len(kept.pages) == 2
    assert bool(kept.pages[0].get("/NICOSuppliedEvidence"))
    quoted = kept.pages[0].extract_text() or ""
    assert "report_contract_reason: quoted supplier evidence" in quoted
    assert "FINAL REPORT PENDING HUMAN APPROVAL" in quoted
    assert len(PdfReader(io.BytesIO(unmarked)).pages) == 1
