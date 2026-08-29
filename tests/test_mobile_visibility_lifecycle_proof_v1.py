from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"


def _load_recovery(monkeypatch: Any) -> ModuleType:
    playwright = ModuleType("playwright")
    sync_api = ModuleType("playwright.sync_api")
    sync_api.Browser = object
    sync_api.Page = object
    sync_api.sync_playwright = lambda: None
    monkeypatch.setitem(sys.modules, "playwright", playwright)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", sync_api)
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    spec = importlib.util.spec_from_file_location(
        "nico_mobile_visibility_lifecycle_test_subject",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Page:
    def __init__(self) -> None:
        self.visibility = "visible"
        self.transitions: list[str] = []
        self.observer_installed = False
        self.front_count = 0

    def set_visibility(self, value: str) -> None:
        if value == self.visibility:
            return
        self.visibility = value
        if self.observer_installed:
            self.transitions.append(value)

    def evaluate(self, expression: str) -> Any:
        if "__nicoVisibilityTransitions = []" in expression:
            self.transitions.clear()
            self.observer_installed = True
            return None
        if "Array.from(window.__nicoVisibilityTransitions" in expression:
            return list(self.transitions)
        if "document.visibilityState" in expression:
            return self.visibility
        raise AssertionError(f"Unexpected evaluate expression: {expression}")

    def wait_for_function(self, expression: str, *, timeout: int) -> None:
        assert timeout > 0
        expected = "hidden" if "=== 'hidden'" in expression else "visible"
        assert self.visibility == expected, (expression, self.visibility)

    def bring_to_front(self) -> None:
        self.front_count += 1
        self.set_visibility("visible")


class _CDPSession:
    def __init__(self, page: _Page) -> None:
        self.page = page
        self.commands: list[tuple[str, dict[str, str]]] = []
        self.detached = False

    def send(self, method: str, params: dict[str, str]) -> None:
        self.commands.append((method, params))
        assert method == "Page.setWebLifecycleState"
        if params == {"state": "frozen"}:
            self.page.set_visibility("hidden")
        else:
            assert params == {"state": "active"}

    def detach(self) -> None:
        self.detached = True


class _ChromiumContext:
    def __init__(self, page: _Page) -> None:
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"))
        self.page = page
        self.session = _CDPSession(page)

    def new_cdp_session(self, page: _Page) -> _CDPSession:
        assert page is self.page
        return self.session

    def new_page(self) -> Any:
        raise AssertionError("Headless Chromium proof must not rely on tab activation")


class _BackgroundPage:
    def __init__(self, primary: _Page) -> None:
        self.primary = primary
        self.closed = False

    def goto(self, url: str) -> None:
        assert url == "about:blank"

    def bring_to_front(self) -> None:
        self.primary.set_visibility("hidden")

    def close(self) -> None:
        self.closed = True


class _WebKitContext:
    def __init__(self, page: _Page) -> None:
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name="webkit"))
        self.background = _BackgroundPage(page)

    def new_page(self) -> _BackgroundPage:
        return self.background


def test_headless_chromium_uses_browser_lifecycle_not_second_tab(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    page = _Page()
    context = _ChromiumContext(page)

    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.session.commands == [
        ("Page.setWebLifecycleState", {"state": "frozen"}),
        ("Page.setWebLifecycleState", {"state": "active"}),
        ("Page.setWebLifecycleState", {"state": "active"}),
    ]
    assert context.session.detached is True
    assert proof["browser_engine"] == "chromium"
    assert proof["visibility_transition_mechanism"] == "chromium_cdp_web_lifecycle"
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"


def test_chromium_failure_still_unfreezes_and_reactivates_page(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)

    class FailingPage(_Page):
        def wait_for_function(self, expression: str, *, timeout: int) -> None:
            if "=== 'hidden'" in expression:
                raise TimeoutError("synthetic hidden wait failure")
            super().wait_for_function(expression, timeout=timeout)

    page = FailingPage()
    context = _ChromiumContext(page)

    with pytest.raises(TimeoutError, match="synthetic hidden wait failure"):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.session.commands[-1] == (
        "Page.setWebLifecycleState",
        {"state": "active"},
    )
    assert context.session.detached is True
    assert page.visibility == "visible"


def test_webkit_retains_native_tab_visibility_transition(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    page = _Page()
    context = _WebKitContext(page)

    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert proof["browser_engine"] == "webkit"
    assert proof["visibility_transition_mechanism"] == "browser_tab_activation"
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"


def test_installed_headless_chromium_observes_real_browser_visibility() -> None:
    """Exercise the pinned browser when this test runs in a Playwright job.

    The ordinary unit-test environment intentionally has no browser download, so it
    skips here. Production-proof CI installs Chromium and must execute this same test
    before using the lifecycle helper against the retained production run.
    """

    sync_api = pytest.importorskip("playwright.sync_api")
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "nico_mobile_visibility_chromium_integration_subject",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)

    try:
        with sync_api.sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context()
                page = context.new_page()
                page.set_content("<main>NICO lifecycle integration proof</main>")

                proof = recovery._prove_visibility_hidden_visible(
                    page,
                    context,
                    timeout_ms=10_000,
                )

                assert proof["browser_engine"] == "chromium"
                assert proof["visibility_transition_mechanism"] == (
                    "chromium_cdp_web_lifecycle"
                )
                assert proof["observed_visibility_transitions"][-2:] == [
                    "hidden",
                    "visible",
                ]
                assert page.evaluate("() => document.visibilityState") == "visible"
            finally:
                browser.close()
    except sync_api.Error as exc:
        if "Executable doesn't exist" not in str(exc):
            raise
        pytest.skip("Playwright Chromium executable is not installed")
