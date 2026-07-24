from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "two_service_live_acceptance_v3.py"


def _module():
    spec = importlib.util.spec_from_file_location("two_service_live_acceptance_v3_hydration_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


class _Page:
    def __init__(self) -> None:
        self.timeouts: list[int] = []
        self.load_states: list[tuple[str, int]] = []
        self.goto_urls: list[str] = []

    def wait_for_timeout(self, value: int) -> None:
        self.timeouts.append(value)

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        self.load_states.append((state, timeout))

    def goto(self, url: str, *args, **kwargs):
        self.goto_urls.append(url)
        return {"url": url}


class _FlakyInput:
    def __init__(self) -> None:
        self.value = ""
        self.fill_calls = 0

    def fill(self, value: str, *args, **kwargs) -> None:
        self.fill_calls += 1
        self.value = value

    def input_value(self) -> str:
        if self.fill_calls == 1:
            return ""
        return self.value


class _FlakyCheckbox:
    def __init__(self) -> None:
        self.checked = False
        self.check_calls = 0

    def check(self, *args, **kwargs) -> None:
        self.check_calls += 1
        self.checked = True

    def is_checked(self) -> bool:
        if self.check_calls == 1:
            return False
        return self.checked


def test_stable_form_locator_retries_input_replaced_by_hydration() -> None:
    module = _module()
    page = _Page()
    locator = _FlakyInput()

    module._StableFormLocator(locator, page).fill("BoneManTGRM/NICO")

    assert locator.fill_calls == 2
    assert locator.value == "BoneManTGRM/NICO"
    assert page.timeouts


def test_stable_form_locator_retries_checkbox_replaced_by_hydration() -> None:
    module = _module()
    page = _Page()
    locator = _FlakyCheckbox()

    module._StableFormLocator(locator, page).check()

    assert locator.check_calls == 2
    assert locator.checked is True


def test_expected_commit_page_waits_for_hydration_and_preserves_exact_sha() -> None:
    module = _module()
    page = _Page()
    wrapped = module._ExpectedCommitPage(page, "a" * 40)

    wrapped.goto(
        "https://app.nicoaudit.com/assessment?tier=express#assessment",
        wait_until="domcontentloaded",
        timeout=90_000,
    )

    assert "expected_commit_sha=" + "a" * 40 in page.goto_urls[0]
    assert page.load_states == [("networkidle", module.FORM_HYDRATION_TIMEOUT_MS)]


def test_acceptance_hydration_repair_is_bounded_and_installed() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert 'VERSION = "nico.two_service_live_acceptance_terminal_reconciliation.v9"' in source
    assert "FORM_HYDRATION_TIMEOUT_MS" in source
    assert "FORM_STABILITY_SECONDS" in source
    assert "runtime.run_service = _run_service_at_expected_commit" in source
    assert "controlled assessment input did not remain stable after hydration" in source
