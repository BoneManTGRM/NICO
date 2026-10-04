from __future__ import annotations

from types import SimpleNamespace
import io
from pypdf import PdfReader
from reportlab.pdfgen import canvas

import pytest

from nico import comprehensive_semantic_navigation_v1 as navigation


def _reference_section_for_line(raw_line):
    # Preserved pre-index algorithm; normalization and aliases are shared.
    candidate, numbered = navigation._heading_candidate(raw_line)
    if not candidate:
        return None
    for section in navigation._canonical_sections():
        if any(
            navigation._visible_heading_match(candidate, alias)
            for alias in navigation._section_aliases(section)
        ):
            return section, numbered
    return None


def _identity(result):
    return None if result is None else (result[0]["section_id"], result[1])


def _reader(lines):
    return SimpleNamespace(pages=[
        SimpleNamespace(extract_text=lambda: "Unbranded cover"),
        SimpleNamespace(extract_text=lambda: "\n".join(lines)),
    ])


def test_alias_preparation_occurs_once_per_section_per_navigation_call(monkeypatch):
    original = navigation._section_aliases
    calls = []
    def counted(section):
        calls.append(section["section_id"])
        return original(section)
    monkeypatch.setattr(navigation, "_section_aliases", counted)
    heading = navigation.CANONICAL_TOC_SECTIONS[1]["title_en"]
    navigation.semantic_entry_records(_reader(["ordinary body text"] * 40 + [heading]))
    assert len(calls) == len(navigation.CANONICAL_TOC_SECTIONS)


def test_bilingual_headings_aliases_and_near_prefixes_keep_original_recognition():
    for section in navigation._canonical_sections():
        for alias in navigation._section_aliases(section):
            lines = [
                alias, "  12.  " + alias, alias.swapcase(),
                "  " + alias.replace(" ", "   ") + "  ",
                *(alias + suffix + "status" for suffix in navigation._SUFFIXES),
                alias + "x", "prefix " + alias, alias[: max(0, len(alias) - 1)],
            ]
            for line in lines:
                assert _identity(navigation._section_for_line(line)) == _identity(
                    _reference_section_for_line(line)
                ), line


def test_known_english_and_spanish_control_headings_have_independent_expected_identity():
    for heading in ("Code Audit", "Auditoría de código"):
        result = navigation._section_for_line("2. " + heading)
        assert result is not None
        assert result[0]["section_id"] == "code_audit"
        assert result[1] is True


def test_ordered_prefix_match_still_precedes_later_exact_match(monkeypatch):
    first = {"section_id": "first", "title_en": "A", "title_es": ""}
    second = {"section_id": "second", "title_en": "A: detail", "title_es": ""}
    monkeypatch.setattr(navigation, "CANONICAL_TOC_SECTIONS", (first, second))
    result = navigation._section_for_line("A: detail")
    assert result[0]["section_id"] == "first"


def test_marker_and_candidate_normalization_limits_match_original(monkeypatch):
    section = {"section_id": "boundary"}
    monkeypatch.setattr(navigation, "CANONICAL_TOC_SECTIONS", (section,))
    monkeypatch.setattr(navigation, "_section_aliases", lambda _: ("X" * 400, " "))
    for line in ("X" * 300, "X" * 301, "X" * 500, "X" * 297 + "...", "  4.  " + "X" * 300):
        assert _identity(navigation._section_for_line(line)) == _identity(
            _reference_section_for_line(line)
        )


def test_navigation_refreshes_aliases_between_calls(monkeypatch):
    section = navigation.CANONICAL_TOC_SECTIONS[1]
    section_id = section["section_id"]
    aliases = {**navigation._TITLE_ALIASES_BY_SECTION_ID, section_id: ("Unique old alias",)}
    monkeypatch.setattr(navigation, "_TITLE_ALIASES_BY_SECTION_ID", aliases)
    records, _ = navigation.semantic_entry_records(_reader(["Unique old alias"]))
    assert any(row["section_id"] == section_id for row in records)
    aliases[section_id] = ("Unique new alias",)
    old, _ = navigation.semantic_entry_records(_reader(["Unique old alias"]))
    new, _ = navigation.semantic_entry_records(_reader(["Unique new alias"]))
    assert not any(row["section_id"] == section_id for row in old)
    assert any(row["section_id"] == section_id for row in new)


@pytest.mark.parametrize("parts", (2, 3))
def test_bounded_wrapped_headings_keep_identity_and_end_line(parts):
    section = next(s for s in navigation._canonical_sections() if s["section_id"] == "dependency_security_static_analysis")
    words = section["title_es"].split()
    cuts = [len(words) * i // parts for i in range(parts + 1)]
    lines = [" ".join(words[cuts[i]:cuts[i + 1]]) for i in range(parts)]
    result = navigation._section_for_visible_heading(lines, 0)
    assert result is not None
    assert result[0]["section_id"] == section["section_id"]
    assert result[2] == parts - 1


def test_four_line_heading_wrap_is_not_accepted():
    lines = ["Análisis de dependencias,", "seguridad", "y análisis", "estático"]
    assert navigation._section_for_visible_heading(lines, 0) is None


@pytest.mark.parametrize("line", ("Code Auditor", "prefix Code Audit", "Code Audit / status", "Code Audit—status"))
def test_unrecognized_heading_boundaries_have_independent_negative_expectations(line):
    assert navigation._section_for_line(line) is None

def test_explicit_page_text_snapshot_preserves_live_navigation_and_rejects_population():
    from nico.report_pdf_text import extract_pdf_page_texts
    from tests.test_comprehensive_four_phase_report_v1 import _pdf
    body = _pdf()
    reader = PdfReader(io.BytesIO(body))
    live = navigation.semantic_entry_records(reader)
    assert navigation.semantic_entry_records(
        PdfReader(io.BytesIO(body)), page_texts=extract_pdf_page_texts(body),
    ) == live
    for length in (1, 7):
        with pytest.raises(ValueError, match="page population"):
            navigation.semantic_entry_records(reader, page_texts=("",) * length)

def test_same_page_count_changed_bytes_change_semantic_identity():
    from nico.report_pdf_text import extract_pdf_page_texts, pdf_text_cache_scope
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 720, "NICO Comprehensive")
    document.showPage()
    document.drawString(40, 720, "Functional QA")
    document.showPage()
    document.save()
    first = buffer.getvalue()
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 720, "NICO Comprehensive")
    document.showPage()
    document.drawString(40, 720, "Platform Parity")
    document.showPage()
    document.save()
    second = buffer.getvalue()
    with pdf_text_cache_scope():
        one, _ = navigation.semantic_entry_records(
            PdfReader(io.BytesIO(first)), page_texts=extract_pdf_page_texts(first))
        two, _ = navigation.semantic_entry_records(
            PdfReader(io.BytesIO(second)), page_texts=extract_pdf_page_texts(second))
    assert len(PdfReader(io.BytesIO(first)).pages) == len(PdfReader(io.BytesIO(second)).pages) == 2
    assert [record["section_id"] for record in one] == ["functional_qa"]
    assert [record["section_id"] for record in two] == ["platform_parity"]

def test_navigation_uses_rewritten_snapshot_after_existing_toc_removal(monkeypatch):
    from tests.test_comprehensive_four_phase_report_v1 import _pdf
    from nico.report_pdf_text import extract_pdf_page_texts
    snapshots = []
    def capture(body):
        reader = PdfReader(io.BytesIO(body))
        snapshots.append(tuple(page.extract_text() or "" for page in reader.pages))
        return extract_pdf_page_texts(body)
    monkeypatch.setattr(navigation, "extract_pdf_page_texts", capture)
    rendered = navigation.semantic_renumber_and_outline(_pdf())
    assert len(snapshots) == 1 and len(snapshots[0]) == 5
    assert "Review-Required Candidate Register" in snapshots[0][1]
    assert "Table of Contents" not in "\n".join(snapshots[0])
    final = PdfReader(io.BytesIO(rendered))
    assert len(final.pages) == 6
    assert "Table of Contents" in final.pages[1].extract_text()
    assert "Review-Required Candidate Register" in final.pages[2].extract_text()

@pytest.mark.parametrize("cover,title,spanish", (
    ("AUTOMATED DRAFT", "Functional QA", False),
    ("BORRADOR AUTOMATIZADO", "QA funcional", True),
))
def test_bilingual_snapshots_keep_independent_heading_and_locale_expectations(cover, title, spanish):
    from nico.report_pdf_text import extract_pdf_page_texts
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    document.drawString(40, 720, cover)
    document.showPage()
    document.drawString(40, 720, title)
    document.showPage()
    document.save()
    body = buffer.getvalue()
    reader = PdfReader(io.BytesIO(body))
    live = navigation.semantic_entry_records(reader)
    cached = navigation.semantic_entry_records(reader, page_texts=extract_pdf_page_texts(body))
    assert cached == live and cached[1] is spanish
    assert [record["section_id"] for record in cached[0]] == ["functional_qa"]
    assert cached[0][0]["source_page_index"] == 1
