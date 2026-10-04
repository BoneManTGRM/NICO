from __future__ import annotations

from types import SimpleNamespace

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
