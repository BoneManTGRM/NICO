from pathlib import Path


SOURCE_PATH = Path("apps/web/app/AssessmentFinalReviewAction.tsx")


def source() -> str:
    return SOURCE_PATH.read_text(encoding="utf-8")


def test_existing_terminal_review_action_updates_are_idempotent() -> None:
    text = source()
    assert 'const reviewHref = `/operations/final-review?${query}`;' in text
    assert 'if (existing.getAttribute("href") !== reviewHref)' in text
    assert 'if (existing.textContent !== label) existing.textContent = label;' in text
    assert 'if (existing.getAttribute("aria-label") !== reviewAriaLabel)' in text


def test_terminal_review_observer_does_not_watch_character_data() -> None:
    text = source()
    observe_start = text.index("observer.observe(document.body")
    observe_end = text.index(");", observe_start)
    observer_contract = text[observe_start:observe_end]
    assert "characterData" not in observer_contract
    assert '"data-assessment-report-ready"' in observer_contract


def test_terminal_review_observer_coalesces_mutation_frames() -> None:
    text = source()
    assert "let scheduled = false;" in text
    assert "if (scheduled) return;" in text
    assert "window.cancelAnimationFrame(frame);" in text
