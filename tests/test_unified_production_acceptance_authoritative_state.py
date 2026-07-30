from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import unified_production_acceptance_authoritative as authoritative


class FakePage:
    def __init__(self, payload: dict | None = None, *, error: Exception | None = None) -> None:
        self.payload = payload or {}
        self.error = error
        self.url = (
            "https://app.nicoaudit.com/assessment?tier=comprehensive"
            "&expected_commit_sha=" + "a" * 40 + "#assessment"
        )
        self.evaluate_calls = 0

    def evaluate(self, script: str) -> dict:
        self.evaluate_calls += 1
        assert 'section[data-assessment-run-state="true"]' in script
        assert 'section[aria-live="polite"]' in script
        if self.error is not None:
            raise self.error
        return dict(self.payload)


def test_authoritative_reader_uses_one_nonblocking_document_query() -> None:
    page = FakePage(
        {
            "phase_label": "Creating engagement",
            "message": "Creating engagement: NICO assessment team",
            "run_id": "comprun_abc123",
            "commit_sha": "b" * 40,
            "page_url": "https://app.nicoaudit.com/assessment?run_id=comprun_abc123",
        }
    )

    state = authoritative.authoritative_ui_state(page)

    assert page.evaluate_calls == 1
    assert state["phase_label"] == "Creating engagement"
    assert state["run_id"] == "comprun_abc123"
    assert state["commit_sha"] == "b" * 40


def test_authoritative_reader_never_calls_the_legacy_locator_fallback() -> None:
    source = (SCRIPTS / "unified_production_acceptance_authoritative.py").read_text(
        encoding="utf-8"
    )

    assert "_ORIGINAL_UI_STATE" not in source
    assert "page.locator(" not in source
    assert "document.querySelector('section[data-assessment-run-state=\"true\"]')" in source
    assert "response capture" in source


def test_authoritative_reader_returns_immediately_when_dom_query_fails() -> None:
    page = FakePage(error=RuntimeError("page changed during read"))

    state = authoritative.authoritative_ui_state(page)

    assert page.evaluate_calls == 1
    assert state["run_id"] == ""
    assert state["commit_sha"] == "a" * 40
    assert state["page_url"].startswith("https://app.nicoaudit.com/assessment")
