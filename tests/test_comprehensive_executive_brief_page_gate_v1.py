from __future__ import annotations

import base64
import io

from nico.comprehensive_executive_brief_page_gate_v1 import (
    _add_page_two_copy,
    _wrap_html,
    _wrap_markdown,
    _wrap_report_builder,
    validate_executive_brief_pdf,
)


def _pdf(*pages: str) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    for page_text in pages:
        y = 740
        for line in page_text.split("\n"):
            document.drawString(42, y, line)
            y -= 14
        document.showPage()
    document.save()
    return buffer.getvalue()


def _valid_base_pdf() -> bytes:
    page_two = "\n".join(
        [
            "Executive Decision Brief",
            "Decision dashboard",
            "Top business consequences",
            "PACKAGE IDENTITY",
            "Evidence-bound decision context " * 40,
        ]
    )
    return _pdf("NICO COMPREHENSIVE", page_two, "Canonical Technical Scorecard\nEvidence Appendix")


def test_pdf_gate_accepts_exactly_one_dedicated_brief_page() -> None:
    revised = _add_page_two_copy(
        _valid_base_pdf(),
        {"repository": "BoneManTGRM/NICO", "commit_sha": "a" * 40, "assessment_duration_seconds": 12.3},
    )
    validation = validate_executive_brief_pdf(revised)
    assert validation["valid"] is True
    assert validation["executive_brief_page_count"] == 1
    assert validation["executive_brief_pages"] == [2]
    assert validation["scorecard_pages"] == [3]


def test_pdf_gate_rejects_duplicate_brief_heading() -> None:
    duplicate = _pdf(
        "NICO COMPREHENSIVE",
        "Executive Decision Brief\nDecision dashboard\nTop business consequences\nPACKAGE IDENTITY\nWHAT THIS MEANS FOR YOU\nimmutable commit\n" + "Context " * 100,
        "Executive Decision Brief\nCanonical Technical Scorecard",
    )
    validation = validate_executive_brief_pdf(duplicate)
    assert validation["valid"] is False
    assert validation["executive_brief_page_count"] == 2


def test_pdf_gate_rejects_scorecard_on_brief_page() -> None:
    invalid = _pdf(
        "NICO COMPREHENSIVE",
        "Executive Decision Brief\nDecision dashboard\nTop business consequences\nPACKAGE IDENTITY\nWHAT THIS MEANS FOR YOU\nimmutable commit\nCanonical Technical Scorecard\n" + "Context " * 100,
        "Evidence Appendix",
    )
    validation = validate_executive_brief_pdf(invalid)
    assert validation["valid"] is False
    assert validation["scorecard_begins_after_executive_brief"] is False


def test_markdown_and_html_copy_include_required_decision_language() -> None:
    identity = {"repository": "BoneManTGRM/NICO", "commit_sha": "b" * 40, "assessment_duration_seconds": 8}
    markdown = _wrap_markdown(lambda **kwargs: "# Report\n\n## Executive Decision Brief\n\nExisting summary.")(
        identity=identity
    )
    html = _wrap_html(lambda **kwargs: "<section><h2>Executive Decision Brief</h2><p>Existing summary.</p></section>")(
        identity=identity
    )
    assert "What this means for you:" in markdown
    assert "immutable commit" in markdown
    assert "What this means for you:" in html
    assert "immutable commit" in html


def test_report_builder_updates_pdf_digest_and_quality_gate() -> None:
    original = _valid_base_pdf()

    def delegate(**kwargs):
        return {
            "status": "complete",
            "report_package": {
                "pdf_base64": base64.b64encode(original).decode("ascii"),
                "pdf_sha256": "old",
            },
            "report_quality_contract": {},
        }

    result = _wrap_report_builder(delegate)(
        identity={"repository": "BoneManTGRM/NICO", "commit_sha": "c" * 40},
        stage_results={},
    )
    assert result["status"] == "complete"
    assert result["report_package"]["pdf_sha256"] != "old"
    assert result["report_quality_contract"]["executive_brief_exactly_one_page"] is True
    assert result["report_quality_contract"]["executive_brief_what_this_means_present"] is True


def test_invalid_pdf_fails_closed() -> None:
    result = _wrap_report_builder(
        lambda **kwargs: {
            "status": "complete",
            "report_package": {"pdf_base64": base64.b64encode(b"not-a-pdf").decode("ascii")},
        }
    )(identity={"repository": "repo", "commit_sha": "d" * 40}, stage_results={})
    assert result["status"] == "blocked"
    assert result["reason"].startswith("executive_decision_brief_page_gate_failed:")
