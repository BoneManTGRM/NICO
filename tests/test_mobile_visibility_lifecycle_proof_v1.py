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
IOS_WORKFLOW = ROOT / ".github/workflows/ios-webkit-paint-proof.yml"


def _load_recovery(monkeypatch: Any) -> ModuleType:
    monkeypatch.delenv("NICO_PROOF_CHROMIUM_CHANNEL", raising=False)
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
        self.observer_install_count = 0
        self.front_count = 0
        self.popup: _BackgroundPage | None = None

    def set_visibility(self, value: str) -> None:
        if value == self.visibility:
            return
        self.visibility = value
        if self.observer_installed:
            self.transitions.append(value)

    def evaluate(self, expression: str) -> Any:
        if "window.open('about:blank', '_blank')" in expression:
            assert self.popup is not None
            self.set_visibility("hidden")
            return True
        if "__nicoVisibilityTransitions = []" in expression:
            self.transitions.clear()
            if not self.observer_installed:
                self.observer_install_count += 1
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

    def expect_popup(self, *, timeout: int) -> _PopupExpectation:
        assert timeout > 0
        assert self.popup is not None
        return _PopupExpectation(self.popup)


class _PopupExpectation:
    def __init__(self, page: _BackgroundPage) -> None:
        self.value = page

    def __enter__(self) -> _PopupExpectation:
        return self

    def __exit__(self, *args: Any) -> None:
        return None


class _BackgroundPage:
    def __init__(self, primary: _Page) -> None:
        self.primary = primary
        self.closed = False

    def goto(self, url: str) -> None:
        assert url == "about:blank"

    def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        assert state == "domcontentloaded"
        assert timeout > 0

    def bring_to_front(self) -> None:
        self.primary.set_visibility("hidden")

    def close(self) -> None:
        self.closed = True


class _WebKitContext:
    def __init__(self, page: _Page) -> None:
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name="webkit"))
        self.background = _BackgroundPage(page)
        page.popup = self.background

    def new_page(self) -> _BackgroundPage:
        return self.background


class _DiagnosticSession:
    def __init__(self, *, window_id: int, target_id: str) -> None:
        self.window_id = window_id
        self.target_id = target_id
        self.commands: list[tuple[str, dict[str, Any]]] = []
        self.detached = False

    def send(
        self,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        rendered = dict(params or {})
        self.commands.append((method, rendered))
        if method == "Target.getTargetInfo":
            return {"targetInfo": {"targetId": self.target_id, "type": "page"}}
        if method == "Browser.getWindowForTarget":
            assert rendered == {"targetId": self.target_id}
            return {"windowId": self.window_id}
        raise AssertionError(f"Unexpected CDP command: {method} {rendered}")

    def detach(self) -> None:
        self.detached = True


class _ChromiumContext(_WebKitContext):
    def __init__(self, page: _Page) -> None:
        super().__init__(page)
        self.browser = SimpleNamespace(browser_type=SimpleNamespace(name="chromium"))
        self.subject_session = _DiagnosticSession(
            window_id=17,
            target_id="subject-target",
        )
        self.background_session = _DiagnosticSession(
            window_id=17,
            target_id="background-target",
        )

    def new_cdp_session(self, page: Any) -> _DiagnosticSession:
        if page is self.background.primary:
            return self.subject_session
        if page is self.background:
            return self.background_session
        raise AssertionError(f"Unexpected CDP page: {page!r}")


class _PermissionContext:
    def __init__(self, browser_engine: str) -> None:
        self.browser = SimpleNamespace(
            browser_type=SimpleNamespace(name=browser_engine)
        )
        self.grants: list[tuple[list[str], str]] = []

    def grant_permissions(self, permissions: list[str], *, origin: str) -> None:
        if self.browser.browser_type.name == "webkit":
            raise AssertionError("WebKit must not receive Chromium clipboard permissions")
        self.grants.append((permissions, origin))


def _enable_native_chromium(monkeypatch: Any, recovery: ModuleType) -> None:
    monkeypatch.setenv(recovery.HEADED_CHROMIUM_ENV, "1")
    monkeypatch.setenv(recovery.NATIVE_VISIBILITY_ENV, "1")


def _enable_native_webkit(monkeypatch: Any, recovery: ModuleType) -> None:
    monkeypatch.setenv(recovery.WEBKIT_NATIVE_VISIBILITY_ENV, "1")


def test_clipboard_permissions_are_granted_only_to_chromium(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    origin = "https://app.nicoaudit.com"
    chromium = _PermissionContext("chromium")
    webkit = _PermissionContext("webkit")

    assert (
        recovery._grant_supported_clipboard_permissions(chromium, origin=origin)
        == "chromium"
    )
    assert chromium.grants == [
        (["clipboard-read", "clipboard-write"], origin)
    ]
    assert (
        recovery._grant_supported_clipboard_permissions(webkit, origin=origin)
        == "webkit"
    )
    assert webkit.grants == []


def test_headless_chromium_fails_before_claiming_visibility(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    monkeypatch.delenv(recovery.NATIVE_VISIBILITY_ENV, raising=False)
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
    _enable_native_chromium(monkeypatch, recovery)
    page = _Page()
    context = _ChromiumContext(page)

    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert context.subject_session.commands == [
        ("Target.getTargetInfo", {}),
        ("Browser.getWindowForTarget", {"targetId": "subject-target"}),
    ]
    assert context.background_session.commands == [
        ("Target.getTargetInfo", {}),
        ("Browser.getWindowForTarget", {"targetId": "background-target"}),
    ]
    assert context.subject_session.detached is True
    assert context.background_session.detached is True
    assert proof["browser_engine"] == "chromium"
    assert proof["browser_launch_mode"] == "headed_xvfb"
    assert proof["visibility_transition_mechanism"] == (
        "opener_tab_activation_without_playwright_focus_emulation"
    )
    assert proof["native_visibility_runtime"] == (
        "nico.playwright_native_visibility.v1"
    )
    assert proof["playwright_focus_emulation_enabled"] is False
    assert proof["shared_native_window"] is True
    assert proof["subject_window_id"] == 17
    assert proof["background_window_id"] == 17
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"

    second_context = _ChromiumContext(page)
    second_proof = recovery._prove_visibility_hidden_visible(
        page,
        second_context,
        timeout_ms=2_000,
    )
    assert second_proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.observer_install_count == 1


def test_chromium_failure_still_closes_background_and_reactivates_page(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    _enable_native_chromium(monkeypatch, recovery)

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
    assert context.subject_session.detached is True
    assert context.background_session.detached is True
    assert page.visibility == "visible"


def test_chromium_requires_both_tabs_in_the_same_native_window(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    _enable_native_chromium(monkeypatch, recovery)
    page = _Page()
    context = _ChromiumContext(page)
    context.background_session.window_id = 23

    with pytest.raises(
        AssertionError,
        match="chromium_visibility_tabs_not_in_same_native_window",
    ):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.subject_session.detached is True
    assert context.background_session.detached is True
    assert context.background.closed is True
    assert page.visibility == "visible"


def test_chromium_popup_failure_creates_no_diagnostic_sessions(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    _enable_native_chromium(monkeypatch, recovery)
    page = _Page()
    context = _ChromiumContext(page)

    def fail_popup(*, timeout: int) -> Any:
        assert timeout == 2_000
        raise RuntimeError("synthetic target creation failure")

    page.expect_popup = fail_popup  # type: ignore[method-assign]

    with pytest.raises(RuntimeError, match="synthetic target creation failure"):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.subject_session.commands == []
    assert context.background_session.commands == []
    assert context.subject_session.detached is False
    assert context.background_session.detached is False
    assert page.visibility == "visible"


def test_chromium_launcher_is_headed_only_when_explicitly_requested(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    calls: list[dict[str, Any]] = []

    class Chromium:
        @staticmethod
        def launch(**kwargs: Any) -> object:
            calls.append(kwargs)
            return object()

    playwright = SimpleNamespace(chromium=Chromium())
    recovery._launch_chromium(playwright)
    _enable_native_chromium(monkeypatch, recovery)
    monkeypatch.setenv("DISPLAY", ":99")
    recovery._launch_chromium(playwright)

    assert calls == [
        {"headless": True, "chromium_sandbox": True},
        {"headless": False, "chromium_sandbox": True},
    ]


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

    monkeypatch.setenv("DISPLAY", ":99")
    monkeypatch.setenv(recovery.NATIVE_VISIBILITY_ENV, "yes")
    with pytest.raises(RuntimeError, match="nico_proof_native_visibility_setting_invalid"):
        recovery._launch_chromium(playwright)

    monkeypatch.delenv(recovery.NATIVE_VISIBILITY_ENV, raising=False)
    with pytest.raises(
        RuntimeError,
        match="headed_chromium_proof_requires_native_visibility_runtime",
    ):
        recovery._launch_chromium(playwright)


def test_unprepared_webkit_fails_before_claiming_visibility(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.WEBKIT_NATIVE_VISIBILITY_ENV, raising=False)
    page = _Page()
    context = _WebKitContext(page)

    with pytest.raises(
        RuntimeError,
        match="webkit_visibility_proof_requires_prepared_runtime",
    ):
        recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert page.visibility == "visible"


def test_prepared_webkit_uses_native_tab_visibility(
    monkeypatch: Any,
) -> None:
    recovery = _load_recovery(monkeypatch)
    _enable_native_webkit(monkeypatch, recovery)
    page = _Page()
    context = _WebKitContext(page)
    proof = recovery._prove_visibility_hidden_visible(page, context, timeout_ms=2_000)

    assert context.background.closed is True
    assert proof["browser_engine"] == "webkit"
    assert proof["browser_launch_mode"] == "headless"
    assert proof["visibility_transition_mechanism"] == (
        "webkit_protocol_active_and_focused_transition"
    )
    assert proof["native_visibility_runtime"] == (
        "nico.playwright_webkit_native_visibility.v1"
    )
    assert proof["playwright_forced_active_override_enabled"] is False
    assert proof["webkit_active_transition_protocol"] == (
        "Emulation.setActiveAndFocused"
    )
    assert proof["observed_visibility_transitions"] == ["hidden", "visible"]
    assert page.visibility == "visible"


def test_webkit_launcher_requires_prepared_runtime(monkeypatch: Any) -> None:
    recovery = _load_recovery(monkeypatch)
    calls: list[bool] = []
    playwright = SimpleNamespace(
        webkit=SimpleNamespace(
            launch=lambda *, headless: calls.append(headless) or object()
        )
    )

    monkeypatch.delenv(recovery.WEBKIT_NATIVE_VISIBILITY_ENV, raising=False)
    with pytest.raises(
        RuntimeError,
        match="webkit_visibility_proof_requires_prepared_runtime",
    ):
        recovery._launch_webkit(playwright)

    monkeypatch.setenv(recovery.WEBKIT_NATIVE_VISIBILITY_ENV, "yes")
    with pytest.raises(
        RuntimeError,
        match="nico_proof_webkit_native_visibility_setting_invalid",
    ):
        recovery._launch_webkit(playwright)

    monkeypatch.setenv(recovery.WEBKIT_NATIVE_VISIBILITY_ENV, "1")
    recovery._launch_webkit(playwright)
    assert calls == [True]


def test_production_chromium_proofs_use_headed_browser_under_xvfb() -> None:
    spanish = SPANISH_WORKFLOW.read_text(encoding="utf-8")
    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")

    assert 'NICO_PROOF_HEADED_CHROMIUM: "1"' in spanish
    assert 'NICO_PROOF_NATIVE_VISIBILITY: "1"' in spanish
    assert "python scripts/prepare_playwright_native_visibility_v1.py" in spanish
    assert "command -v xvfb-run" in spanish
    assert "xvfb-run -a python -m pytest" in spanish
    assert (
        "xvfb-run -a python scripts/"
        "spanish_comprehensive_authenticated_live_acceptance_v1.py"
    ) in spanish
    assert (
        "xvfb-run -a python scripts/"
        "spanish_comprehensive_authenticated_existing_run_recovery_v1.py"
    ) in spanish
    assert 'NICO_PROOF_HEADED_CHROMIUM: "1"' in mobile
    assert 'NICO_PROOF_NATIVE_VISIBILITY: "1"' in mobile
    patch_invocations = [
        line.strip()
        for line in mobile.splitlines()
        if line.strip() == "python scripts/prepare_playwright_native_visibility_v1.py"
    ]
    assert len(patch_invocations) == 2
    assert "command -v xvfb-run" in mobile
    assert "xvfb-run -a python scripts/mobile_restart_authenticated_live_acceptance_v1.py" in mobile
    assert "test_installed_headed_chromium_observes_real_browser_visibility" in mobile

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


def test_production_webkit_proof_uses_prepared_native_tab_visibility() -> None:
    workflow = IOS_WORKFLOW.read_text(encoding="utf-8")
    launcher = (ROOT / "scripts/mobile_restart_live_acceptance_v2.py").read_text(
        encoding="utf-8"
    )
    lifecycle = SCRIPT.read_text(encoding="utf-8")

    assert 'NICO_PROOF_WEBKIT_NATIVE_VISIBILITY: "1"' in workflow
    assert "python scripts/prepare_playwright_webkit_native_visibility_v1.py" in workflow
    assert "python -m pytest -q --noconftest" in workflow
    assert "NICO_PROOF_" + "HEADED_WEBKIT" not in workflow
    assert "open" + "box" not in workflow
    assert "xdo" + "tool" not in workflow
    assert "python scripts/ios_webkit_authenticated_live_acceptance_v1.py" in workflow
    assert "_launch_webkit(playwright)" in launcher
    assert "playwright.webkit.launch(headless=True)" not in launcher
    assert "Object.defineProperty(document" not in lifecycle
    assert "dispatchEvent(new Event('visibilitychange'))" not in lifecycle


def test_production_final_gates_use_authoritative_visibility_mechanism() -> None:
    expected = "opener_tab_activation_without_playwright_focus_emulation"
    retired = "headed_tab_activation_without_focus_emulation"
    required_contracts = (
        'visibility["browser_engine"] == "chromium"',
        'visibility["browser_launch_mode"] == "headed_xvfb"',
        'visibility["native_visibility_runtime"] == "nico.playwright_native_visibility.v1"',
        'visibility["playwright_focus_emulation_enabled"] is False',
        'visibility["shared_native_window"] is True',
        'isinstance(visibility["subject_window_id"], int)',
        'isinstance(visibility["background_window_id"], int)',
        'visibility["subject_window_id"] == visibility["background_window_id"]',
        'isinstance(visibility["subject_target_id"], str)',
        'isinstance(visibility["background_target_id"], str)',
        'visibility["subject_target_id"] != visibility["background_target_id"]',
        'visibility["subject_target_type"] == "page"',
        'visibility["background_target_type"] == "page"',
        'visibility["document_hidden_observed"] is True',
        'visibility["document_visible_after_foreground"] is True',
        'visibility["observed_visibility_transitions"][-2:] == ["hidden", "visible"]',
    )

    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")
    assert (
        f'visibility["visibility_transition_mechanism"] == "{expected}"'
        in mobile
    )
    assert retired not in mobile
    for contract in required_contracts:
        assert contract in mobile

    spanish = SPANISH_WORKFLOW.read_text(encoding="utf-8")
    assert retired not in spanish
    assert "spanish_comprehensive_authenticated_live_acceptance_v1.py" in spanish
    assert "spanish_comprehensive_authenticated_existing_run_recovery_v1.py" in spanish
    for contract in (
        'visibility["browser_engine"] == "chromium"',
        'visibility["browser_launch_mode"] == "headed_xvfb"',
        'visibility["document_hidden_observed"] is True',
        'visibility["document_visible_after_foreground"] is True',
        'visibility["observed_visibility_transitions"][-2:] == ["hidden", "visible"]',
    ):
        assert contract in spanish


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
                "opener_tab_activation_without_playwright_focus_emulation"
            )
            assert proof["native_visibility_runtime"] == (
                "nico.playwright_native_visibility.v1"
            )
            assert proof["playwright_focus_emulation_enabled"] is False
            assert proof["shared_native_window"] is True
            assert proof["observed_visibility_transitions"][-2:] == [
                "hidden",
                "visible",
            ]
            assert page.evaluate("() => document.visibilityState") == "visible"

            repeated = recovery._prove_visibility_hidden_visible(
                page,
                context,
                timeout_ms=10_000,
            )
            assert repeated["observed_visibility_transitions"] == [
                "hidden",
                "visible",
            ]
            assert page.evaluate("() => document.visibilityState") == "visible"
        finally:
            browser.close()


def test_installed_webkit_observes_real_browser_visibility() -> None:
    """Exercise the prepared pinned WebKit tab lifecycle on PR CI."""

    sync_api = pytest.importorskip("playwright.sync_api")
    scripts = str(ROOT / "scripts")
    if scripts not in sys.path:
        sys.path.insert(0, scripts)
    spec = importlib.util.spec_from_file_location(
        "nico_mobile_visibility_webkit_integration_subject",
        SCRIPT,
    )
    assert spec is not None and spec.loader is not None
    recovery = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(recovery)
    if not recovery._webkit_native_visibility_requested():
        pytest.skip("Prepared WebKit proof mode is enabled by the iOS workflow")

    with sync_api.sync_playwright() as playwright:
        browser = recovery._launch_webkit(playwright)
        try:
            context = browser.new_context()
            page = context.new_page()
            page.set_content("<main>NICO WebKit lifecycle integration proof</main>")

            proof = recovery._prove_visibility_hidden_visible(
                page,
                context,
                timeout_ms=10_000,
            )

            assert proof["browser_engine"] == "webkit"
            assert proof["browser_launch_mode"] == "headless"
            assert proof["visibility_transition_mechanism"] == (
                "webkit_protocol_active_and_focused_transition"
            )
            assert proof["native_visibility_runtime"] == (
                "nico.playwright_webkit_native_visibility.v1"
            )
            assert proof["playwright_forced_active_override_enabled"] is False
            assert proof["webkit_active_transition_protocol"] == (
                "Emulation.setActiveAndFocused"
            )
            assert proof["observed_visibility_transitions"][-2:] == [
                "hidden",
                "visible",
            ]
            assert page.evaluate("() => document.visibilityState") == "visible"
        finally:
            browser.close()


@pytest.mark.parametrize("headed", [False, True])
def test_chromium_launcher_propagates_sandbox_failure_without_fallback(
    monkeypatch: Any, headed: bool,
) -> None:
    recovery = _load_recovery(monkeypatch)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    if headed:
        _enable_native_chromium(monkeypatch, recovery)
        monkeypatch.setenv("DISPLAY", ":99")
    calls: list[dict[str, Any]] = []
    failure = RuntimeError("synthetic_sandbox_unavailable")

    def launch(**kwargs: Any) -> object:
        calls.append(kwargs)
        raise failure

    with pytest.raises(RuntimeError) as caught:
        recovery._launch_chromium(
            SimpleNamespace(chromium=SimpleNamespace(launch=launch))
        )
    assert caught.value is failure
    assert calls == [{"headless": not headed, "chromium_sandbox": True}]

@pytest.mark.parametrize("headed", [False, True])
def test_explicit_installed_chrome_preserves_sandbox_and_propagates_failure(monkeypatch, headed):
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv("NICO_PROOF_CHROMIUM_CHANNEL", "chrome")
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    if headed:
        _enable_native_chromium(monkeypatch, recovery)
        monkeypatch.setenv("DISPLAY", ":99")
    calls = []
    failure = RuntimeError("synthetic_installed_chrome_unavailable")
    def launch(**kwargs):
        calls.append(kwargs)
        raise failure
    with pytest.raises(RuntimeError) as caught:
        recovery._launch_chromium(SimpleNamespace(chromium=SimpleNamespace(launch=launch)))
    assert caught.value is failure
    assert calls == [{"headless": not headed, "chromium_sandbox": True, "channel": "chrome"}]


@pytest.mark.parametrize("channel", ["chromium", "chrome-beta", "msedge", "--no-sandbox", " chrome "])
def test_chromium_channel_rejects_unapproved_values_before_launch(monkeypatch, channel):
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv("NICO_PROOF_CHROMIUM_CHANNEL", channel)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    calls = []
    with pytest.raises(RuntimeError, match="nico_proof_chromium_channel_invalid"):
        recovery._launch_chromium(SimpleNamespace(chromium=SimpleNamespace(launch=lambda **kw: calls.append(kw))))
    assert calls == []


def test_hosted_visibility_selects_existing_chrome_without_security_repair():
    import yaml
    workflow = yaml.safe_load(MOBILE_WORKFLOW.read_text())
    steps = workflow["jobs"]["contract"]["steps"]
    proof = next(s for s in steps if s["name"] == "Prove headed Chromium visibility before merge")
    assert proof["env"]["NICO_PROOF_CHROMIUM_CHANNEL"] == "chrome"
    setup = next(s for s in steps if s["name"] == "Prepare installed Chrome contract runtime")["run"]
    assert "python scripts/prepare_playwright_native_visibility_v1.py" in setup
    assert "test -x /opt/google/chrome/chrome" in setup
    assert "test -r /etc/apparmor.d/chrome" in setup
    assert "/opt/google/chrome/chrome --version" in setup
    assert "sha256sum /opt/google/chrome/chrome /etc/apparmor.d/chrome" in setup
    for forbidden in ("sudo", "sysctl", "chmod", "chown", "--no-sandbox", "playwright install"):
        assert forbidden not in setup

@pytest.mark.parametrize("channel", ["", "chrome"])
def test_chromium_channel_returns_browser_without_extra_launch_arguments(monkeypatch, channel):
    recovery = _load_recovery(monkeypatch)
    monkeypatch.setenv("NICO_PROOF_CHROMIUM_CHANNEL", channel)
    monkeypatch.delenv(recovery.HEADED_CHROMIUM_ENV, raising=False)
    browser = object()
    calls = []
    def launch(**kwargs):
        calls.append(kwargs)
        return browser
    assert recovery._launch_chromium(SimpleNamespace(chromium=SimpleNamespace(launch=launch))) is browser
    expected = {"headless": True, "chromium_sandbox": True}
    if channel:
        expected["channel"] = "chrome"
    assert calls == [expected]

@pytest.mark.parametrize("workflow_path,job_name", [
    (MOBILE_WORKFLOW, "live-production"),
    (SPANISH_WORKFLOW, "spanish-comprehensive"),
])
def test_shared_launcher_production_jobs_require_installed_chrome(workflow_path, job_name):
    import yaml
    job = yaml.safe_load(workflow_path.read_text())["jobs"][job_name]
    assert job["env"]["NICO_PROOF_CHROMIUM_CHANNEL"] == "chrome"
    assert job["env"]["NICO_PROOF_HEADED_CHROMIUM"] == "1"
    assert job["env"]["NICO_PROOF_NATIVE_VISIBILITY"] == "1"
    steps = job["steps"]
    preflight = next(s for s in steps if s["name"] == "Verify installed Chrome before production proof")
    assert "if" not in preflight and not preflight.get("continue-on-error", False)
    source = preflight["run"]
    for required in ("set -euo pipefail", "test -x /opt/google/chrome/chrome",
                     "test -r /etc/apparmor.d/chrome", "command -v xvfb-run", "command -v xauth",
                     "/opt/google/chrome/chrome --version",
                     "sha256sum /opt/google/chrome/chrome /etc/apparmor.d/chrome"):
        assert required in source
    for forbidden in ("sudo", "sysctl", "chmod", "chown", "--no-sandbox", "playwright install"):
        assert forbidden not in source
    preflight_index = steps.index(preflight)
    launches = [i for i, s in enumerate(steps) if any(
        line.strip().startswith("xvfb-run -a python scripts/" + entry)
        for line in s.get("run", "").splitlines()
        for entry in ("mobile_restart_authenticated_live_acceptance_v1.py",
                      "spanish_comprehensive_authenticated_live_acceptance_v1.py",
                      "spanish_comprehensive_authenticated_existing_run_recovery_v1.py"))]
    assert launches and all(preflight_index < i for i in launches)
