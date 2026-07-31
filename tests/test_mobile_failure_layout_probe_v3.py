from __future__ import annotations

import time

import pytest

from scripts.mobile_failure_layout_probe import _dispatch_failure_until_visible


class _Locator:
    def __init__(self, page: "_Page", visible_after: int) -> None:
        self.page = page
        self.visible_after = visible_after
        self.first = self

    def is_visible(self) -> bool:
        return self.page.dispatches >= self.visible_after


class _Page:
    def __init__(self, visible_after: int) -> None:
        self.dispatches = 0
        self.locator_value = _Locator(self, visible_after)

    def locator(self, selector: str) -> _Locator:
        assert selector == '[data-assessment-failure-evidence="true"]'
        return self.locator_value

    def evaluate(self, script: str, payload: dict) -> None:
        assert payload["eventName"] == "nico:assessment-request-failed"
        assert payload["detail"]["run_id"] == "comprun_test"
        self.dispatches += 1

    def wait_for_timeout(self, milliseconds: int) -> None:
        time.sleep(milliseconds / 1000)


def test_failure_dispatch_retries_until_hydrated_listener_renders_panel() -> None:
    page = _Page(visible_after=3)
    dispatches = _dispatch_failure_until_visible(
        page,
        {"run_id": "comprun_test"},
        timeout_ms=500,
        poll_ms=1,
    )

    assert dispatches == 3
    assert page.dispatches == 3


def test_failure_dispatch_is_bounded_when_panel_never_renders() -> None:
    page = _Page(visible_after=10_000)
    with pytest.raises(AssertionError, match="bounded hydration-safe dispatch"):
        _dispatch_failure_until_visible(
            page,
            {"run_id": "comprun_test"},
            timeout_ms=15,
            poll_ms=1,
        )
    assert page.dispatches > 1
