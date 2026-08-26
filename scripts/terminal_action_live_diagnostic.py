#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, sync_playwright

REPORT_ACTIONS = '[data-assessment-report-actions="true"]'
FINAL_REVIEW = 'a[data-nico-final-review-action="true"]'
INTERNAL_REVIEW = 'a[data-assessment-internal-review="true"]'


def wait_terminal(origin: str, run_id: str, timeout_seconds: float) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last: dict[str, Any] = {}
    while time.time() < deadline:
        req = urllib.request.Request(
            f"{origin}/api/nico/assessment/comprehensive-run/{run_id}",
            headers={"Accept": "application/json", "Cache-Control": "no-store"},
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            last = json.loads(response.read().decode("utf-8"))
        if last.get("terminal") is True:
            if str(last.get("status") or "") not in {"review_required", "approved"}:
                raise AssertionError(f"run reached unexpected terminal state: {last.get('status')}")
            return last
        time.sleep(5)
    raise AssertionError(f"timed out waiting for terminal run: {last.get('status')} {last.get('current_stage')}")


def hit_test(page: Page, selector: str) -> dict[str, Any]:
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=120_000)
    result = locator.evaluate(
        """el => {
          const r = el.getBoundingClientRect();
          const x = r.left + r.width / 2;
          const y = r.top + r.height / 2;
          const top = document.elementFromPoint(x, y);
          return {
            width: r.width,
            height: r.height,
            pointerEvents: getComputedStyle(el).pointerEvents,
            topTag: top?.tagName || '',
            topText: String(top?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 180),
            targetOwnsPoint: top === el || Boolean(top && el.contains(top)),
          };
        }"""
    )
    assert result["width"] > 0 and result["height"] > 0, result
    assert result["pointerEvents"] != "none", result
    assert result["targetOwnsPoint"] is True, result
    return result


def wait_terminal_ui(page: Page, run_id: str) -> None:
    page.locator('section[data-assessment-run-state="true"]').first.wait_for(state="visible", timeout=120_000)
    page.wait_for_function(
        """runId => {
          const actions = document.querySelector('[data-assessment-report-actions="true"]');
          const ids = Array.from(document.querySelectorAll('.nico-identifier-value code[title]'))
            .map(el => String(el.getAttribute('title') || ''));
          return ids.includes(runId)
            && actions?.getAttribute('data-assessment-report-ready') === 'true';
        }""",
        arg=run_id,
        timeout=120_000,
    )
    page.locator(REPORT_ACTIONS).first.scroll_into_view_if_needed()


def exact_run_href(page: Page, selector: str, run_id: str) -> str:
    locator = page.locator(selector).first
    locator.wait_for(state="visible", timeout=120_000)
    href = str(locator.get_attribute("href") or "")
    assert href, f"{selector} has no href"
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    assert query.get("run_id", [""])[0] == run_id, {"selector": selector, "href": href}
    assert parsed.path == "/operations/final-review", {"selector": selector, "href": href}
    return href


def click_review_link(page: Page, selector: str, run_id: str) -> dict[str, Any]:
    href = exact_run_href(page, selector, run_id)
    hit = hit_test(page, selector)
    before = page.url
    page.locator(selector).first.click(timeout=10_000)
    page.wait_for_url(lambda value: "/operations/final-review" in value, timeout=30_000)
    parsed = urlparse(page.url)
    assert parse_qs(parsed.query).get("run_id", [""])[0] == run_id, page.url
    assert page.url != before
    return {"href": href, "destination": page.url, "hit_test": hit}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--terminal-timeout-seconds", type=float, default=3600)
    args = parser.parse_args()

    origin = args.frontend_url.rstrip("/")
    terminal = wait_terminal(origin, args.run_id, args.terminal_timeout_seconds)
    assert terminal.get("commit_sha") == args.expected_sha, terminal.get("commit_sha")
    assert terminal.get("human_review_required") is True
    assert terminal.get("client_delivery_allowed") is False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1440, "height": 1000})
        context.grant_permissions(["clipboard-read", "clipboard-write"], origin=origin)
        page = context.new_page()
        review_posts: list[str] = []
        pdf_requests: list[str] = []

        def on_request(request: Any) -> None:
            parsed = urlparse(request.url)
            if request.method == "POST" and "/review" in parsed.path:
                review_posts.append(parsed.path)
            if "/localized-report/" in parsed.path and parsed.path.endswith("/pdf"):
                pdf_requests.append(parsed.path)

        page.on("request", on_request)
        assessment_url = f"{origin}/assessment?tier=comprehensive&run_id={args.run_id}&terminal_action_probe={time.time_ns()}#assessment"
        page.goto(assessment_url, wait_until="domcontentloaded", timeout=120_000)
        wait_terminal_ui(page, args.run_id)

        actions = page.locator(REPORT_ACTIONS).first
        copy_button = actions.get_by_role("button", name="Copy Markdown", exact=True)
        copy_button.wait_for(state="visible", timeout=30_000)
        assert copy_button.is_enabled()
        copy_hit = hit_test(page, f'{REPORT_ACTIONS} button')

        # First click either copies already-prefetched Markdown or explicitly prepares it.
        copy_button.click()
        page.wait_for_timeout(350)
        status_text = str(actions.text_content() or "")
        if "Preparing Markdown" in status_text or "Markdown ready" in status_text:
            page.wait_for_function(
                """selector => String(document.querySelector(selector)?.textContent || '').includes('Markdown ready')""",
                arg=REPORT_ACTIONS,
                timeout=30_000,
            )
            copy_button.click()
        page.wait_for_function(
            """selector => String(document.querySelector(selector)?.textContent || '').includes('Markdown copied')""",
            arg=REPORT_ACTIONS,
            timeout=10_000,
        )
        clipboard = page.evaluate("() => navigator.clipboard.readText()")
        assert isinstance(clipboard, str) and len(clipboard) > 1_000
        assert args.run_id in clipboard

        pdf_button = actions.get_by_role("button", name="Download review PDF", exact=True)
        pdf_button.wait_for(state="visible", timeout=30_000)
        assert pdf_button.is_enabled()
        pdf_hit = hit_test(page, f'{REPORT_ACTIONS} button:nth-of-type(2)')
        pdf_requests.clear()
        pdf_button.click()
        page.wait_for_function(
            """selector => String(document.querySelector(selector)?.textContent || '').includes('PDF requested')""",
            arg=REPORT_ACTIONS,
            timeout=10_000,
        )
        deadline = time.time() + 10
        while time.time() < deadline and len(pdf_requests) < 1:
            page.wait_for_timeout(100)
        assert len(pdf_requests) == 1, {"pdf_requests": pdf_requests}
        assert args.run_id in pdf_requests[0]

        # Both review entry points must be real, hit-testable links and navigate to the exact run.
        page.wait_for_timeout(500)
        final_review = click_review_link(page, FINAL_REVIEW, args.run_id)
        assert review_posts == [], {"unexpected_review_posts": review_posts}

        page.goto(assessment_url, wait_until="domcontentloaded", timeout=120_000)
        wait_terminal_ui(page, args.run_id)
        page.wait_for_timeout(500)
        internal_review = click_review_link(page, INTERNAL_REVIEW, args.run_id)
        assert review_posts == [], {"unexpected_review_posts": review_posts}

        result = {
            "artifact_schema": "nico.terminal_action_live_diagnostic.v1",
            "status": "passed",
            "run_id": args.run_id,
            "expected_sha": args.expected_sha,
            "production_status": terminal.get("status"),
            "copy_markdown_verified": True,
            "copy_markdown_clipboard_bytes": len(clipboard.encode("utf-8")),
            "copy_markdown_hit_test": copy_hit,
            "review_pdf_single_dispatch_verified": True,
            "review_pdf_request_count": len(pdf_requests),
            "review_pdf_request": pdf_requests[0],
            "review_pdf_hit_test": pdf_hit,
            "review_and_accept_navigation_verified": True,
            "review_and_accept": final_review,
            "open_internal_review_navigation_verified": True,
            "open_internal_review": internal_review,
            "review_mutation_absent": len(review_posts) == 0,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(json.dumps(result, sort_keys=True))
        context.close()
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
