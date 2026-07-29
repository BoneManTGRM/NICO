from __future__ import annotations

import io

from pypdf import PdfReader

from nico.phase17_canonical_artifact_rebuild_v1 import _PDF_CONTROL_CHARACTER_GUARD
from nico.v2_authoritative_premium_report import _pdf_from_markdown
from nico.v2_pdf_control_character_guard import _assert_no_control_glyphs, _pdf_safe_markdown


def _canonical() -> dict:
    return {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "run_id": "comprun_control_glyph",
            "commit_sha": "9" * 40,
        },
        "assessment": {
            "technical_score": 70,
            "canonical_evidence_adjusted_score": 71,
            "maturity_signal": {
                "technical_score": 70,
                "canonical_evidence_adjusted_score": 71,
            },
        },
    }


def _control_codes(text: str) -> set[int]:
    return {
        ord(char)
        for char in text
        if (ord(char) < 32 and char not in "\n\r\t") or 0x7F <= ord(char) <= 0x9F
    }


def test_pdf_safe_markdown_replaces_list_markers_without_changing_copy() -> None:
    source = "# NICO\n\n## Evidence\n- completed scanner\n- [ ] reviewer approval\nplain text"
    projected = _pdf_safe_markdown(source)

    assert "* completed scanner" in projected
    assert "[ ] reviewer approval" in projected
    assert "plain text" in projected
    assert "- completed scanner" not in projected


def test_authoritative_pdf_has_no_c0_or_c1_control_glyphs() -> None:
    markdown = "# NICO\n\n## Evidence\n- completed scanner\n- second scanner\n\n## Human Review and Acceptance Gate\n- [ ] approve exact package"
    pdf, page_count = _pdf_from_markdown(markdown, _canonical(), spanish=False)

    assert page_count >= 2
    _assert_no_control_glyphs(pdf)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert not _control_codes(text)
    assert "completed scanner" in text
    assert "approve exact package" in text


def test_guard_is_bound_at_phase17_bootstrap() -> None:
    assert _PDF_CONTROL_CHARACTER_GUARD["bound"] is True
    assert _PDF_CONTROL_CHARACTER_GUARD["pdf_control_glyph_validation"] is True
