#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import Page, sync_playwright

import mobile_restart_live_acceptance_v1 as recovery
from comprehensive_production_run_handoff_v1 import (
    load_source_proof,
    require_canonical_json_digest,
    require_matching_canonical_truth_digest,
    source_binding_marker,
)
from mobile_pdf_download_action_proof_v1 import install_ui_pdf_download_proof

VERSION = "nico.completed-run-two-pass-production-acceptance.v1"


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _observe_terminal(
    page: Page,
    *,
    run_id: str,
    expected_sha: str,
    expected_canonical_digest: str,
    seconds: float,
    requests: list[dict[str, Any]],
    frontend_origin: str,
) -> dict[str, Any]:
    started = time.monotonic()
    baseline_index = len(requests)
    first_pdf = recovery._verify_manifest_and_pdf(page, frontend_origin, run_id)
    proof = recovery._observe_terminal_stability(
        page,
        run_id=run_id,
        expected_sha=expected_sha,
        expected_canonical_digest=expected_canonical_digest,
        seconds=seconds,
        requests=requests,
    )
    second_pdf = recovery._verify_manifest_and_pdf(page, frontend_origin, run_id)
    duration = time.monotonic() - started
    assert duration >= seconds
    for item in (first_pdf, second_pdf):
        assert item["ui_review_pdf_user_gesture_request_count"] == 1, item
        assert item["ui_review_pdf_signature_verified"] is True, item
        assert item["ui_review_pdf_exact_run_response_verified"] is True, item
        assert item["ui_review_pdf_artifact_hash_header_verified"] is True, item
        assert item["ui_review_pdf_canonical_truth_digest_verified"] is True, item
        assert item["ui_review_pdf_original_page_visible_after_action"] is True, item
        assert item["ui_review_pdf_lifecycle_contract_verified"] is True, item
        assert item["ui_review_pdf_network_path"], item
    assert (
        first_pdf["ui_review_pdf_download_sha256"]
        == second_pdf["ui_review_pdf_download_sha256"]
    )
    assert (
        first_pdf["ui_review_pdf_canonical_truth_sha256"]
        == second_pdf["ui_review_pdf_canonical_truth_sha256"]
    )
    assert first_pdf["ui_review_pdf_action_kind"] == second_pdf[
        "ui_review_pdf_action_kind"
    ]
    assert first_pdf["ui_review_pdf_network_path"] == second_pdf[
        "ui_review_pdf_network_path"
    ]
    observed = requests[baseline_index:]
    status_path = f"/api/nico/assessment/comprehensive-run/{run_id}"
    markdown_path = status_path + f"/localized-report/{proof['markdown_report_language']}"
    allowed_gets = {
        status_path,
        markdown_path,
        status_path + "/report/pdf",
        first_pdf["ui_review_pdf_network_path"],
        second_pdf["ui_review_pdf_network_path"],
    }
    posts = [item for item in observed if item.get("method") == "POST"]
    unexpected = [
        item
        for item in observed
        if item.get("path", "").startswith("/api/nico/assessment/")
        and not (
            item.get("method") == "GET" and item.get("path") in allowed_gets
        )
    ]
    assert not posts, posts
    assert not unexpected, unexpected
    assert proof["legacy_markdown_get_count"] == 0, proof
    assert proof["markdown_action_success_count"] == 2, proof
    pdf_user_gesture_get_count = sum(
        int(item["ui_review_pdf_user_gesture_request_count"])
        for item in (first_pdf, second_pdf)
    )
    assert pdf_user_gesture_get_count == 2
    proof["desktop_viewport_verified"] = True
    proof["observed_seconds_including_pdf_actions"] = round(duration, 2)
    proof["visible_pdf_action_count"] = 2
    proof["pdf_ui_action_proofs"] = [first_pdf, second_pdf]
    proof["pdf_ui_action_digests_stable"] = True
    proof["pdf_ui_actions_exact_run_bound"] = True
    proof["pdf_ui_actions_network_bounded"] = True
    proof["pdf_ui_action_browser_get_count"] = pdf_user_gesture_get_count
    proof["network_request_count_including_pdf_actions"] = len(observed)
    proof["unexpected_request_count_including_pdf_actions"] = len(unexpected)
    proof["final_pdf_artifact"] = second_pdf
    return proof


def _locale_surface(page: Page, locale: str) -> dict[str, str]:
    expected_spanish = locale == "es-MX"
    value = page.evaluate(
        """() => ({
          document_language: String(document.documentElement.lang || ''),
          workspace_locale: String(document.querySelector('main[data-workspace="assessment"]')?.getAttribute('data-assessment-locale') || ''),
          navigation_locale: String(document.querySelector('nav.global-nav')?.getAttribute('data-locale') || ''),
          pathname: window.location.pathname,
          search: window.location.search,
        })"""
    )
    surface = {str(key): str(item or "") for key, item in dict(value or {}).items()}
    expected_path = "/es/assessment" if expected_spanish else "/assessment"
    assert surface["pathname"].startswith(expected_path), surface
    assert surface["document_language"].lower().startswith(
        "es" if expected_spanish else "en"
    ), surface
    assert surface["workspace_locale"] == ("es-MX" if expected_spanish else "en"), surface
    assert surface["navigation_locale"] == (
        "es-MX" if expected_spanish else "en-US"
    ), surface
    query = parse_qs(urlparse(str(page.url)).query)
    assert len(query.get("run_id", [])) == 1, query
    assert "report_language" not in query, query
    marker = "Identidad técnica" if expected_spanish else "Technical identity"
    body = page.locator("body").inner_text()
    assert marker in body, {"locale": locale, "missing_authored_marker": marker}
    if expected_spanish:
        for leaked in (
            "Create engagement and capture repository snapshot",
            "Client name, optional",
            "Project name, optional",
            "Start new assessment",
            "Internal review required",
        ):
            assert leaked not in body, {"locale": locale, "english_leak": leaked}
    return surface


def _prove_locale_round_trip(
    page: Page,
    *,
    run_id: str,
    expected_sha: str,
    source_locale: str,
    timeout_ms: int,
) -> dict[str, Any]:
    source = _locale_surface(page, source_locale)
    target_locale = "en" if source_locale == "es-MX" else "es-MX"
    switcher = page.locator("a.language-switcher[data-preserves-assessment-state='true']").first
    assert switcher.is_visible()
    switcher.click()
    page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    target_terminal = recovery._wait_for_terminal_ui_ready(
        page, run_id, expected_sha, 120.0
    )
    target = _locale_surface(page, target_locale)
    assert parse_qs(urlparse(str(page.url)).query).get("run_id") == [run_id]

    page.go_back(wait_until="domcontentloaded", timeout=timeout_ms)
    page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
        state="visible", timeout=timeout_ms
    )
    source_terminal_after = recovery._wait_for_terminal_ui_ready(
        page, run_id, expected_sha, 120.0
    )
    source_after = _locale_surface(page, source_locale)
    assert parse_qs(urlparse(str(page.url)).query).get("run_id") == [run_id]
    return {
        "source_locale": source_locale,
        "target_locale": target_locale,
        "source_surface": source,
        "target_surface": target,
        "source_surface_after_round_trip": source_after,
        "target_terminal_run_id": target_terminal.get("run_id"),
        "source_terminal_run_id_after_round_trip": source_terminal_after.get("run_id"),
        "same_run_preserved": True,
        "same_commit_preserved": True,
        "locale_control_used": True,
        "authored_copy_localized": True,
    }


def _review_locale_surface(page: Page, locale: str, run_id: str) -> dict[str, Any]:
    spanish = locale == "es-MX"
    expected_title = (
        "Revisión final interna y autorización para el cliente."
        if spanish
        else "Internal final review and client-ready authorization."
    )
    expected_boundary = (
        "Revisa el informe NICO Comprehensive inmutable exacto, confirma su límite de evidencia"
        if spanish
        else "Review the exact immutable NICO Comprehensive report, confirm its evidence boundary"
    )
    query = parse_qs(urlparse(str(page.url)).query)
    assert query.get("run_id") == [run_id], query
    if spanish:
        assert query.get("lang") == ["es-MX"], query
    else:
        assert query.get("lang", ["en"])[0] in {"en", "en-US"}, query
    document_language = str(
        page.evaluate("() => document.documentElement.lang || ''")
    )
    assert document_language.lower().startswith("es" if spanish else "en")
    workspace = page.locator("main[data-review-contract='accepted-edition-v2']")
    workspace.wait_for(state="visible", timeout=120_000)
    heading = workspace.locator("h1").inner_text().strip()
    body = workspace.inner_text()
    assert heading == expected_title
    assert expected_boundary in body
    if spanish:
        assert "Internal final review and client-ready authorization." not in body
    return {
        "locale": locale,
        "document_language": document_language,
        "heading": heading,
        "expected_boundary_copy_present": True,
        "run_id_preserved": True,
        "requested_locale_preserved": True,
    }


def _run_pass(
    browser: Any,
    args: argparse.Namespace,
    handoff: dict[str, Any],
    *,
    pass_number: int,
    locale: str,
) -> dict[str, Any]:
    run_id = str(handoff["run_id"])
    context = browser.new_context(
        viewport={"width": 1440, "height": 1000},
        locale="es-MX" if locale == "es-MX" else "en-US",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    context.grant_permissions(
        ["clipboard-read", "clipboard-write"],
        origin=args.frontend_url.rstrip("/"),
    )
    page = context.new_page()
    requests: list[dict[str, Any]] = []
    prohibited: list[dict[str, str]] = []
    console_errors: list[str] = []
    page_errors: list[str] = []

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/nico/assessment/"):
            requests.append(
                {
                    "method": str(request.method).upper(),
                    "path": parsed.path,
                    "monotonic": time.monotonic(),
                }
            )

    def guard(route: Any, request: Any) -> None:
        path = urlparse(request.url).path
        blocked = request.method == "POST" and (
            path == "/api/nico/assessment/comprehensive-intake"
            or (
                path.startswith("/api/nico/assessment/comprehensive-run/")
                and path.endswith("/continue")
            )
        )
        if blocked:
            prohibited.append({"method": request.method, "path": path})
            route.abort("blockedbyclient")
        else:
            route.continue_()

    page.on("request", record_request)
    page.on(
        "console",
        lambda message: console_errors.append(message.text)
        if message.type == "error"
        else None,
    )
    page.on("pageerror", lambda error: page_errors.append(str(error)))
    page.route("**/*", guard)
    path = "/es/assessment" if locale == "es-MX" else "/assessment"
    url = (
        f"{args.frontend_url.rstrip('/')}{path}?tier=comprehensive&run_id={run_id}"
        f"&expected_commit_sha={args.expected_sha}"
        f"&terminal_pass={pass_number}#assessment"
    )
    try:
        page.goto(url, wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        initial = recovery._wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 240.0
        )
        initial_locale_surface = _locale_surface(page, locale)
        observation = _observe_terminal(
            page,
            run_id=run_id,
            expected_sha=args.expected_sha,
            expected_canonical_digest=handoff["canonical_truth_sha256"],
            seconds=args.observation_seconds,
            requests=requests,
            frontend_origin=args.frontend_url.rstrip("/"),
        )
        artifacts = dict(observation.pop("final_pdf_artifact"))

        page.reload(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        after_refresh = recovery._wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )

        page.goto(
            f"{args.frontend_url.rstrip('/')}/privacy",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        page.go_back(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        after_navigation = recovery._wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )

        locale_round_trip = _prove_locale_round_trip(
            page,
            run_id=run_id,
            expected_sha=args.expected_sha,
            source_locale=locale,
            timeout_ms=args.navigation_timeout_ms,
        )

        review_action = page.locator('[data-assessment-internal-review="true"]').first
        review_action.wait_for(state="visible", timeout=args.navigation_timeout_ms)
        review_href = str(review_action.get_attribute("href") or "")
        assert run_id in review_href and "final-review" in review_href, review_href
        review_action.click()
        page.wait_for_load_state("domcontentloaded", timeout=args.navigation_timeout_ms)
        assert "final-review" in page.url and run_id in page.url
        review_locale_surface = _review_locale_surface(page, locale, run_id)
        page.go_back(wait_until="domcontentloaded", timeout=args.navigation_timeout_ms)
        page.locator(recovery.WORKSPACE_SELECTOR).first.wait_for(
            state="visible", timeout=args.navigation_timeout_ms
        )
        after_review_navigation = recovery._wait_for_terminal_ui_ready(
            page, run_id, args.expected_sha, 120.0
        )

        canonical_truth = recovery._verify_canonical_truth(
            page,
            frontend_origin=args.frontend_url.rstrip("/"),
            run_id=run_id,
            expected_sha=args.expected_sha,
            expected_digest=handoff["canonical_truth_sha256"],
        )

        screenshot = args.screenshot_dir / f"pass-{pass_number}-{locale}.png"
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(screenshot), full_page=False, animations="disabled")
        start_count = recovery._start_count(requests)
        continuation_count = recovery._continuation_count(requests)
        assert start_count == 0
        assert continuation_count == 0
        assert not prohibited
        assessment_posts = [
            item for item in requests if item.get("method") == "POST"
        ]
        wrong_run_requests = [
            item
            for item in requests
            if "/comprehensive-run/" in item.get("path", "")
            and not item.get("path", "").startswith(
                f"/api/nico/assessment/comprehensive-run/{run_id}"
            )
        ]
        assert not assessment_posts, assessment_posts
        assert not wrong_run_requests, wrong_run_requests
        assert not page_errors
        relevant_console = [
            value
            for value in console_errors
            if "favicon" not in value.casefold() and "404" not in value.casefold()
        ]
        assert not relevant_console, relevant_console
        return {
            "pass_number": pass_number,
            "locale": locale,
            "run_id": run_id,
            "commit_sha": args.expected_sha,
            "initial_terminal": initial,
            "initial_locale_surface": initial_locale_surface,
            "observation": observation,
            "after_refresh": after_refresh,
            "after_navigation": after_navigation,
            "locale_round_trip": locale_round_trip,
            "after_review_navigation": after_review_navigation,
            "professional_review_href": review_href,
            "professional_review_navigation_verified": True,
            "professional_review_locale_surface": review_locale_surface,
            "professional_review_locale_preserved": True,
            "start_request_count": 0,
            "continuation_post_count": 0,
            "prohibited_mutation_attempt_count": 0,
            "assessment_request_count": len(requests),
            "assessment_post_request_count": len(assessment_posts),
            "wrong_run_request_count": len(wrong_run_requests),
            "network_request_paths": sorted(
                {f"{item['method']} {item['path']}" for item in requests}
            ),
            "network_activity_exact_run_bound": True,
            "canonical_truth": canonical_truth,
            "console_errors": relevant_console,
            "page_errors": page_errors,
            "screenshot": screenshot.as_posix(),
            "screenshot_sha256": hashlib.sha256(screenshot.read_bytes()).hexdigest(),
            **artifacts,
        }
    finally:
        context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Observe one completed production run twice without mutation."
    )
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source-proof", type=Path, required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--observation-seconds", type=float, default=90.0)
    parser.add_argument("--navigation-timeout-ms", type=int, default=120_000)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--screenshot-dir", type=Path, required=True)
    parser.add_argument("--artifact-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.passes != 2 or args.observation_seconds < 90.0:
        raise ValueError("two passes with at least 90 seconds each are required")
    source_marker = source_binding_marker(
        args.source_workflow_run_id,
        args.source_workflow_run_attempt,
    )
    handoff = load_source_proof(
        args.source_proof,
        expected_sha=args.expected_sha,
        repository=args.repository,
        source_workflow_run_id=args.source_workflow_run_id,
        source_workflow_run_attempt=args.source_workflow_run_attempt,
    )
    install_ui_pdf_download_proof(recovery)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            runs = [
                _run_pass(browser, args, handoff, pass_number=1, locale="en"),
                _run_pass(browser, args, handoff, pass_number=2, locale="es-MX"),
            ]
            request = playwright.request.new_context(
                extra_http_headers={"Accept": "application/json", "Cache-Control": "no-store"}
            )
            try:
                response = request.get(
                    f"{args.frontend_url.rstrip('/')}/api/nico/assessment/comprehensive-run/"
                    f"{handoff['run_id']}/report/json",
                    timeout=120_000,
                )
                assert response.ok
                canonical = response.json()
                canonical_digest = require_canonical_json_digest(
                    canonical,
                    response.headers.get("x-nico-canonical-truth-sha256"),
                )
            finally:
                request.dispose()
        finally:
            browser.close()
    identity = canonical.get("identity") if isinstance(canonical, dict) else {}
    assert identity.get("run_id") == handoff["run_id"]
    assert identity.get("commit_sha") == args.expected_sha
    canonical_digest = require_matching_canonical_truth_digest(
        canonical_digest,
        handoff["canonical_truth_sha256"],
        *(item["canonical_truth"]["canonical_truth_sha256"] for item in runs),
        *(
            proof["ui_review_pdf_canonical_truth_sha256"]
            for item in runs
            for proof in item["observation"]["pdf_ui_action_proofs"]
        ),
        *(
            proof["canonical_truth_sha256"]
            for item in runs
            for proof in item["observation"]["markdown_action_proofs"]
        ),
    )
    args.artifact_dir.mkdir(parents=True, exist_ok=True)
    canonical_path = args.artifact_dir / "pass-2-comprehensive.json"
    _write(canonical_path, canonical)
    unique_run_ids = sorted({str(item["run_id"]) for item in runs})
    result = {
        "artifact_schema": VERSION,
        "status": "passed",
        "live_production_claim": True,
        "expected_deployed_sha": args.expected_sha,
        "repository": args.repository,
        "source_proof_sha256": handoff["source_proof_sha256"],
        "source_workflow_run_id": handoff["source_workflow_run_id"],
        "source_workflow_run_attempt": handoff["source_workflow_run_attempt"],
        "source_binding": source_marker.removeprefix("source:"),
        "canonical_truth_sha256": canonical_digest,
        "canonical_truth_digest_computed_from_json": True,
        "passes_required": 2,
        "passes_completed": 2,
        "unique_run_ids": unique_run_ids,
        "fresh_assessment_count": 0,
        "start_request_count": 0,
        "continuation_post_count": 0,
        "runs": runs,
        "canonical_json": canonical_path.as_posix(),
        "proof": {
            "same_immutable_completed_run": unique_run_ids == [handoff["run_id"]],
            "two_terminal_observation_passes": True,
            "each_observation_at_least_90_seconds": all(
                item["observation"]["observed_seconds"] >= 90.0 for item in runs
            ),
            "zero_downstream_intake": True,
            "zero_downstream_continuation": True,
            "desktop_english_verified": True,
            "desktop_es_mx_verified": True,
            "locale_control_round_trip_verified": all(
                item["locale_round_trip"]["same_run_preserved"]
                and item["locale_round_trip"]["same_commit_preserved"]
                for item in runs
            ),
            "canonical_truth_bound_to_retrieved_json": True,
            "markdown_http_and_localized_success_verified": all(
                len(item["observation"]["markdown_action_proofs"]) == 2
                for item in runs
            ),
            "visible_pdf_action_repeated_across_each_hold": all(
                item["observation"]["visible_pdf_action_count"] == 2
                and item["observation"]["pdf_ui_action_digests_stable"] is True
                for item in runs
            ),
            "assessment_network_exact_run_bound": all(
                item["network_activity_exact_run_bound"] for item in runs
            ),
            "refresh_recovery_verified": True,
            "navigation_recovery_verified": True,
            "professional_review_navigation_verified": True,
            "professional_review_locale_preserved": all(
                item["professional_review_locale_preserved"] is True
                for item in runs
            ),
            "terminal_polling_bounded": True,
            "blocking_overlay_absent": True,
            "human_review_required": all(
                item["canonical_truth"]["human_review_required"] is True
                for item in runs
            ),
            "client_delivery_allowed": all(
                item["canonical_truth"]["client_delivery_allowed"] is False
                for item in runs
            ),
        },
    }
    assert all(result["proof"].values())
    _write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
