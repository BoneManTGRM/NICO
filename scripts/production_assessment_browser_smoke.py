#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import production_assessment_smoke as smoke

PLAYWRIGHT_VERSION = "1.61.0"
START_PATHS = {
    "express": "/assessment/github",
    "mid": "/assessment/mid-run",
    "full": "/assessment/full-run",
}
EXPECTED_UI_PHASE = {
    "express": "Complete",
    "mid": "Human review required",
    "full": "Human review required",
}
TERMINAL_UI_PHASES = {
    "Complete",
    "Human review required",
    "Run failed or blocked",
    "Continuation timed out",
}
STATUS_PATH_RE = re.compile(r"^/assessment/(mid|full)-run/([^/]+)/status$")


def now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def url_origin(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return ""
    return f"{parsed.scheme.lower()}://{parsed.hostname.lower()}{f':{parsed.port}' if parsed.port else ''}"


def safe_text(value: Any, limit: int = 240) -> str:
    return str(value or "").strip().replace("\n", " ")[:limit]


def is_assessment_path(path: str) -> bool:
    return path in START_PATHS.values() or STATUS_PATH_RE.fullmatch(path) is not None


def response_summary(tier: str, path: str, http_status: int, raw: Any) -> dict[str, Any]:
    payload = smoke.payload_dict(raw)
    customer_id = smoke.first(payload.get("customer_id"), smoke.nested(payload, "assessment").get("customer_id"))
    project_id = smoke.first(payload.get("project_id"), smoke.nested(payload, "assessment").get("project_id"))
    return {
        "path": path,
        "http_status": int(http_status),
        "status": safe_text(payload.get("status") or "unknown", 80),
        "run_id": smoke.run_id(payload),
        "report_id": smoke.report_id(payload),
        "review_request_id": smoke.review_id(payload),
        "customer_id": customer_id,
        "project_id": project_id,
        "human_review_required": smoke.explicit_bool(payload, "human_review_required"),
        "client_ready": smoke.explicit_bool(payload, "client_ready"),
        "terminal": smoke.terminal(tier, payload),
        "failed": smoke.failed(payload),
        "unavailable_or_failed_evidence": smoke.unavailable(payload),
        "payload_present": bool(payload),
    }


def screenshot_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""


def _dedupe(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def build_tier_evidence(
    tier: str,
    backend_origin: str,
    requests: list[dict[str, Any]],
    responses: list[dict[str, Any]],
    ui: dict[str, Any],
    screenshot: Path,
    started_at: str,
    finished_at: str,
    error: str = "",
) -> dict[str, Any]:
    start_path = START_PATHS[tier]
    assessment_requests = [
        item
        for item in requests
        if str(item.get("method") or "").upper() == "POST" and is_assessment_path(str(item.get("path") or ""))
    ]
    expected_requests = [item for item in assessment_requests if item.get("origin") == backend_origin]
    unexpected_origins = sorted({str(item.get("origin") or "") for item in assessment_requests if item.get("origin") != backend_origin})
    start_requests = [item for item in expected_requests if item.get("path") == start_path]
    status_requests = [item for item in expected_requests if STATUS_PATH_RE.fullmatch(str(item.get("path") or ""))]
    start_responses = [item for item in responses if item.get("origin") == backend_origin and item.get("path") == start_path]
    status_responses = [item for item in responses if item.get("origin") == backend_origin and STATUS_PATH_RE.fullmatch(str(item.get("path") or ""))]

    initial = start_responses[-1] if start_responses else {}
    final = status_responses[-1] if status_responses else initial
    initial_run_id = str(initial.get("run_id") or "")
    final_run_id = str(final.get("run_id") or initial_run_id)
    continuation_ids = _dedupe([str(item.get("run_id") or "") for item in status_responses])
    status_paths = [str(item.get("path") or "") for item in status_requests]
    status_codes = [int(item.get("http_status") or 0) for item in status_responses]

    exact = True
    if tier in {"mid", "full"}:
        expected_path = f"/assessment/{tier}-run/{initial_run_id}/status" if initial_run_id else ""
        exact = bool(
            initial_run_id
            and status_requests
            and len(status_requests) == len(status_responses)
            and continuation_ids
            and final_run_id == initial_run_id
            and all(item == initial_run_id for item in continuation_ids)
            and all(path == expected_path for path in status_paths)
        )

    report = str(final.get("report_id") or initial.get("report_id") or "")
    review = str(final.get("review_request_id") or initial.get("review_request_id") or "")
    human_review = final.get("human_review_required") if final else initial.get("human_review_required")
    client_ready = final.get("client_ready") if final else initial.get("client_ready")
    ui_phase = safe_text(ui.get("phase_label"), 100)
    ui_run_id = safe_text(ui.get("run_id"), 200)
    screenshot_hash = screenshot_sha256(screenshot)
    unavailable = _dedupe(
        [
            safe_text(note)
            for response in responses
            for note in response.get("unavailable_or_failed_evidence") or []
        ]
    )[:20]
    response_failures = any(item.get("failed") is True for item in responses)
    response_statuses_ok = bool(start_responses) and all(200 <= int(item.get("http_status") or 0) < 300 for item in start_responses + status_responses)
    identities = bool(final_run_id and report and (tier == "express" or review))
    browser_verified = bool(
        ui_phase == EXPECTED_UI_PHASE[tier]
        and ui_run_id == final_run_id
        and screenshot_hash
        and not error
    )
    passed = bool(
        len(start_requests) == 1
        and len(start_responses) == 1
        and not unexpected_origins
        and response_statuses_ok
        and final.get("terminal") is True
        and not response_failures
        and identities
        and human_review is True
        and client_ready is False
        and exact
        and browser_verified
    )

    return {
        "tier": tier,
        "status": "passed" if passed else "failed",
        "evidence_source": "deployed_browser_network",
        "assessment_terminal_status": str(final.get("status") or "unknown"),
        "start_count": len(start_requests),
        "start_http_status": int(start_responses[-1].get("http_status") or 0) if start_responses else 0,
        "started_at": started_at,
        "finished_at": finished_at,
        "run_id": final_run_id,
        "initial_run_id": initial_run_id,
        "continuation_run_ids": continuation_ids,
        "continuation_status_paths": status_paths,
        "continuation_http_statuses": status_codes,
        "polled_single_exact_status_url": exact,
        "report_id": report,
        "review_request_id": review,
        "human_review_required": human_review,
        "client_ready": client_ready,
        "customer_id": str(final.get("customer_id") or initial.get("customer_id") or ""),
        "project_id": str(final.get("project_id") or initial.get("project_id") or ""),
        "browser_phase": ui_phase,
        "browser_message": safe_text(ui.get("message"), 500),
        "browser_run_id": ui_run_id,
        "browser_url": safe_text(ui.get("page_url"), 500),
        "browser_verified": browser_verified,
        "screenshot_path": screenshot.as_posix(),
        "screenshot_sha256": screenshot_hash,
        "unexpected_assessment_origins": unexpected_origins,
        "unavailable_or_failed_evidence": unavailable,
        "error": safe_text(error, 500),
    }


def _ui_state(page: Any) -> dict[str, str]:
    state = page.locator('section[aria-live="polite"]').first
    return state.evaluate(
        """section => {
          const header = section.querySelector('.section-head');
          const phase = header?.querySelector('span')?.textContent?.trim() || '';
          const message = section.querySelector(':scope > p')?.textContent?.trim() || '';
          const articles = Array.from(section.querySelectorAll('article'));
          const runArticle = articles.find(article => article.querySelector('b')?.textContent?.trim() === 'Run ID');
          const runId = runArticle?.querySelector('span')?.textContent?.trim() || '';
          return {phase_label: phase, message, run_id: runId, page_url: window.location.href};
        }"""
    )


def _wait_for_terminal_ui(page: Any, timeout_ms: float) -> None:
    page.wait_for_function(
        """labels => {
          const section = document.querySelector('section[aria-live="polite"]');
          const value = section?.querySelector('.section-head span')?.textContent?.trim() || '';
          return labels.includes(value);
        }""",
        arg=sorted(TERMINAL_UI_PHASES),
        timeout=timeout_ms,
    )


def run_browser_tier(browser: Any, tier: str, config: dict[str, Any], screenshot_dir: Path) -> dict[str, Any]:
    context = browser.new_context(viewport={"width": 1440, "height": 1100}, locale="en-US")
    page = context.new_page()
    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []
    screenshot = screenshot_dir / f"{tier}.png"
    started_at = now()
    error = ""
    ui: dict[str, Any] = {"phase_label": "", "message": "", "run_id": "", "page_url": ""}

    def on_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if str(request.method or "").upper() != "POST" or not is_assessment_path(parsed.path):
            return
        requests.append({"method": request.method, "origin": url_origin(request.url), "path": parsed.path})

    def on_response(response: Any) -> None:
        parsed = urlparse(response.url)
        if str(response.request.method or "").upper() != "POST" or not is_assessment_path(parsed.path):
            return
        summary: dict[str, Any]
        try:
            summary = response_summary(tier, parsed.path, response.status, response.json())
        except Exception as exc:  # Browser proof must retain invalid or unreadable responses as failure evidence.
            summary = response_summary(tier, parsed.path, response.status, {})
            summary["response_error"] = type(exc).__name__
        responses.append({"origin": url_origin(response.url), **summary})

    page.on("request", on_request)
    page.on("response", on_response)
    try:
        page.goto(
            f"{config['frontend_origin']}/assessment?tier={tier}#assessment",
            wait_until="domcontentloaded",
            timeout=config["request_timeout"] * 1000,
        )
        label = tier.capitalize()
        tier_button = page.get_by_role("button", name=label, exact=True)
        if tier_button.get_attribute("aria-pressed") != "true":
            tier_button.click()
        page.get_by_label("Repository owner/name or GitHub URL").fill(config["repository"])
        page.get_by_label("Client name, optional").fill(config["customer_id"])
        page.get_by_label("Project name, optional").fill(config["project_id"])
        page.get_by_role(
            "checkbox",
            name="I confirm I own this target or have explicit permission to assess it.",
        ).check()
        page.get_by_role("button", name=f"Run {label} assessment", exact=True).click()
        if tier == "express":
            terminal_timeout_ms = (config["express_timeout"] + 60) * 1000
        else:
            terminal_timeout_ms = (
                config["max_polls"] * config["poll_interval"]
                + config["request_timeout"]
                + 60
            ) * 1000
        _wait_for_terminal_ui(page, terminal_timeout_ms)
        page.wait_for_timeout(750)
        ui = _ui_state(page)
    except Exception as exc:
        error = f"{type(exc).__name__}: {safe_text(exc, 420)}"
        try:
            ui = _ui_state(page)
        except Exception:
            ui = {"phase_label": "unavailable", "message": error, "run_id": "", "page_url": page.url}
    finally:
        screenshot.parent.mkdir(parents=True, exist_ok=True)
        try:
            page.screenshot(path=str(screenshot), full_page=True)
        except Exception as exc:
            error = safe_text(f"{error}; screenshot {type(exc).__name__}" if error else f"screenshot {type(exc).__name__}", 500)
        finished_at = now()
        context.close()

    return build_tier_evidence(
        tier,
        config["backend_origin"],
        requests,
        responses,
        ui,
        screenshot,
        started_at,
        finished_at,
        error,
    )


def failed_browser_evidence(config: dict[str, Any], reason: str) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "evidence_kind": "deployed_browser_assessment_proof",
        "status": "failed",
        "generated_at": now(),
        "playwright_version": PLAYWRIGHT_VERSION,
        "frontend_origin": config["frontend_origin"],
        "backend_origin": config["backend_origin"],
        "repository": config["repository"],
        "tenant": {},
        "proof": {
            "one_start_per_tier": False,
            "exact_run_continuation": False,
            "matching_browser_network_identity": False,
            "screenshots_retained": False,
            "same_isolated_tenant": False,
            "no_unexpected_assessment_origins": False,
        },
        "tiers": [],
        "error": safe_text(reason, 500),
    }


def run_browser_proof(config: dict[str, Any], screenshot_dir: Path) -> dict[str, Any]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return failed_browser_evidence(config, f"Playwright unavailable: {type(exc).__name__}")

    tiers: list[dict[str, Any]] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                for tier in ("express", "mid", "full"):
                    tiers.append(run_browser_tier(browser, tier, config, screenshot_dir))
            finally:
                browser.close()
    except Exception as exc:
        evidence = failed_browser_evidence(config, f"Browser launch or execution failed: {type(exc).__name__}: {safe_text(exc, 360)}")
        evidence["tiers"] = tiers
        return evidence

    customer_ids = {str(item.get("customer_id") or "") for item in tiers if item.get("customer_id")}
    project_ids = {str(item.get("project_id") or "") for item in tiers if item.get("project_id")}
    same_tenant = bool(
        len(customer_ids) == 1
        and len(project_ids) == 1
        and next(iter(customer_ids)).startswith("customer_production_smoke_")
        and next(iter(project_ids)).startswith("project_production_smoke_")
    )
    proof = {
        "one_start_per_tier": len(tiers) == 3 and all(item.get("start_count") == 1 for item in tiers),
        "exact_run_continuation": all(item.get("polled_single_exact_status_url") is True for item in tiers if item.get("tier") in {"mid", "full"}),
        "matching_browser_network_identity": len(tiers) == 3 and all(item.get("browser_verified") is True for item in tiers),
        "screenshots_retained": len(tiers) == 3 and all(bool(item.get("screenshot_sha256")) for item in tiers),
        "same_isolated_tenant": same_tenant,
        "no_unexpected_assessment_origins": len(tiers) == 3 and all(not item.get("unexpected_assessment_origins") for item in tiers),
    }
    passed = len(tiers) == 3 and all(proof.values()) and all(item.get("status") == "passed" for item in tiers)
    return {
        "schema_version": 1,
        "evidence_kind": "deployed_browser_assessment_proof",
        "status": "passed" if passed else "failed",
        "generated_at": now(),
        "playwright_version": PLAYWRIGHT_VERSION,
        "frontend_origin": config["frontend_origin"],
        "backend_origin": config["backend_origin"],
        "repository": config["repository"],
        "tenant": {
            "customer_id": next(iter(customer_ids)) if len(customer_ids) == 1 else "",
            "project_id": next(iter(project_ids)) if len(project_ids) == 1 else "",
        },
        "proof": proof,
        "tiers": tiers,
        "error": "",
    }


def combined_artifact(
    config: dict[str, Any],
    deploy: dict[str, Any],
    ready: dict[str, Any],
    browser_evidence: dict[str, Any],
) -> dict[str, Any]:
    tiers = browser_evidence.get("tiers") if isinstance(browser_evidence.get("tiers"), list) else []
    result = smoke.artifact(config, deploy, ready, tiers)
    result["schema_version"] = 2
    result["evidence_kind"] = "authorized_live_production_browser_api_smoke"
    requested_tenant = result.get("tenant")
    result["requested_tenant_labels"] = requested_tenant
    if browser_evidence.get("tenant"):
        result["tenant"] = browser_evidence["tenant"]
    browser_proof = browser_evidence.get("proof") if isinstance(browser_evidence.get("proof"), dict) else {}
    result["proof"].update(
        {
            "matching_browser_evidence": browser_proof.get("matching_browser_network_identity") is True,
            "screenshots_retained": browser_proof.get("screenshots_retained") is True,
            "same_isolated_browser_tenant": browser_proof.get("same_isolated_tenant") is True,
            "no_unexpected_assessment_origins": browser_proof.get("no_unexpected_assessment_origins") is True,
            "browser_generated_the_only_api_starts": len(tiers) == 3 and all(item.get("evidence_source") == "deployed_browser_network" for item in tiers),
        }
    )
    result["browser_evidence"] = {
        "status": browser_evidence.get("status"),
        "generated_at": browser_evidence.get("generated_at"),
        "playwright_version": browser_evidence.get("playwright_version"),
        "frontend_origin": browser_evidence.get("frontend_origin"),
        "backend_origin": browser_evidence.get("backend_origin"),
        "proof": browser_proof,
        "screenshots": [
            {
                "tier": item.get("tier"),
                "path": item.get("screenshot_path"),
                "sha256": item.get("screenshot_sha256"),
            }
            for item in tiers
        ],
    }
    result["limitations"] = [
        "The deployed browser UI generated the only assessment start request for each tier; the evidence finalizer did not issue separate API starts.",
        *result["limitations"],
        "Screenshots and browser-network summaries are retained, but full response bodies and credentials are deliberately excluded.",
    ]
    passed = (
        result.get("status") == "passed"
        and browser_evidence.get("status") == "passed"
        and all(result["proof"].values())
    )
    result["status"] = "passed" if passed else "failed"
    return result


def combined_markdown(result: dict[str, Any]) -> str:
    base = smoke.markdown(result).rstrip()
    browser = result.get("browser_evidence") if isinstance(result.get("browser_evidence"), dict) else {}
    proof = browser.get("proof") if isinstance(browser.get("proof"), dict) else {}
    lines = [
        base,
        "",
        "## Browser evidence",
        "",
        f"- Browser proof status: `{browser.get('status') or 'failed'}`",
        f"- Playwright: `{browser.get('playwright_version') or 'unknown'}`",
        f"- Matching browser/network identity: `{proof.get('matching_browser_network_identity')}`",
        f"- Screenshots retained: `{proof.get('screenshots_retained')}`",
        f"- Same isolated tenant: `{proof.get('same_isolated_tenant')}`",
        "",
    ]
    for screenshot in browser.get("screenshots") or []:
        lines.append(f"- {screenshot.get('tier')}: `{screenshot.get('path')}` · `{screenshot.get('sha256') or 'missing'}`")
    return "\n".join(lines) + "\n"


def parse(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the guarded NICO production smoke through the deployed browser UI.")
    for name in (
        "frontend-url",
        "backend-url",
        "repository",
        "allowlisted-repository",
        "allowed-hosts",
        "authorization-reference",
        "confirmation",
        "commit-sha",
        "github-repository",
        "backend-status-context",
    ):
        parser.add_argument(f"--{name}", required=True)
    parser.add_argument("--customer-id", default="production_smoke_customer")
    parser.add_argument("--project-id", default="production_smoke_project")
    parser.add_argument("--frontend-status-context", default="Vercel")
    parser.add_argument("--output-json", default="audit-results/production-assessment-smoke.json")
    parser.add_argument("--output-markdown", default="audit-results/production-assessment-smoke.md")
    parser.add_argument("--browser-evidence-json", default="audit-results/production-assessment-browser-evidence.json")
    parser.add_argument("--preflight-output", default="audit-results/production-assessment-preflight.json")
    parser.add_argument("--screenshot-dir", default="audit-results/production-assessment-browser")
    parser.add_argument("--max-polls", type=int, default=200)
    parser.add_argument("--poll-interval-seconds", type=float, default=3.0)
    parser.add_argument("--request-timeout-seconds", type=float, default=smoke.DEFAULT_REQUEST_TIMEOUT_SECONDS)
    parser.add_argument("--express-timeout-seconds", type=float, default=smoke.DEFAULT_EXPRESS_TIMEOUT_SECONDS)
    parser.add_argument("--preflight-only", action="store_true")
    return parser.parse_args(argv)


def config_from(args: argparse.Namespace) -> dict[str, Any]:
    return smoke.validate(
        {
            "frontend_origin": smoke.origin(args.frontend_url, "frontend URL"),
            "backend_origin": smoke.origin(args.backend_url, "backend URL"),
            "repository": args.repository.strip(),
            "allowlisted_repository": args.allowlisted_repository.strip(),
            "allowed_hosts": smoke.allowed_hosts(args.allowed_hosts),
            "customer_id": args.customer_id.strip(),
            "project_id": args.project_id.strip(),
            "authorization_reference": args.authorization_reference.strip(),
            "confirmation": args.confirmation,
            "commit_sha": args.commit_sha.strip().lower(),
            "github_repository": args.github_repository.strip(),
            "frontend_status_context": args.frontend_status_context.strip(),
            "backend_status_context": args.backend_status_context.strip(),
            "admin_token": os.environ.get("NICO_PRODUCTION_SMOKE_ADMIN_TOKEN", ""),
            "github_token": os.environ.get("GITHUB_TOKEN", ""),
            "output_json": Path(args.output_json),
            "output_markdown": Path(args.output_markdown),
            "browser_evidence_json": Path(args.browser_evidence_json),
            "preflight_output": Path(args.preflight_output),
            "screenshot_dir": Path(args.screenshot_dir),
            "max_polls": args.max_polls,
            "poll_interval": args.poll_interval_seconds,
            "request_timeout": args.request_timeout_seconds,
            "express_timeout": args.express_timeout_seconds,
        }
    )


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse(argv)
    config = config_from(args)
    deploy = smoke.deployment(config)
    ready = smoke.preflight(config)
    preflight_result = {
        "schema_version": 1,
        "evidence_kind": "authorized_production_smoke_preflight",
        "status": "passed" if deploy.get("verified") and ready.get("verified") else "failed",
        "generated_at": now(),
        "source_commit_sha": config["commit_sha"],
        "repository": config["repository"],
        "deployment": deploy,
        "preflight": ready,
    }
    write_json(config["preflight_output"], preflight_result)
    if args.preflight_only:
        print(f"Production smoke preflight status: {preflight_result['status']}")
        return 0 if preflight_result["status"] == "passed" else 1

    if preflight_result["status"] == "passed":
        browser_evidence = run_browser_proof(config, config["screenshot_dir"])
    else:
        browser_evidence = failed_browser_evidence(config, "Deployment or health preflight failed; no assessment was started.")
    result = combined_artifact(config, deploy, ready, browser_evidence)
    write_json(config["browser_evidence_json"], browser_evidence)
    write_json(config["output_json"], result)
    config["output_markdown"].parent.mkdir(parents=True, exist_ok=True)
    config["output_markdown"].write_text(combined_markdown(result), encoding="utf-8")
    print(f"Production browser/API assessment smoke status: {result['status']}")
    print(f"Evidence written to: {config['output_json']}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
