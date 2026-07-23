#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import hashlib
import html as html_lib
import io
import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

TERMINAL_PHASES = {
    "Complete",
    "Human review required",
    "Run failed or blocked",
    "Continuation timed out",
}
SERVICE_LABELS = {"express": "Express", "comprehensive": "Comprehensive"}
START_PATHS = {
    "express": "/api/nico/assessment/express-run",
    "comprehensive": "/api/nico/assessment/comprehensive-intake",
}
CONTINUATION_PATTERNS = {
    "express": re.compile(r"^/api/nico/assessment/express-run/([^/]+)/status$"),
    "comprehensive": re.compile(r"^/api/nico/assessment/comprehensive-run/([^/]+)/continue$"),
}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Config:
    frontend_origin: str
    repository: str
    expected_sha: str
    output: Path
    screenshot_dir: Path
    artifact_dir: Path
    passes: int
    navigation_timeout_ms: int
    express_timeout_ms: int
    comprehensive_timeout_ms: int


def now_epoch() -> int:
    return int(time.time())


def origin(value: str) -> str:
    parsed = urlparse(str(value or "").strip())
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("frontend URL must be an unauthenticated HTTPS origin")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("frontend URL must not include a path, query, or fragment")
    return f"https://{parsed.hostname.lower()}{f':{parsed.port}' if parsed.port else ''}"


def text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def nested_values(value: Any, key: str) -> list[Any]:
    output: list[Any] = []
    if isinstance(value, dict):
        if key in value:
            output.append(value[key])
        for item in value.values():
            output.extend(nested_values(item, key))
    elif isinstance(value, list):
        for item in value:
            output.extend(nested_values(item, key))
    return output


def first_text(*values: Any) -> str:
    for value in values:
        candidate = text(value, 500)
        if candidate:
            return candidate
    return ""


def first_bool(payload: Any, key: str) -> bool | None:
    for value in nested_values(payload, key):
        if isinstance(value, bool):
            return value
    return None


def run_id(payload: dict[str, Any]) -> str:
    return first_text(payload.get("run_id"), dict_value(payload.get("record")).get("run_id"))


def record(payload: dict[str, Any]) -> dict[str, Any]:
    return dict_value(payload.get("record"))


def stage_results(payload: dict[str, Any]) -> dict[str, Any]:
    return dict_value(record(payload).get("stage_results"))


def report_package(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    if service == "express":
        reports = dict_value(payload.get("reports"))
        if reports:
            return reports
    stages = stage_results(payload)
    for stage_id in (
        "final_comprehensive_report_generation",
        "risk_reduction_and_executive_briefing",
        "decision_report_generation",
        "report_generation",
        "reports",
    ):
        stage = dict_value(stages.get(stage_id))
        package = dict_value(stage.get("report_package")) or dict_value(stage.get("reports"))
        if package:
            return package
    for value in nested_values(payload, "report_package"):
        package = dict_value(value)
        if package.get("markdown") or package.get("pdf_base64"):
            return package
    return {}


def assessment_payload(service: str, payload: dict[str, Any]) -> dict[str, Any]:
    if service == "express" and isinstance(payload.get("sections"), list):
        return payload
    stages = stage_results(payload)
    for stage_id in ("final_comprehensive_report_generation", "evidence_reconciliation_and_scoring"):
        assessment = dict_value(dict_value(stages.get(stage_id)).get("assessment"))
        if assessment:
            return assessment
    assessment = dict_value(payload.get("assessment"))
    return assessment


def status_value(payload: dict[str, Any]) -> str:
    return first_text(payload.get("status"), record(payload).get("status")).lower()


def immutable_commit(payload: dict[str, Any]) -> str:
    candidates = [
        payload.get("commit_sha"),
        dict_value(payload.get("repository_snapshot")).get("commit_sha"),
    ]
    candidates.extend(nested_values(payload, "snapshot_commit_sha"))
    candidates.extend(nested_values(payload, "commit_sha"))
    for value in candidates:
        candidate = text(value, 80).lower()
        if SHA_RE.fullmatch(candidate):
            return candidate
    return ""


def integrity(payload: dict[str, Any]) -> tuple[int | None, str]:
    rec = record(payload)
    revision = rec.get("revision")
    revision_value = int(revision) if isinstance(revision, int) else None
    digest = first_text(rec.get("integrity_sha256"), payload.get("integrity_sha256"))
    return revision_value, digest


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def pdf_evidence(encoded: str, destination: Path) -> dict[str, Any]:
    raw = base64.b64decode(encoded, validate=True)
    if not raw.startswith(b"%PDF"):
        raise AssertionError("report PDF does not begin with the PDF signature")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(raw))
    extracted = "\n".join(page.extract_text() or "" for page in reader.pages)
    return {
        "path": destination.as_posix(),
        "sha256": sha256(raw),
        "page_count": len(reader.pages),
        "text": extracted,
    }


def section_parity(assessment: dict[str, Any], markdown: str, rendered_html: str, pdf_text: str) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for section in list_value(assessment.get("sections")):
        if not isinstance(section, dict):
            continue
        label = first_text(section.get("label"), section.get("id"))
        score = section.get("presented_score", section.get("score"))
        status = first_text(section.get("presented_status"), section.get("status")).upper()
        score_label = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
        if label:
            assert label in markdown, f"Markdown omitted section {label}"
            assert html_lib.escape(label) in rendered_html or label in rendered_html, f"HTML omitted section {label}"
            assert label in pdf_text, f"PDF omitted section {label}"
        assert score_label in markdown, f"Markdown omitted score {score_label} for {label}"
        assert score_label in rendered_html, f"HTML omitted score {score_label} for {label}"
        assert score_label in pdf_text, f"PDF omitted score {score_label} for {label}"
        evidence.append({"label": label, "status": status, "score": score_label})
    return evidence


def validate_report(service: str, payload: dict[str, Any], destination: Path) -> dict[str, Any]:
    package = report_package(service, payload)
    assessment = assessment_payload(service, payload)
    markdown = str(package.get("markdown") or "")
    rendered_html = str(package.get("html") or "")
    encoded_pdf = str(package.get("pdf_base64") or "")
    assert markdown.strip(), f"{service} Markdown report is missing"
    assert rendered_html.strip().lower().startswith("<!doctype html"), f"{service} HTML report is invalid"
    assert encoded_pdf, f"{service} PDF report is missing"
    assert "NONE/100" not in markdown.upper()
    assert "NULL/100" not in markdown.upper()
    pdf = pdf_evidence(encoded_pdf, destination)
    if service == "comprehensive":
        assert package.get("service_id") == "comprehensive"
        assert "NICO Comprehensive Technical Assessment" in markdown
        assert "NICO MID TECHNICAL" not in markdown.upper()
        assert "NICO MID TECHNICAL" not in pdf["text"].upper()
        semantic_markers = (
            "NICO Comprehensive Technical Assessment",
            "Functional QA",
            "Platform Parity",
            "Six-Month Roadmap",
            "Staffing, Sequencing, and Cost",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
        )
        for marker in semantic_markers:
            assert marker in markdown, f"Comprehensive Markdown omitted {marker}"
            assert marker in pdf["text"], f"Comprehensive PDF omitted {marker}"
        upper_markdown = markdown.upper()
        upper_pdf = pdf["text"].upper()
        for stale in ("DRAFT ONLY", "DRAFT - HUMAN REVIEW REQUIRED", "DRAFT · HUMAN REVIEW REQUIRED", "COMPLETE ONLY AS A DRAFT"):
            assert stale not in upper_markdown, f"Comprehensive Markdown retained stale status: {stale}"
            assert stale not in upper_pdf, f"Comprehensive PDF retained stale status: {stale}"
        assert "FINAL REPORT" in upper_markdown
        assert "FINAL REPORT" in upper_pdf
        assert "PENDING HUMAN APPROVAL" in upper_markdown
        assert "PENDING HUMAN APPROVAL" in upper_pdf
        assert "\x7f" not in pdf["text"], "Comprehensive PDF contains a control-character glyph"
        for heading in (
            "Functional QA",
            "Platform Parity",
            "Six-Month Roadmap",
            "Staffing, Sequencing, and Cost",
            "Evidence Appendix",
            "Human Review and Acceptance Gate",
        ):
            assert heading in markdown, f"Comprehensive Markdown omitted {heading}"
            assert heading in pdf["text"], f"Comprehensive PDF omitted {heading}"
    maturity = dict_value(assessment.get("maturity_signal"))
    score = maturity.get("presented_score", maturity.get("score"))
    score_label = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    assert score_label in markdown
    assert score_label in rendered_html
    assert score_label in pdf["text"]
    section_evidence = section_parity(assessment, markdown, rendered_html, pdf["text"])
    truth_values = {
        text(value, 128)
        for value in (
            package.get("canonical_truth_sha256"),
            dict_value(package.get("json")).get("canonical_truth_sha256"),
            payload.get("canonical_truth_sha256"),
        )
        if text(value, 128)
    }
    if len(truth_values) > 1:
        raise AssertionError(f"canonical truth hash drift: {sorted(truth_values)}")
    return {
        "report_id": first_text(package.get("report_id"), payload.get("report_id")),
        "score": score_label,
        "maturity_level": first_text(maturity.get("level")),
        "section_parity": section_evidence,
        "canonical_truth_sha256": next(iter(truth_values), ""),
        "pdf": {key: value for key, value in pdf.items() if key != "text"},
        "semantic_contract": {
            "status": "passed",
            "page_count_informational_only": True,
            "required_sections_verified": True,
            "final_report_language_verified": True,
            "stale_draft_language_absent": True,
            "control_characters_absent": True,
        },
        "markdown_sha256": sha256(markdown.encode("utf-8")),
        "html_sha256": sha256(rendered_html.encode("utf-8")),
    }


def response_json(response: Any) -> dict[str, Any]:
    try:
        value = response.json()
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def ui_state(page: Any) -> dict[str, str]:
    section = page.locator('section[aria-live="polite"]').first
    return section.evaluate(
        """section => {
          const header = section.querySelector('.section-head');
          const phase = header?.querySelector('span')?.textContent?.trim() || '';
          const message = section.querySelector(':scope > p')?.textContent?.trim() || '';
          const articles = Array.from(section.querySelectorAll('article'));
          const find = label => articles.find(article => article.querySelector('b')?.textContent?.trim() === label)?.querySelector('span')?.textContent?.trim() || '';
          return {
            phase_label: phase,
            message,
            run_id: find('Run ID'),
            commit_sha: find('Immutable commit'),
            scanner: find('Scanner'),
            report: find('Report'),
            review: find('Human review'),
            score: find('Technical score'),
            page_url: window.location.href,
          };
        }"""
    )


def wait_for_terminal(page: Any, timeout_ms: int) -> None:
    page.wait_for_function(
        """labels => {
          const section = document.querySelector('section[aria-live="polite"]');
          const value = section?.querySelector('.section-head span')?.textContent?.trim() || '';
          return labels.includes(value);
        }""",
        arg=sorted(TERMINAL_PHASES),
        timeout=timeout_ms,
    )


def verify_language_parity(browser: Any, config: Config) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for locale, path, expected in (
        ("en", "/assessment?tier=express#assessment", ["Express", "Comprehensive"]),
        ("es-MX", "/es/assessment?tier=express#assessment", ["Express", "Integral"]),
    ):
        context = browser.new_context(viewport={"width": 390, "height": 844}, locale=locale)
        page = context.new_page()
        try:
            page.goto(config.frontend_origin + path, wait_until="domcontentloaded", timeout=config.navigation_timeout_ms)
            workspace = page.locator('main[data-assessment-service-count="2"]').first
            workspace.wait_for(state="visible", timeout=config.navigation_timeout_ms)
            buttons = workspace.locator('[aria-label="Assessment type"] button')
            labels = [text(buttons.nth(index).inner_text(), 80) for index in range(buttons.count())]
            assert labels == expected, f"{locale} service labels were {labels}, expected {expected}"
            forbidden = {"Mid", "Full", "Intermedia", "Completa"}
            assert not forbidden.intersection(labels), f"{locale} exposed legacy services: {labels}"
            screenshot = config.screenshot_dir / f"parity-{locale}.png"
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(screenshot), full_page=True)
            results[locale] = {
                "service_count": buttons.count(),
                "labels": labels,
                "screenshot": screenshot.as_posix(),
                "screenshot_sha256": sha256(screenshot.read_bytes()),
            }
        finally:
            context.close()
    return results


def terminal_payload(responses: list[dict[str, Any]], expected_run_id: str) -> dict[str, Any]:
    matching = [item["payload"] for item in responses if run_id(item["payload"]) == expected_run_id]
    if not matching:
        return {}
    for payload in reversed(matching):
        if status_value(payload) in {"complete", "completed", "review_required", "failed", "blocked"}:
            return payload
    return matching[-1]


def status_reconnect(page: Any, service: str, payload: dict[str, Any]) -> dict[str, Any]:
    rid = run_id(payload)
    if service == "express":
        customer = first_text(payload.get("customer_id"))
        project = first_text(payload.get("project_id"))
        response = page.request.post(
            f"/api/nico/assessment/express-run/{rid}/status",
            data={"customer_id": customer, "project_id": project},
        )
    else:
        response = page.request.get(f"/api/nico/assessment/comprehensive-run/{rid}")
    assert 200 <= response.status < 300, f"{service} reconnect returned HTTP {response.status}"
    current = response_json(response)
    assert run_id(current) == rid, f"{service} reconnect changed run identity"
    before_revision, before_integrity = integrity(payload)
    after_revision, after_integrity = integrity(current)
    if before_revision is not None and after_revision is not None:
        assert after_revision >= before_revision
    if before_integrity and after_integrity:
        assert after_integrity == before_integrity
    return {
        "http_status": response.status,
        "run_id": rid,
        "revision_before": before_revision,
        "revision_after": after_revision,
        "integrity_before": before_integrity,
        "integrity_after": after_integrity,
        "identity_preserved": True,
    }


def run_service(browser: Any, config: Config, pass_number: int, service: str) -> dict[str, Any]:
    label = SERVICE_LABELS[service]
    context = browser.new_context(viewport={"width": 390, "height": 844}, locale="en-US")
    page = context.new_page()
    requests: list[dict[str, Any]] = []
    responses: list[dict[str, Any]] = []

    def on_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/nico/assessment/"):
            requests.append({"method": request.method, "path": parsed.path})

    def on_response(response: Any) -> None:
        parsed = urlparse(response.url)
        if not parsed.path.startswith("/api/nico/assessment/"):
            return
        responses.append({
            "method": response.request.method,
            "path": parsed.path,
            "http_status": response.status,
            "payload": response_json(response),
        })

    page.on("request", on_request)
    page.on("response", on_response)
    started_at = now_epoch()
    try:
        page.goto(
            f"{config.frontend_origin}/assessment?tier={service}#assessment",
            wait_until="domcontentloaded",
            timeout=config.navigation_timeout_ms,
        )
        page.locator('main[data-assessment-service-count="2"]').wait_for(state="visible", timeout=config.navigation_timeout_ms)
        button = page.get_by_role("button", name=label, exact=True)
        if button.get_attribute("aria-pressed") != "true":
            button.click()
        client = f"Production Acceptance Pass {pass_number}"
        project = f"NICO {service.title()} Acceptance {pass_number}"
        page.get_by_label("Repository owner/name or GitHub URL").fill(config.repository)
        page.get_by_label("Client name, optional").fill(client)
        page.get_by_label("Project name, optional").fill(project)
        page.get_by_role(
            "checkbox",
            name="I confirm I own this target or have explicit permission to assess it.",
        ).check()
        page.get_by_role("button", name=f"Run {label}", exact=True).click()
        timeout = config.express_timeout_ms if service == "express" else config.comprehensive_timeout_ms
        wait_for_terminal(page, timeout)
        page.wait_for_timeout(1000)
        state = ui_state(page)
        rid = state["run_id"]
        assert rid, f"{service} UI did not expose a run ID"
        start_requests = [item for item in requests if item["method"] == "POST" and item["path"] == START_PATHS[service]]
        assert len(start_requests) == 1, f"{service} emitted {len(start_requests)} start requests"
        continuation = [
            item for item in requests
            if CONTINUATION_PATTERNS[service].fullmatch(item["path"])
        ]
        assert continuation, f"{service} emitted no exact-run continuation requests"
        assert all(CONTINUATION_PATTERNS[service].fullmatch(item["path"]).group(1) == rid for item in continuation)
        observed_run_ids = {
            run_id(item["payload"])
            for item in responses
            if run_id(item["payload"])
        }
        assert observed_run_ids == {rid}, f"{service} response identity drift: {sorted(observed_run_ids)}"
        final = terminal_payload(responses, rid)
        assert final, f"{service} terminal payload was not captured"
        assert state["phase_label"] in {"Complete", "Human review required"}
        assert first_bool(final, "human_review_required") is True
        assert first_bool(final, "client_ready") is not True
        assert first_bool(final, "client_delivery_allowed") is not True
        commit = immutable_commit(final)
        assert commit == config.expected_sha, f"{service} assessed {commit or 'missing SHA'}, expected {config.expected_sha}"
        pdf_path = config.artifact_dir / f"pass-{pass_number}-{service}.pdf"
        report = validate_report(service, final, pdf_path)
        reconnect = status_reconnect(page, service, final)
        screenshot = config.screenshot_dir / f"pass-{pass_number}-{service}.png"
        page.screenshot(path=str(screenshot), full_page=True)
        return {
            "status": "passed",
            "pass": pass_number,
            "service": service,
            "started_at_epoch": started_at,
            "finished_at_epoch": now_epoch(),
            "run_id": rid,
            "repository": first_text(final.get("repository"), config.repository),
            "commit_sha": commit,
            "evidence_ledger_id": first_text(final.get("evidence_ledger_id")),
            "customer_id": first_text(final.get("customer_id")),
            "project_id": first_text(final.get("project_id")),
            "terminal_status": status_value(final),
            "ui": state,
            "start_count": len(start_requests),
            "continuation_count": len(continuation),
            "continuation_paths": sorted({item["path"] for item in continuation}),
            "response_run_ids": sorted(observed_run_ids),
            "human_review_required": True,
            "client_ready": False,
            "client_delivery_allowed": False,
            "report": report,
            "reconnect": reconnect,
            "screenshot": screenshot.as_posix(),
            "screenshot_sha256": sha256(screenshot.read_bytes()),
        }
    finally:
        context.close()


def run(config: Config) -> dict[str, Any]:
    from playwright.sync_api import sync_playwright

    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.screenshot_dir.mkdir(parents=True, exist_ok=True)
    config.artifact_dir.mkdir(parents=True, exist_ok=True)
    started = now_epoch()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            parity = verify_language_parity(browser, config)
            runs: list[dict[str, Any]] = []
            for pass_number in range(1, config.passes + 1):
                for service in ("express", "comprehensive"):
                    runs.append(run_service(browser, config, pass_number, service))
        finally:
            browser.close()
    run_ids = [item["run_id"] for item in runs]
    assert len(run_ids) == len(set(run_ids)), "acceptance runs reused an existing run ID"
    assert len(runs) == config.passes * 2
    assert all(item["status"] == "passed" for item in runs)
    return {
        "artifact_schema": "nico.two_service_live_acceptance.v1",
        "status": "passed",
        "live_production_claim": True,
        "authorized_repository": config.repository,
        "expected_deployed_sha": config.expected_sha,
        "passes_required": config.passes,
        "passes_completed": config.passes,
        "services": ["express", "comprehensive"],
        "language_parity": parity,
        "proof": {
            "two_public_services_only": True,
            "english_spanish_parity": True,
            "one_start_per_service_per_pass": True,
            "exact_run_continuation": True,
            "exact_sha_bound": True,
            "markdown_html_pdf_json_parity": True,
            "comprehensive_depth_verified": True,
            "post_run_reconnect_identity_preserved": True,
            "human_review_required": True,
            "client_delivery_blocked": True,
            "two_consecutive_passes": config.passes >= 2,
        },
        "runs": runs,
        "started_at_epoch": started,
        "finished_at_epoch": now_epoch(),
        "guardrail": "Live automated evidence is a release-acceptance proof, not human approval or client-delivery authorization.",
    }


def parse(argv: list[str] | None = None) -> Config:
    parser = argparse.ArgumentParser(description="Run two consecutive deployed Express and Comprehensive acceptance passes.")
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", default="audit-results/two-service-live-acceptance.json")
    parser.add_argument("--screenshot-dir", default="audit-results/two-service-live-screenshots")
    parser.add_argument("--artifact-dir", default="audit-results/two-service-live-artifacts")
    parser.add_argument("--passes", type=int, default=2)
    parser.add_argument("--navigation-timeout-seconds", type=int, default=120)
    parser.add_argument("--express-timeout-seconds", type=int, default=1200)
    parser.add_argument("--comprehensive-timeout-seconds", type=int, default=3600)
    args = parser.parse_args(argv)
    expected_sha = str(args.expected_sha).strip().lower()
    if not SHA_RE.fullmatch(expected_sha):
        raise ValueError("expected SHA must be an exact lowercase 40-character SHA")
    repository = str(args.repository).strip()
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("repository must use owner/name form")
    if args.passes < 2 or args.passes > 3:
        raise ValueError("acceptance requires two or three consecutive passes")
    return Config(
        frontend_origin=origin(args.frontend_url),
        repository=repository,
        expected_sha=expected_sha,
        output=Path(args.output),
        screenshot_dir=Path(args.screenshot_dir),
        artifact_dir=Path(args.artifact_dir),
        passes=args.passes,
        navigation_timeout_ms=args.navigation_timeout_seconds * 1000,
        express_timeout_ms=args.express_timeout_seconds * 1000,
        comprehensive_timeout_ms=args.comprehensive_timeout_seconds * 1000,
    )


def main(argv: list[str] | None = None) -> int:
    config = parse(argv)
    try:
        result = run(config)
    except Exception as exc:
        result = {
            "artifact_schema": "nico.two_service_live_acceptance.v1",
            "status": "failed",
            "live_production_claim": True,
            "authorized_repository": config.repository,
            "expected_deployed_sha": config.expected_sha,
            "error": f"{type(exc).__name__}: {text(exc, 1200)}",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    config.output.parent.mkdir(parents=True, exist_ok=True)
    config.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Two-service live acceptance: {result['status']}")
    print(f"Evidence: {config.output}")
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValueError as exc:
        print(f"Configuration blocked: {exc}", file=sys.stderr)
        raise SystemExit(2)
