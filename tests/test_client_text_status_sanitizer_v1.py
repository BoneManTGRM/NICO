from __future__ import annotations

from nico.client_text_status_sanitizer_v1 import sanitize_client_text_status


def test_text_status_sanitizer_removes_unapproved_finality_and_bad_article() -> None:
    source = (
        "The package is a final automated assessment pending human approval. "
        "The report is a automated draft report. "
        "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"
    )
    result = sanitize_client_text_status(source)

    assert "final automated" not in result
    assert "a automated" not in result
    assert "FINAL REPORT" not in result
    assert "an automated draft assessment" in result
    assert "an automated draft report" in result
    assert "AUTOMATED DRAFT · PENDING HUMAN APPROVAL" in result
