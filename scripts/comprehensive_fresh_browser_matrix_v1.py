#!/usr/bin/env python3
"""Fresh intake/execution in the three previously reopening-only browser cells.

Uses the existing production-proof OIDC scope and public smoke repository only.
The emulated devices do not claim physical iPhone or Android qualification.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from nico.complete_assessment_gate_v1 import require_retained_assessment
from scripts.comprehensive_production_run_handoff_v1 import (
    load_source_proof, require_canonical_json_digest, require_matching_canonical_truth_digest,
)
from scripts.github_actions_nico_proof_auth_v1 import AuthenticatedBrowser, acquire_production_proof_session

VERSION = "nico.comprehensive_fresh_browser_matrix.v1"
CELLS = (
    ("mobile-chromium-en", "chromium", "en"),
    ("iphone-webkit-en", "webkit", "en"),
    ("iphone-webkit-es-MX", "webkit", "es-MX"),
)
ORIGIN = "https://app.nicoaudit.com"
REPOSITORY = "https://gitlab.com/gitlab-org/gitlab-test"
CLIENT = "TEST ENGAGEMENT — NOT A CLIENT ASSESSMENT"


def context_options(engine: str, language: str) -> dict:
    assert engine in {"chromium", "webkit"} and language in {"en", "es-MX"}
    return {
        "viewport": {"width": 390, "height": 844},
        "screen": {"width": 390, "height": 844},
        "device_scale_factor": 3,
        "is_mobile": True,
        "has_touch": True,
        "locale": "en-US" if language == "en" else language,
        "service_workers": "block",
        "extra_http_headers": {"Cache-Control": "no-store", "Pragma": "no-cache"},
    }


def verify_intake(requests: list[dict], language: str, project: str) -> dict:
    matches = [x for x in requests if x["method"] == "POST" and
               x["path"] == "/api/nico/assessment/comprehensive-intake"]
    assert len(matches) == 1, "Fresh browser cell must submit exactly one intake"
    payload = json.loads(matches[0]["body"])
    assert payload.get("report_language") == language
    assert payload.get("client_name") == CLIENT
    assert payload.get("project_name") == project
    # Do not retain credentials or the entire intake body.
    return {"intake_request_count": 1, "intake_report_language": language,
            "intake_client_name": CLIENT, "intake_project_name": project}


def retain(path: Path, body: bytes, *, response=None) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    result = {"path": path.name, "size_bytes": len(body),
              "sha256": hashlib.sha256(body).hexdigest()}
    if response is not None:
        # Whitelist identity headers; never retain cookies or session headers.
        result["http_status"] = response.status
        result["identity_headers"] = {
            key: value for key, value in response.headers.items()
            if key in {"x-nico-run-id", "x-nico-artifact-sha256",
                       "x-nico-canonical-truth-sha256", "x-nico-report-language"}
        }
    return result


def read_status(page, run_id: str):
    import mobile_restart_live_acceptance_v1 as recovery

    response = page.request.get(
        f"{ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={"Accept": "application/json", "Cache-Control": "no-store",
                 recovery.BROWSER_PROJECTION_HEADER: recovery.BROWSER_PROJECTION_VALUE},
        timeout=60_000,
    )
    assert response.ok, f"Run status returned HTTP {response.status}"
    return response


def verify_terminal(payload: dict, canonical: dict, run_id: str, commit: str) -> dict:
    assert payload.get("run_id") == run_id and payload.get("commit_sha") == commit
    assert payload.get("terminal") is True
    assert payload.get("human_review_required") is True
    assert payload.get("client_delivery_allowed") is False
    identity = canonical.get("identity") or {}
    assert identity.get("run_id") == run_id and identity.get("commit_sha") == commit
    return require_retained_assessment(canonical, payload, expected_commit=commit, expected_run=run_id)


def run_cell(playwright, session: str, cell: tuple, args, commit: str, evidence: dict):
    from pypdf import PdfReader
    import mobile_restart_live_acceptance_v1 as recovery
    import spanish_comprehensive_live_acceptance_v1 as scope
    import spanish_comprehensive_live_acceptance_v2 as telemetry

    name, engine, language = cell
    evidence["started_at"] = datetime.now(timezone.utc).isoformat()
    folder = args.output.parent / name
    folder.mkdir(parents=True, exist_ok=True)
    evidence.update({"cell": name, "status": "running", "browser_engine": engine,
                     "browser_conditions": context_options(engine, language),
                     "emulation": "390x844 CSS pixels, 3x scale, mobile/touch; not a physical device",
                     "application_revision": args.expected_sha, "assessed_commit_sha": commit,
                     "stages_exercised": [], "files": []})
    raw_browser = getattr(playwright, engine).launch(headless=True)
    evidence["browser_version"] = raw_browser.version
    browser = AuthenticatedBrowser(raw_browser, session=session, frontend_url=ORIGIN)
    context = browser.new_context(**context_options(engine, language))
    page = context.new_page()
    requests = []
    run_id = ""
    completed = False
    scope._install_reserved_proof_scope(page)

    def record(request):
        path = urlparse(request.url).path
        if path.startswith("/api/nico/assessment/"):
            requests.append({"method": request.method, "path": path,
                             "body": (request.post_data or "") if path.endswith("/comprehensive-intake") else ""})

    page.on("request", record)
    try:
        route = "/es/assessment" if language == "es-MX" else "/assessment"
        page.goto(f"{ORIGIN}{route}?tier=comprehensive&fresh_browser_cell={name}#assessment",
                  wait_until="domcontentloaded", timeout=120_000)
        page.locator(scope.SPANISH_HYDRATED_WORKSPACE_SELECTOR).first.wait_for(state="visible", timeout=120_000)
        page.wait_for_function("language => document.documentElement.lang === language", arg=language, timeout=120_000)
        spanish = language == "es-MX"
        project = f"TEST — fresh browser qualification — {name}"
        page.get_by_label("URL o identificador del repositorio" if spanish else "Repository URL or identifier").fill(REPOSITORY)
        page.get_by_label("Nombre del cliente, opcional" if spanish else "Client name, optional").fill(CLIENT)
        page.get_by_label("Nombre del proyecto, opcional" if spanish else "Project name, optional").fill(project)
        page.locator(recovery.AUTHORIZATION_SELECTOR).check()
        page.locator(recovery.ACTION_SELECTOR).click()
        run_id, _ = recovery._wait_for_run_id(page, 180.0)
        evidence["run_id"] = run_id
        evidence.update(verify_intake(requests, language, project))
        evidence["stages_exercised"].append("fresh browser intake")
        scope._verify_proof_scope(page, ORIGIN, run_id)
        capture_deadline = time.monotonic() + 180
        while True:
            captured = read_status(page, run_id).json()
            if captured.get("commit_sha"):
                assert captured["commit_sha"] == commit, "Assessed source changed from fixed producer commit"
                break
            assert not captured.get("terminal"), "Source acquisition failed before immutable capture"
            assert time.monotonic() < capture_deadline, "Immutable source capture was not retained"
            page.wait_for_timeout(500)
        evidence["source_commit_verified_before_reload"] = True
        # Reload the actual new run; never submit a replacement if restoration fails.
        evidence["reload"] = recovery._reload_and_restore(page, run_id, 120_000, expect_active_storage=True)
        evidence["stages_exercised"].append("same-run reload")
        telemetry._FRONTEND_ORIGIN = ORIGIN
        telemetry._OUTPUT_PATH = folder / "execution-progress.json"
        telemetry._wait_for_terminal_with_telemetry(page, run_id, args.timeout_seconds)
        evidence["terminal_ui"] = recovery._wait_for_terminal_ui_ready(page, run_id, commit, 240.0)
        evidence["stages_exercised"].append("assessment execution through terminal UI")
        status = read_status(page, run_id)
        payload = status.json()
        report = page.request.get(f"{ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}/report/json", timeout=120_000)
        assert report.ok, f"Canonical JSON returned HTTP {report.status}"
        canonical = report.json()
        evidence["scanner_retention"] = verify_terminal(payload, canonical, run_id, commit)
        digest = require_canonical_json_digest(canonical, report.headers.get("x-nico-canonical-truth-sha256"))
        require_matching_canonical_truth_digest(digest, payload["reports"]["canonical_truth_sha256"])
        evidence["canonical_truth_sha256"] = digest
        evidence["files"].append(retain(folder / "terminal-status.json", status.body(), response=status))
        evidence["files"].append(retain(folder / "canonical-report.json", report.body(), response=report))
        pdf = page.request.get(f"{ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}/localized-report/{language}/pdf", timeout=300_000)
        assert pdf.ok and pdf.body().startswith(b"%PDF")
        assert pdf.headers.get("x-nico-run-id") == run_id
        assert pdf.headers.get("x-nico-report-language") == language
        assert pdf.headers.get("x-nico-artifact-sha256") == hashlib.sha256(pdf.body()).hexdigest()
        require_matching_canonical_truth_digest(digest, pdf.headers.get("x-nico-canonical-truth-sha256"))
        text = " ".join(" ".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf.body())).pages).split())
        assert run_id in text, "PDF must contain actual run identity"
        evidence["files"].append(retain(folder / f"report-{language}.pdf", pdf.body(), response=pdf))
        markdown = page.request.get(f"{ORIGIN}/api/nico/assessment/comprehensive-run/{run_id}/localized-report/{language}", timeout=300_000)
        assert markdown.ok
        rendered = markdown.json()
        assert rendered.get("run_id") == run_id and rendered.get("commit_sha") == commit
        assert rendered.get("report_language") == language and rendered.get("assessment_rerun") is False
        require_matching_canonical_truth_digest(digest, rendered.get("canonical_truth_sha256"))
        body = str((rendered.get("report") or {}).get("markdown") or "").encode("utf-8")
        assert body.strip()
        evidence["files"].append(retain(folder / f"report-{language}.md", body))
        evidence["files"].append(retain(folder / "localized-rendering.json", markdown.body(), response=markdown))
        evidence["stages_exercised"].append("authenticated canonical JSON, localized PDF and Markdown byte retrieval")
        evidence.update(verify_intake(requests, language, project))
        assert recovery._continuation_count(requests) == 0
        evidence["continuation_request_count"] = 0
        after = read_status(page, run_id).json()
        assert (after.get("revision"), after.get("integrity_sha256"), after.get("status")) == (
            payload.get("revision"), payload.get("integrity_sha256"), payload.get("status"))
        evidence["terminal_state_unchanged_after_exports"] = True
        screenshot = folder / "terminal.png"
        page.screenshot(path=str(screenshot), full_page=False, timeout=15_000)
        evidence["files"].append(retain(screenshot, screenshot.read_bytes()))
        evidence["status"] = "passed"
        evidence["professional_review_or_delivery_approval"] = False
        completed = True
    finally:
        if run_id and not completed:
            evidence["cleanup"] = scope._cancel_proof_run(page, ORIGIN, run_id)
        context.close()
        raw_browser.close()
        evidence["finished_at"] = datetime.now(timezone.utc).isoformat()


def main(argv=None) -> int:
    from playwright.sync_api import sync_playwright
    import mobile_restart_live_acceptance_v1 as recovery

    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--source-proof", type=Path, required=True)
    parser.add_argument("--source-workflow-run-id", required=True)
    parser.add_argument("--source-workflow-run-attempt", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=900)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    assert re.fullmatch(r"[0-9a-f]{40}", args.expected_sha)
    assert 0 < args.timeout_seconds <= 1200
    handoff = load_source_proof(args.source_proof, expected_sha=args.expected_sha, repository=REPOSITORY,
                               source_workflow_run_id=args.source_workflow_run_id,
                               source_workflow_run_attempt=args.source_workflow_run_attempt,
                               expected_proof_tool_sha=args.expected_sha)
    result = {"artifact_schema": VERSION, "status": "running", "cells": [],
              "application_revision": args.expected_sha, "source_proof_sha256": hashlib.sha256(args.source_proof.read_bytes()).hexdigest(),
              "source_binding": f"{args.source_workflow_run_id}:{args.source_workflow_run_attempt}",
              "session_token_retained": False}
    session = ""
    try:
        with sync_playwright() as playwright:
            for cell in CELLS:
                evidence = {}
                result["cells"].append(evidence)
                try:
                    # Each bounded cell gets a fresh unchanged restricted session.
                    session, auth = acquire_production_proof_session(ORIGIN)
                    evidence["authentication"] = auth
                    run_cell(playwright, session, cell, args, handoff["assessed_commit_sha"], evidence)
                except Exception as exc:
                    evidence.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:1000]}")
                finally:
                    recovery._write(args.output, result)
        if any(x.get("status") != "passed" for x in result["cells"]):
            result["status"] = "failed"
            return 1
        assert len({x["run_id"] for x in result["cells"]}) == len(CELLS)
        assert handoff["run_id"] not in {x["run_id"] for x in result["cells"]}
        result["status"] = "passed"
        return 0
    except Exception as exc:
        result.update(status="failed", error=f"{type(exc).__name__}: {str(exc)[:1000]}")
        return 1
    finally:
        recovery._write(args.output, result)
        session = ""


if __name__ == "__main__":
    raise SystemExit(main())
