from __future__ import annotations

from nico.comprehensive_truth_diagnostics_v1 import (
    _excerpt,
    _markdown_semantic_text,
    _visible_html,
)


MARKER = "Platform Parity: Complete"


def test_inline_code_in_immutable_commit_message_is_not_a_report_assertion() -> None:
    markdown = (
        "- snapshot.commit_message: Fix contradictory platform parity language. "
        "Replaces the prohibited `Platform Parity: Complete` PDF overlay with "
        "bounded repository-indicator wording."
    )
    searchable = _markdown_semantic_text(markdown)

    assert "snapshot.commit_message" in searchable
    assert MARKER not in searchable
    assert _excerpt(searchable, MARKER) == ""


def test_html_code_in_immutable_commit_message_is_not_a_report_assertion() -> None:
    rendered_html = (
        "<p>snapshot.commit_message: Fix contradictory platform parity language. "
        "Replaces the prohibited <code>Platform Parity: Complete</code> PDF overlay "
        "with bounded repository-indicator wording.</p>"
    )
    searchable = _visible_html(rendered_html)

    assert "snapshot.commit_message" in searchable
    assert MARKER not in searchable
    assert _excerpt(searchable, MARKER) == ""


def test_fenced_source_evidence_is_not_a_report_assertion() -> None:
    markdown = """
Evidence excerpt:

```text
Platform Parity: Complete
```

Repository indicator review complete; runtime platform parity not assessed.
"""
    searchable = _markdown_semantic_text(markdown)

    assert MARKER not in searchable
    assert "runtime platform parity not assessed" in searchable


def test_plain_prose_completion_claim_still_fails_closed() -> None:
    markdown = (
        "Platform Parity: Complete. Runtime device and permission parity are ready."
    )
    html = (
        "<p>Platform Parity: Complete. Runtime device and permission parity are ready.</p>"
    )

    markdown_searchable = _markdown_semantic_text(markdown)
    html_searchable = _visible_html(html)
    assert MARKER in _excerpt(markdown_searchable, MARKER)
    assert MARKER in _excerpt(html_searchable, MARKER)
