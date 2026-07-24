from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"


def _module():
    spec = importlib.util.spec_from_file_location("acceptance_v3_hydration_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class Page:
    def __init__(self) -> None:
        self.timeouts = []
        self.load_states = []
        self.goto_urls = []

    def wait_for_timeout(self, value):
        self.timeouts.append(value)

    def wait_for_load_state(self, state, timeout):
        self.load_states.append((state, timeout))

    def goto(self, url, *args, **kwargs):
        self.goto_urls.append(url)
        return {"url": url}


class FlakyInput:
    def __init__(self) -> None:
        self.value = ""
        self.calls = 0

    def fill(self, value, *args, **kwargs):
        self.calls += 1
        self.value = value

    def input_value(self):
        return "" if self.calls == 1 else self.value


class FlakyCheckbox:
    def __init__(self) -> None:
        self.checked = False
        self.calls = 0

    def check(self, *args, **kwargs):
        self.calls += 1
        self.checked = True

    def is_checked(self):
        return False if self.calls == 1 else self.checked


class Locator:
    def __init__(self, selector):
        self.selector = selector
        self.has_text = ""

    def filter(self, *, has_text):
        self.has_text = has_text
        return self

    @property
    def first(self):
        return self


class SelectorPage(Page):
    def __init__(self) -> None:
        super().__init__()
        self.role_calls = []

    def locator(self, selector):
        return Locator(selector)

    def get_by_role(self, role, *args, **kwargs):
        self.role_calls.append((role, args, kwargs))
        return Locator(f"role:{role}")


def test_stable_input_retries_after_hydration_reset() -> None:
    module = _module()
    page = Page()
    field = FlakyInput()
    module._StableFormLocator(field, page).fill("BoneManTGRM/NICO")
    assert field.calls == 2
    assert field.value == "BoneManTGRM/NICO"


def test_stable_checkbox_retries_after_hydration_reset() -> None:
    module = _module()
    page = Page()
    checkbox = FlakyCheckbox()
    module._StableFormLocator(checkbox, page).check()
    assert checkbox.calls == 2
    assert checkbox.checked is True


def test_expected_commit_page_waits_and_preserves_sha() -> None:
    module = _module()
    page = Page()
    wrapped = module._ExpectedCommitPage(page, "a" * 40)
    wrapped.goto("https://app.nicoaudit.com/assessment?tier=express#assessment")
    assert "expected_commit_sha=" + "a" * 40 in page.goto_urls[0]
    assert page.load_states == [("networkidle", module.FORM_HYDRATION_TIMEOUT_MS)]


def test_service_and_run_buttons_use_stable_selectors() -> None:
    module = _module()
    page = SelectorPage()
    wrapped = module._ExpectedCommitPage(page, "a" * 40)

    service = wrapped.get_by_role("button", name="Express", exact=True)
    run = wrapped.get_by_role("button", name="Run Comprehensive", exact=True)

    assert service.selector == module.SERVICE_SELECTOR
    assert service.has_text == "Express"
    assert run.selector == module.RUN_SELECTOR
    assert page.role_calls == []


def test_acceptance_repair_contract_is_installed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v10"' in source
    assert "FORM_HYDRATION_TIMEOUT_MS" in source
    assert "SERVICE_SELECTOR" in source
    assert "RUN_SELECTOR" in source
    assert "runtime.run_service = _run_service_at_expected_commit" in source
