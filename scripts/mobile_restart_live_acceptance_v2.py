#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Browser, Page, sync_playwright

import mobile_restart_live_acceptance_v1 as recovery

VERSION = "nico.mobile_restart_live_acceptance.webkit.v2"
OPTIONAL_EVIDENCE_SELECTOR = 'section[aria-labelledby="strategic-evidence-title"]'
AUTHORIZATION_SELECTOR = '[data-assessment-authorization="true"]'
ACTION_SELECTOR = '[data-assessment-primary-action="true"]'


class _IPhoneBrowser:
    """Force every recovery context onto an iPhone-like WebKit surface."""

    def __init__(self, browser: Browser) -> None:
        self._browser = browser

    def new_context(self, **kwargs: Any) -> Any:
        kwargs.setdefault("viewport", {"width": 390, "height": 844})
        kwargs.setdefault("screen", {"width": 390, "height": 844})
        kwargs.setdefault("device_scale_factor", 3)
        kwargs.setdefault("is_mobile", True)
        kwargs.setdefault("has_touch", True)
        kwargs.setdefault(
            "user_agent",
            "Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0 "
            "Mobile/15E148 Safari/604.1",
        )
        return self._browser.new_context(**kwargs)


def _assert_not_clipped(page: Page, selector: str) -> dict[str, Any]:
    result = page.locator(selector).evaluate(
        """element => {
          const target = element.getBoundingClientRect();
          const offenders = [];
          let parent = element.parentElement;
          while (parent) {
            const style = getComputedStyle(parent);
            const rect = parent.getBoundingClientRect();
            const clipsY = ['hidden', 'clip'].includes(style.overflowY)
              || ['hidden', 'clip'].includes(style.overflow);
            if (clipsY && (target.bottom > rect.bottom + 1 || target.top < rect.top - 1)) {
              offenders.push({
                tag: parent.tagName,
                id: parent.id || '',
                class_name: String(parent.className || '').slice(0, 240),
                overflow: style.overflow,
                overflow_y: style.overflowY,
                target_top: target.top,
                target_bottom: target.bottom,
                parent_top: rect.top,
                parent_bottom: rect.bottom,
              });
            }
            parent = parent.parentElement;
          }
          return {
            target: {top: target.top, bottom: target.bottom, width: target.width, height: target.height},
            offenders,
          };
        }"""
    )
    assert not result.get("offenders"), f"Mobile action is clipped by an ancestor: {result}"
    return dict(result)


def _prove_intake_paint(browser: _IPhoneBrowser, args: Any) -> dict[str, Any]:
    context = browser.new_context(
        locale="en-US",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    crashes: list[str] = []
    page.on("crash", lambda: crashes.append("page_crashed"))
    started = time.time()
    top_path = args.output.with_name(args.output.stem + "-intake-top.png")
    bottom_path = args.output.with_name(args.output.stem + "-intake-bottom.png")
    try:
        page.goto(
            f"{args.frontend_url.rstrip('/')}/assessment?tier=comprehensive&webkit_paint_probe={time.time_ns()}#assessment",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        workspace = page.locator(recovery.WORKSPACE_SELECTOR).first
        workspace.wait_for(state="visible", timeout=args.navigation_timeout_ms)
        optional = page.locator(OPTIONAL_EVIDENCE_SELECTOR).first
        optional.wait_for(state="visible", timeout=args.navigation_timeout_ms)

        paint_boundary = optional.evaluate(
            """section => {
              const chooser = section.querySelector(':scope > label');
              const workspace = section.querySelector(':scope > div:nth-of-type(2)');
              const style = getComputedStyle(section);
              return {
                chooser_display: chooser ? getComputedStyle(chooser).display : 'missing',
                editor_display: workspace ? getComputedStyle(workspace).display : 'missing',
                section_height: section.getBoundingClientRect().height,
                section_overflow: style.overflow,
              };
            }"""
        )
        assert paint_boundary.get("chooser_display") == "none", paint_boundary
        assert paint_boundary.get("editor_display") == "none", paint_boundary
        assert float(paint_boundary.get("section_height") or 0) < 520, paint_boundary

        document_metrics = page.evaluate(
            """() => ({
              scroll_height: document.documentElement.scrollHeight,
              body_height: document.body.getBoundingClientRect().height,
              viewport_height: window.innerHeight,
              viewport_width: window.innerWidth,
              node_count: document.getElementsByTagName('*').length,
            })"""
        )
        assert int(document_metrics.get("scroll_height") or 0) < 6_000, document_metrics
        assert int(document_metrics.get("node_count") or 0) < 2_500, document_metrics

        page.screenshot(path=str(top_path), full_page=False, timeout=15_000, animations="disabled")

        authorization = page.locator(AUTHORIZATION_SELECTOR).first
        action = page.locator(ACTION_SELECTOR).first
        authorization.scroll_into_view_if_needed(timeout=args.navigation_timeout_ms)
        action.scroll_into_view_if_needed(timeout=args.navigation_timeout_ms)
        page.wait_for_timeout(350)
        assert authorization.is_visible(), "Authorization control was not visible after mobile scroll"
        assert action.is_visible(), "Assessment start action was not visible after mobile scroll"
        clipping = _assert_not_clipped(page, ACTION_SELECTOR)
        action_box = action.bounding_box()
        assert action_box is not None and action_box["height"] >= 44, action_box
        assert action_box["y"] < 844 and action_box["y"] + action_box["height"] > 0, action_box
        assert not crashes, crashes

        page.screenshot(path=str(bottom_path), full_page=False, timeout=15_000, animations="disabled")
        return {
            "status": "passed",
            "browser_engine": "webkit",
            "mobile_emulation": "iPhone 390x844 @3x touch",
            "optional_evidence_editor_suppressed": True,
            "authorization_reachable": True,
            "assessment_action_reachable": True,
            "ancestor_clipping_absent": True,
            "page_crash_absent": True,
            "paint_boundary": paint_boundary,
            "document_metrics": document_metrics,
            "action_box": action_box,
            "clipping": clipping,
            "started_at_epoch": started,
            "finished_at_epoch": time.time(),
            "top_screenshot": top_path.as_posix(),
            "bottom_screenshot": bottom_path.as_posix(),
        }
    finally:
        context.close()


def main(argv: list[str] | None = None) -> int:
    args = recovery.parse_args(argv)
    failure: dict[str, Any] | None = None
    try:
        with sync_playwright() as playwright:
            raw_browser = playwright.webkit.launch(headless=True)
            browser = _IPhoneBrowser(raw_browser)
            try:
                intake = _prove_intake_paint(browser, args)
                result = recovery.run_proof(browser, args)
            finally:
                raw_browser.close()
        result["webkit_intake_paint"] = intake
        result["webkit_intake_paint_stability_verified"] = True
        result["browser_engine"] = "webkit"
        result["mobile_emulation"] = "iPhone 390x844 @3x touch"
        result["acceptance_version"] = VERSION
    except Exception as exc:
        failure = {
            "artifact_schema": recovery.VERSION,
            "acceptance_version": VERSION,
            "status": "failed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "browser_engine": "webkit",
            "error": f"{type(exc).__name__}: {recovery._bounded(exc, 2_000)}",
            "finished_at_epoch": time.time(),
        }
        recovery._write(args.output, failure)
        raise

    recovery._write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
