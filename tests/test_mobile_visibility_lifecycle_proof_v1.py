from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/mobile_restart_live_acceptance_v1.py"
SPANISH_WORKFLOW = ROOT / ".github/workflows/spanish-comprehensive-production-proof.yml"
MOBILE_WORKFLOW = ROOT / ".github/workflows/mobile-restart-production-proof.yml"


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

    def wait_for_function(
        self,
        expression: str,
        *,
        polling: int,
        timeout: int,
    ) -> None:
        assert polling == 100
        assert timeout > 0
        if "window.__nicoVisibilityTransitions" in expression:
            assert self.visibility == "hidden" or (
                self.visibility == "visible"
                and self.transitions[-2:] == ["hidden", "visible"]
            ), (expression, self.visibility, self.transitions)
            return
        expected = "hidden" if "=== 'hidden'" in expression else "visible"
        assert self.visibility == expected, (expression, self.visibility)

    def bring_to_front(self) -> None:
        self.front_count += 1
        self.set_visibility("visible")


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


class _FocusSession:
    def __init__(self) -> None:
        self.commands: list[tuple[str, dict[str, bool]]] = []
        self.detached = False

    def send(self, method: str, params: dict[str, bool]) -> None:
        assert method == "Emulation.setFocusEmulationEnabled"
        assert params in ({"enabled": False}, {"enabled": True})
        self.commands.append((method, params))

    def detach(self) -> None:
        self.detached = True


class _FocusHidingSession(_FocusSession):
    def __init__(self, page: _Page) -> None:
        super().__init__()
        self.page = page

    def send(self, method: str, params: dict[str, bool]) -> None:
        super().send(method, params)
        if params == {"enabled": False}:
            self.page.set_visibility("hidden")


class _ChromiumContext(_WebKitContext):
    def __init__(self, page: _Page) -> None:
        super().__init__(page)
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"))
        self.focus_session = _FocusSession()

    def new_cdp_session(self, page: _Page) -> _FocusSession:
        assert page is self.background.primary
        return self.focus_session


def test_headless_chromium_fails_before_claiming_visibility(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    page = _Page()
    context = _ChromiumContext(page)

    with pytest.raises(
        RuntimeError,
        match="chromium_visibility_proof_requires_headed_browser_under_xvfb",
    ):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is False
    assert page.visibility == "visible"


def test_headed_chromium_uses_native_tab_visibility_transition(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    page = _Page()
    context = _ChromiumContext(page)

    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert context.focus_session.commands == [
        ("Emulation.setFocusEmulationEnabled", {"enabled": False}),
        ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
    ]
    assert context.focus_session.detached is True
    assert proof["browser_engine"] == "chromium"
    assert proof["browser_launch_mode"] == "headed_xvfb"
    assert proof["visibility_transition_mechanism"] == (
        "headed_tab_activation_without_focus_emulation"
    )
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"


def test_chromium_failure_still_closes_background_and_reactivates_page(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")

    class FailingPage(_Page):
        def wait_for_function(
            self,
            expression: str,
            *,
            polling: int,
            timeout: int,
        ) -> None:
            if "=== 'hidden'" in expression:
                raise TimeoutError("synthetic hidden wait failure")
            super().wait_for_function(
                expression,
                polling=polling,
                timeout=timeout,
            )

    page = FailingPage()
    context = _ChromiumContext(page)

    with pytest.raises(TimeoutError, match="synthetic hidden wait failure"):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert context.focus_session.commands == [
        ("Emulation.setFocusEmulationEnabled", {"enabled": False}),
        ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
    ]
    assert context.focus_session.detached is True
    assert page.visibility == "visible"


def test_focus_override_removal_cannot_supply_hidden_transition(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    page = _Page()
    context = _ChromiumContext(page)
    context.focus_session = _FocusHidingSession(page)

    with pytest.raises(
        AssertionError,
        match="chromium_focus_emulation_disable_changed_subject_visibility",
    ):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.focus_session.commands == [
        ("Emulation.setFocusEmulationEnabled", {"enabled": False}),
        ("Emulation.setFocusEmulationEnabled", {"enabled": True}),
    ]
    assert context.focus_session.detached is True
    assert context.background.closed is True
    assert page.visibility == "visible"


def test_chromium_new_tab_failure_does_not_change_focus_emulation(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    page = _Page()
    context = _ChromiumContext(page)

    def fail_new_page() -> Any:
        raise RuntimeError("synthetic target creation failure")

    context.new_page = fail_new_page  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synthetic target creation failure"):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.focus_session.commands == []
    assert context.focus_session.detached is False
    assert page.visibility == "visible"


def test_chromium_launcher_is_headed_only_when_explicitly_requested(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    calls: list[bool] = []

    class Chromium:
        @staticmethod
        def launch(*, headless: bool) -> object:
            calls.append(headless)
            return object()

    playwright = SimpleNamespace(chromium=Chromium())
    recovery._launch_chromium(playwright)
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    monkeypatch.setenv("DISPLAY", ":99")
    recovery._launch_chromium(playwright)

    assert calls == [True, False]


def test_chromium_launcher_rejects_invalid_mode_or_missing_display(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    playwright = SimpleNamespace(
        chromium=SimpleNamespace(launch=lambda **_kwargs: object())
    )

    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "yes")
    with pytest.raises(RuntimeError, match="nico_proof_headed_chromium_setting_invalid"):
        recovery._launch_chromium(playwright)

    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    monkeypatch.delenv("DISPLAY", raising=False)
    with pytest.raises(RuntimeError, match="headed_chromium_proof_requires_x_display"):
        recovery._launch_chromium(playwright)


def test_webkit_retains_native_tab_visibility_transition(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    page = _Page()
    context = _WebKitContext(page)

    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert proof["browser_engine"] == "webkit"
    assert proof["browser_launch_mode"] == "headless"
    assert proof["visibility_transition_mechanism"] == "browser_tab_activation"
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"


def test_production_chromium_proofs_use_headed_browser_under_xvfb() -> None:
    spanish = SPANISH_WORKFLOW.read_text(encoding="utf-8")
    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")

    assert 'NICO_PROOF_HEADED_CHROMIUM: "1"' in spanish
    assert "command -v xvfb-run" in spanish
    assert "xvfb-run -a python -m pytest" in spanish
    assert "xvfb-run -a python scripts/spanish_comprehensive_live_acceptance_v3.py" in spanish
    assert "xvfb-run -a python scripts/spanish_comprehensive_existing_run_recovery_v1.py" in spanish
    assert 'NICO_PROOF_HEADED_CHROMIUM: "1"' in mobile
    assert "command -v xvfb-run" in mobile
    assert "xvfb-run -a python scripts/mobile_restart_live_acceptance_v5.py" in mobile

    launchers = (
        SCRIPT,
        ROOT / "scripts/mobile_restart_live_acceptance_v3.py",
        ROOT / "scripts/spanish_comprehensive_live_acceptance_v1.py",
        ROOT / "scripts/spanish_comprehensive_existing_run_recovery_v1.py",
    )
    for launcher in launchers:
        source = launcher.read_text(encoding="utf-8")
        assert ".chromium.launch(headless=True)" not in source
        assert "_launch_chromium(playwright)" in source


def test_installed_headed_chromium_observes_real_browser_visibility() -> None:
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
    if not recovery._headed_chromium_requested():
        pytest.skip("Headed Chromium proof mode is enabled by the production workflow")

    with sync_api.sync_playwright() as playwright:
        browser = recovery._launch_chromium(playwright)
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
            assert proof["browser_launch_mode"] == "headed_xvfb"
            assert proof["visibility_transition_mechanism"] == (
                "headed_tab_activation_without_focus_emulation"
            )
            assert proof["observed_visibility_transitions"][-2:] == [
                "hidden",
                "visible",
            ]
            assert page.evaluate("() => document.visibilityState") == "visible"
        finally:
            browser.close()
