from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/AssessmentActiveRunReset.tsx"
LAYOUT = ROOT / "apps/web/app/layout.tsx"


def test_active_run_reset_is_mounted_globally() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")
    assert 'import AssessmentActiveRunReset from "./AssessmentActiveRunReset"' in layout
    assert "<AssessmentActiveRunReset />" in layout
    assert layout.index("<AssessmentActiveRunReset />") < layout.index("<ComprehensiveStuckRunRecovery />")


def test_active_run_reset_is_available_before_terminal_state() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert 'data-assessment-run-state="true"' in source
    assert 'data-assessment-terminal-actions="true"' in source
    assert 'data-assessment-active-run-reset="true"' in source
    assert 'data-assessment-clear-current-run="true"' in source
    assert "Clear current run and start new assessment" in source


def test_reset_clears_saved_identity_and_url_run_id() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert 'window.localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY)' in source
    assert 'window.sessionStorage.removeItem(ACTIVE_RUN_STORAGE_KEY)' in source
    assert 'url.searchParams.delete(ACTIVE_RUN_QUERY_KEY)' in source
    assert 'url.searchParams.set("new_assessment", String(Date.now()))' in source
    assert 'window.location.replace(`${url.pathname}${url.search}${url.hash}`)' in source


def test_terminal_assessment_keeps_existing_start_new_action() -> None:
    source = COMPONENT.read_text(encoding="utf-8")
    assert "if (terminalAction) return false" in source
