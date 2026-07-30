#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Any

VIEWPORT_WIDTHS = (320, 375, 390, 414, 430)
VIEWPORT_HEIGHT = 844
FAILURE_EVENT = "nico:assessment-request-failed"
FAILURE_RUN_ID = "comprun_mobile_failure_layout_probe"


def _screenshot_path(output: Path, locale: str, width: int) -> Path:
    language = "es-MX" if locale == "es-MX" else "en"
    return output.with_name(f"{output.stem}-failure-{language}-{width}.png")


def prove_failure_layouts(browser: Any, args: Any) -> dict[str, Any]:
    """Render the real failure component tree at every supported phone width."""

    results: list[dict[str, Any]] = []
    started = time.time()
    for locale, route, expected_title in (
        ("en", "/assessment?tier=comprehensive", "The assessment stopped"),
        ("es-MX", "/es/assessment?tier=comprehensive", "La evaluación se detuvo"),
    ):
        for width in VIEWPORT_WIDTHS:
            context = browser.new_context(
                viewport={"width": width, "height": VIEWPORT_HEIGHT},
                screen={"width": width, "height": VIEWPORT_HEIGHT},
                locale=locale,
                service_workers="block",
                extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
            )
            page = context.new_page()
            crashes: list[str] = []
            page.on("crash", lambda: crashes.append("page_crashed"))
            screenshot = _screenshot_path(args.output, locale, width)
            try:
                page.goto(
                    f"{args.frontend_url.rstrip('/')}{route}&failure_layout_probe={time.time_ns()}#assessment",
                    wait_until="domcontentloaded",
                    timeout=args.navigation_timeout_ms,
                )
                page.locator('main[data-workspace="assessment"]').first.wait_for(
                    state="visible",
                    timeout=args.navigation_timeout_ms,
                )
                page.evaluate(
                    """({eventName, detail}) => {
                      window.dispatchEvent(new CustomEvent(eventName, {detail}));
                    }""",
                    {
                        "eventName": FAILURE_EVENT,
                        "detail": {
                            "http_status": 200,
                            "route": "/api/nico/assessment/comprehensive-run/layout-probe",
                            "code": "v2_production_publication_failed",
                            "message": (
                                "scorecard omitted canonical control row: "
                                "Dependency / Library Ecosystem"
                            ),
                            "assessment_type": "comprehensive",
                            "run_id": FAILURE_RUN_ID,
                            "progress": [
                                {
                                    "step": "final_comprehensive_report_generation",
                                    "status": "blocked",
                                    "message": (
                                        "Final report publication stopped before internal review."
                                    ),
                                }
                            ],
                        },
                    },
                )
                panel = page.locator('[data-assessment-failure-evidence="true"]').first
                panel.wait_for(state="visible", timeout=args.navigation_timeout_ms)
                page.wait_for_function(
                    """() => document.body.dataset.nicoTerminalFailure === 'true'""",
                    timeout=args.navigation_timeout_ms,
                )
                metrics = page.evaluate(
                    """({expectedTitle, expectedRunId}) => {
                      const visible = element => {
                        if (!element) return false;
                        const style = getComputedStyle(element);
                        const rect = element.getBoundingClientRect();
                        return style.display !== 'none'
                          && style.visibility !== 'hidden'
                          && rect.width > 0
                          && rect.height > 0;
                      };
                      const panel = document.querySelector('[data-assessment-failure-evidence="true"]');
                      const main = document.querySelector('main[data-workspace="assessment"]');
                      const hero = main?.querySelector(':scope > .hero');
                      const intake = main?.querySelector('section#assessment');
                      const state = main?.querySelector('[data-assessment-run-state="true"]');
                      const stateHeader = state?.querySelector(':scope > .section-head');
                      const reportActions = state?.querySelector('[data-assessment-report-actions="true"]');
                      const details = panel?.querySelector('details');
                      const runCode = panel?.querySelector('.nico-failure-evidence__primary code');
                      const recovery = panel?.querySelector('a[href*="/operations/recovery"]');
                      const title = panel?.querySelector('h2');
                      const clone = panel?.cloneNode(true);
                      clone?.querySelectorAll('details').forEach(item => item.remove());
                      const primaryText = String(clone?.textContent || '').replace(/\s+/g, ' ').trim();
                      const panelRect = panel?.getBoundingClientRect();
                      const runRect = runCode?.getBoundingClientRect();
                      const recoveryRect = recovery?.getBoundingClientRect();
                      return {
                        viewport_width: window.innerWidth,
                        document_scroll_width: document.documentElement.scrollWidth,
                        body_scroll_width: document.body.scrollWidth,
                        panel_count: document.querySelectorAll('[data-assessment-failure-evidence="true"]').length,
                        title: String(title?.textContent || '').replace(/\s+/g, ' ').trim(),
                        expected_title: expectedTitle,
                        hero_visible: visible(hero),
                        intake_visible: visible(intake),
                        state_header_visible: visible(stateHeader),
                        report_actions_visible: visible(reportActions),
                        details_open: Boolean(details?.open),
                        raw_error_prominent: /scorecard omitted canonical control row/i.test(primaryText),
                        http_badge_prominent: /HTTP[_ ]?200/i.test(primaryText),
                        run_id: String(runCode?.textContent || '').replace(/\s+/g, ' ').trim(),
                        expected_run_id: expectedRunId,
                        run_scroll_width: runCode?.scrollWidth || 0,
                        run_client_width: runCode?.clientWidth || 0,
                        panel_left: panelRect?.left ?? -1,
                        panel_right: panelRect?.right ?? -1,
                        panel_width: panelRect?.width ?? 0,
                        run_left: runRect?.left ?? -1,
                        run_right: runRect?.right ?? -1,
                        recovery_visible: visible(recovery),
                        recovery_left: recoveryRect?.left ?? -1,
                        recovery_right: recoveryRect?.right ?? -1,
                        body_terminal_failure: document.body.dataset.nicoTerminalFailure || '',
                        main_terminal_failure: main?.dataset.assessmentTerminalFailure || '',
                      };
                    }""",
                    {"expectedTitle": expected_title, "expectedRunId": FAILURE_RUN_ID},
                )

                assert metrics["document_scroll_width"] <= width + 1, metrics
                assert metrics["body_scroll_width"] <= width + 1, metrics
                assert metrics["panel_count"] == 1, metrics
                assert metrics["title"] == expected_title, metrics
                assert metrics["hero_visible"] is False, metrics
                assert metrics["intake_visible"] is False, metrics
                assert metrics["state_header_visible"] is False, metrics
                assert metrics["report_actions_visible"] is False, metrics
                assert metrics["details_open"] is False, metrics
                assert metrics["raw_error_prominent"] is False, metrics
                assert metrics["http_badge_prominent"] is False, metrics
                assert metrics["run_id"] == FAILURE_RUN_ID, metrics
                assert metrics["run_scroll_width"] <= metrics["run_client_width"] + 1, metrics
                assert metrics["panel_left"] >= -1 and metrics["panel_right"] <= width + 1, metrics
                assert metrics["run_left"] >= -1 and metrics["run_right"] <= width + 1, metrics
                assert metrics["recovery_visible"] is True, metrics
                assert metrics["recovery_left"] >= -1 and metrics["recovery_right"] <= width + 1, metrics
                assert metrics["body_terminal_failure"] == "true", metrics
                assert metrics["main_terminal_failure"] == "true", metrics
                assert not crashes, crashes

                screenshot.parent.mkdir(parents=True, exist_ok=True)
                page.screenshot(
                    path=str(screenshot),
                    full_page=True,
                    timeout=15_000,
                    animations="disabled",
                )
                results.append(
                    {
                        "locale": locale,
                        "width": width,
                        "height": VIEWPORT_HEIGHT,
                        "status": "passed",
                        "metrics": metrics,
                        "screenshot": screenshot.as_posix(),
                    }
                )
            finally:
                context.close()

    return {
        "status": "passed",
        "viewports": list(VIEWPORT_WIDTHS),
        "locales": ["en", "es-MX"],
        "cases_required": len(VIEWPORT_WIDTHS) * 2,
        "cases_completed": len(results),
        "horizontal_overflow_absent": True,
        "duplicate_terminal_content_absent": True,
        "raw_diagnostics_collapsed": True,
        "recovery_reachable": True,
        "results": results,
        "started_at_epoch": started,
        "finished_at_epoch": time.time(),
    }


__all__ = ["VIEWPORT_HEIGHT", "VIEWPORT_WIDTHS", "prove_failure_layouts"]
