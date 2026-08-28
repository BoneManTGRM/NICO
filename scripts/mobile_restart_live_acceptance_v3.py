#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Browser, Locator, Page, sync_playwright

import mobile_restart_live_acceptance_v1 as recovery

VERSION = "nico.mobile_restart_live_acceptance.single_dispatch.v3"
_ORIGINAL_RUN_PROOF = recovery.run_proof
_ORIGINAL_UI_STATE = recovery._ui_state
_ORIGINAL_WAIT_FOR_TERMINAL = recovery._wait_for_terminal
HYDRATED_WORKSPACE_SELECTOR = (
    recovery.WORKSPACE_SELECTOR
    + '[data-assessment-hydrated="true"]'
    + '[data-assessment-client-mode="compact-mobile"]'
)
MAX_COMPACT_NODE_COUNT = 1_500
MAX_COMPACT_SCROLL_HEIGHT = 7_000


class _SingleDispatchLocator:
    """Dispatch one click only after the hydrated React form is actionable."""

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
                      const rect = button.getBoundingClientRect();
                      return {
                        connected: button.isConnected,
                        disabled: Boolean(button.disabled),
                        width: rect.width,
                        height: rect.height,
                        label: String(button.textContent || '').trim(),
                      };
                    }"""
                )
                or {}
            )
            if (
                last.get("connected") is True
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


def _read_terminal_metrics(page: Page) -> dict[str, Any]:
    return dict(
        page.evaluate(
            """() => ({
              hydrated: document.querySelector(
                'main[data-workspace="assessment"][data-assessment-hydrated="true"]'
              ) !== null,
              client_mode: document.querySelector(
                'main[data-workspace="assessment"]'
              )?.getAttribute('data-assessment-client-mode') || '',
              compact_terminal_count: document.querySelectorAll(
                '[data-mobile-compact-terminal="true"]'
              ).length,
              full_detail_count: document.querySelectorAll(
                '[data-full-assessment-details="true"]'
              ).length,
              heavy_report_mounted_count: document.querySelectorAll(
                '[data-mobile-heavy-report-mounted="true"]'
              ).length,
              stage_history_count: document.querySelectorAll(
                'details[class*="stageHistory"]'
              ).length,
              scorecard_grid_count: document.querySelectorAll('.results-grid').length,
              evidence_metric_count: document.querySelectorAll(
                '[data-assessment-evidence-metrics="true"] article'
              ).length,
              internal_review_action_count: document.querySelectorAll(
                '[data-assessment-internal-review="true"]'
              ).length,
              node_count: document.getElementsByTagName('*').length,
              scroll_height: document.documentElement.scrollHeight,
              body_height: document.body.getBoundingClientRect().height,
            })"""
        )
        or {}
    )


def _validate_terminal_metrics(metrics: dict[str, Any]) -> None:
    """Fail closed on the compact mobile DOM after deterministic capture."""

    assert metrics.get("hydrated") is True, metrics
    assert metrics.get("client_mode") == "compact-mobile", metrics
    assert int(metrics.get("compact_terminal_count") or 0) == 1, metrics
    assert int(metrics.get("full_detail_count") or 0) == 0, metrics
    assert int(metrics.get("heavy_report_mounted_count") or 0) == 0, metrics
    assert int(metrics.get("stage_history_count") or 0) == 0, metrics
    assert int(metrics.get("scorecard_grid_count") or 0) == 0, metrics
    assert int(metrics.get("evidence_metric_count") or 0) <= 4, metrics
    assert int(metrics.get("internal_review_action_count") or 0) <= 1, metrics
    assert int(metrics.get("node_count") or 0) < MAX_COMPACT_NODE_COUNT, metrics
    assert int(metrics.get("scroll_height") or 0) < MAX_COMPACT_SCROLL_HEIGHT, metrics


def _bounded_failure_diagnostic(page: Any, run_id: str) -> dict[str, Any]:
    if not run_id:
        return {"status": "unavailable", "reason": "run_id_missing"}
    try:
        parsed = urlparse(str(page.url))
        origin = f"{parsed.scheme}://{parsed.netloc}"
        response = page.request.get(
            f"{origin}/api/nico/assessment/comprehensive-run/{run_id}",
            headers={
                "Accept": "application/json",
                recovery.BROWSER_PROJECTION_HEADER: recovery.BROWSER_PROJECTION_VALUE,
                "Cache-Control": "no-store",
            },
            timeout=60_000,
        )
        if not response.ok:
            return {
                "status": "unavailable",
                "http_status": response.status,
                "reason": "terminal_status_request_failed",
            }
        payload = response.json()
        record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
        stage_results = record.get("stage_results") if isinstance(record.get("stage_results"), dict) else {}
        current_stage = str(payload.get("current_stage") or record.get("current_stage") or "")
        current_result = (
            stage_results.get(current_stage)
            if current_stage and isinstance(stage_results.get(current_stage), dict)
            else {}
        )
        return {
            "status": "retained",
            "run_id": str(payload.get("run_id") or run_id),
            "repository": str(payload.get("repository") or ""),
            "commit_sha": str(payload.get("commit_sha") or ""),
            "lifecycle_status": str(payload.get("status") or ""),
            "current_stage": current_stage,
            "progress_percent": payload.get("progress_percent"),
            "canonical_progress_percent": payload.get("canonical_progress_percent"),
            "active_stage_progress_percent": payload.get("active_stage_progress_percent"),
            "revision": payload.get("revision"),
            "terminal": payload.get("terminal"),
            "blockers": record.get("blockers") or [],
            "current_stage_result": current_result,
            "response_projection": payload.get("response_projection") or {},
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    except Exception as exc:
        return {
            "status": "unavailable",
            "reason": f"{type(exc).__name__}: {recovery._bounded(exc, 800)}",
        }


class _SingleDispatchPage:
    def __init__(self, page: Page, terminal_metrics: dict[str, Any]) -> None:
        self._page = page
        self._terminal_metrics = terminal_metrics

    def __getattr__(self, name: str) -> Any:
        return getattr(self._page, name)

    def _wait_for_hydration(self, timeout: int | None = None) -> None:
        self._page.locator(HYDRATED_WORKSPACE_SELECTOR).first.wait_for(
            state="visible",
            timeout=int(timeout or 120_000),
        )

    def capture_terminal_metrics(self) -> dict[str, Any]:
        metrics = _read_terminal_metrics(self._page)
        self._terminal_metrics.clear()
        self._terminal_metrics.update(metrics)
        return metrics

    def goto(self, *args: Any, **kwargs: Any) -> Any:
        response = self._page.goto(*args, **kwargs)
        self._wait_for_hydration(kwargs.get("timeout"))
        return response

    def reload(self, *args: Any, **kwargs: Any) -> Any:
        response = self._page.reload(*args, **kwargs)
        self._wait_for_hydration(kwargs.get("timeout"))
        return response

    def locator(self, selector: str, *args: Any, **kwargs: Any) -> Any:
        locator = self._page.locator(selector, *args, **kwargs)
        if selector == recovery.ACTION_SELECTOR:
            return _SingleDispatchLocator(locator)
        return locator

    def screenshot(self, *args: Any, **kwargs: Any) -> Any:
        self.capture_terminal_metrics()
        return self._page.screenshot(*args, **kwargs)


class _SingleDispatchContext:
    def __init__(self, context: Any, terminal_metrics: dict[str, Any]) -> None:
        self._context = context
        self._terminal_metrics = terminal_metrics

    def __getattr__(self, name: str) -> Any:
        return getattr(self._context, name)

    def new_page(self) -> _SingleDispatchPage:
        return _SingleDispatchPage(self._context.new_page(), self._terminal_metrics)


class SingleDispatchBrowser:
    def __init__(self, browser: Any) -> None:
        self._browser = browser
        self.terminal_metrics: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._browser, name)

    def new_context(self, **kwargs: Any) -> _SingleDispatchContext:
        return _SingleDispatchContext(
            self._browser.new_context(**kwargs),
            self.terminal_metrics,
        )


def run_proof(browser: Any, args: Any) -> dict[str, Any]:
    recovery._require_existing_source_args(args)
    wrapped = SingleDispatchBrowser(browser)

    def capture_on_terminal(page: Any) -> dict[str, str]:
        state = _ORIGINAL_UI_STATE(page)
        if state.get("phase") in recovery.TERMINAL_PHASES and hasattr(page, "capture_terminal_metrics"):
            page.capture_terminal_metrics()
        return state

    def retain_failure_diagnostic(page: Any, run_id: str, timeout_seconds: float) -> dict[str, str]:
        try:
            return _ORIGINAL_WAIT_FOR_TERMINAL(page, run_id, timeout_seconds)
        except AssertionError as exc:
            setattr(exc, "nico_diagnostic", _bounded_failure_diagnostic(page, run_id))
            raise

    recovery._ui_state = capture_on_terminal
    recovery._wait_for_terminal = retain_failure_diagnostic
    try:
        # Historical contract marker: _ORIGINAL_RUN_PROOF(SingleDispatchBrowser(browser), args)
        result = _ORIGINAL_RUN_PROOF(wrapped, args)
    finally:
        recovery._ui_state = _ORIGINAL_UI_STATE
        recovery._wait_for_terminal = _ORIGINAL_WAIT_FOR_TERMINAL

    assert wrapped.terminal_metrics, "Terminal compact-DOM metrics were not captured"
    _validate_terminal_metrics(wrapped.terminal_metrics)
    assert result.get("start_request_count") == 0
    assert result.get("continuation_post_count") == 0
    result["start_dispatch"] = "not_dispatched_existing_run"
    result["start_dispatch_retry_absent"] = True
    result["hydration_wait_verified"] = True
    result["compact_mobile_dom_verified"] = True
    result["terminal_dom_metrics"] = dict(wrapped.terminal_metrics)
    result["acceptance_version"] = VERSION
    return result


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    recovery._require_existing_source_args(args)
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
            "diagnostic": getattr(exc, "nico_diagnostic", {}),
            "finished_at_epoch": time.time(),
        }
        recovery._write(args.output, failure)
        raise

    recovery._write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
