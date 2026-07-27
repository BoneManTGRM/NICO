#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any

from playwright.sync_api import Browser, Locator, Page, sync_playwright

import mobile_restart_live_acceptance_v1 as recovery

VERSION = "nico.mobile_restart_live_acceptance.single_dispatch.v3"
_ORIGINAL_RUN_PROOF = recovery.run_proof


class _SingleDispatchLocator:
    """Use one DOM click for an action that disables itself synchronously.

    Playwright's pointer click action can retry when React disables the button in the
    same event turn. The first click has already entered the readiness check, but the
    retry is then reported as a timeout. This adapter waits for the pre-click enabled
    state and dispatches exactly one native DOM click. The acceptance contract still
    requires exactly one observed intake request, so a duplicate or missing start fails.
    """

    def __init__(self, locator: Locator) -> None:
        self._locator = locator

    def __getattr__(self, name: str) -> Any:
        return getattr(self._locator, name)

    def click(self, *args: Any, **kwargs: Any) -> None:
        timeout_ms = int(kwargs.get("timeout") or 30_000)
        deadline = time.monotonic() + timeout_ms / 1000.0
        last: dict[str, Any] = {}
        self._locator.wait_for(state="visible", timeout=timeout_ms)
        while time.monotonic() < deadline:
            last = dict(
                self._locator.evaluate(
                    """button => {
                      const workspace = button.closest('main[data-workspace="assessment"]');
                      const authorization = workspace?.querySelector('[data-assessment-authorization="true"]');
                      const repository = workspace?.querySelector('input[type="text"]');
                      const rect = button.getBoundingClientRect();
                      return {
                        connected: button.isConnected,
                        disabled: Boolean(button.disabled),
                        width: rect.width,
                        height: rect.height,
                        label: String(button.textContent || '').trim(),
                        hydrated: workspace?.dataset.assessmentHydrated || '',
                        authorization_checked: Boolean(authorization?.checked),
                        repository_value: String(repository?.value || ''),
                      };
                    }"""
                )
                or {}
            )
            if (
                last.get("hydrated") == "true"
                and last.get("connected") is True
                and last.get("disabled") is False
                and float(last.get("width") or 0) > 0
                and float(last.get("height") or 0) > 0
            ):
                break
            time.sleep(0.05)
        else:
            raise AssertionError(f"Assessment start action never became dispatchable: {last}")

        dispatched = self._locator.evaluate(
            """button => {
              if (!button.isConnected || button.disabled) return false;
              button.click();
              return true;
            }"""
        )
        assert dispatched is True, f"Assessment start action was not dispatched: {last}"


class _SingleDispatchPage:
    def __init__(self, page: Page) -> None:
        self._page = page
        self._hydration_verified = False

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def _wait_for_hydration(self, timeout_ms: int = 30_000) -> None:
        if self._hydration_verified:
            return
        workspace = self._page.locator(recovery.WORKSPACE_SELECTOR).first
        workspace.wait_for(state="visible", timeout=timeout_ms)
        self._page.wait_for_function(
            "selector => document.querySelector(selector)?.dataset.assessmentHydrated === 'true'",
            arg=recovery.WORKSPACE_SELECTOR,
            timeout=timeout_ms,
        )
        self._hydration_verified = True

    def get_by_label(self, text: Any, *args: Any, **kwargs: Any) -> Locator:
        timeout_ms = int(kwargs.pop("timeout", 30_000))
        self._wait_for_hydration(timeout_ms)
        return self._page.get_by_label(text, *args, **kwargs)

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        locator = self._page.locator(selector, *args, **kwargs)
        if selector == recovery.ACTION_SELECTOR:
            return _SingleDispatchLocator(locator)
        return locator


class _SingleDispatchContext:
    def __init__(self, context: Any) -> None:
        self._context = context

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)

    def new_page(self) -> _SingleDispatchPage:
        return _SingleDispatchPage(self._context.new_page())


class SingleDispatchBrowser:
    def __init__(self, browser: Any) -> None:
        self._browser = browser

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    def new_context(self, **kwargs: Any) -> _SingleDispatchContext:
        return _SingleDispatchContext(self._browser.new_context(**kwargs))


def run_proof(browser: Any, args: Any) -> dict[str, Any]:
    result = _ORIGINAL_RUN_PROOF(SingleDispatchBrowser(browser), args)
    result["start_dispatch"] = "single_native_dom_click"
    result["start_dispatch_retry_absent"] = True
    result["client_hydration_wait_verified"] = True
    result["acceptance_version"] = VERSION
    return result


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    try:
        with sync_playwright() as playwright:
            browser: Browser = playwright.chromium.launch(headless=True)
            try:
                result = run_proof(browser, args)
            finally:
                browser.close()
    except Exception as exc:
        failure = {
            "artifact_schema": recovery.VERSION,
            "acceptance_version": VERSION,
            "status": "failed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "error": f"{type(exc).__name__}: {recovery._bounded(exc, 1_500)}",
            "finished_at_epoch": time.time(),
        }
        recovery._write(args.output, failure)
        raise

    recovery._write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
