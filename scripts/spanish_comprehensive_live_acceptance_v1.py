#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright
from pypdf import PdfReader

import mobile_restart_live_acceptance_v1 as recovery

VERSION = "nico.spanish_comprehensive_live_acceptance.v1"
SPANISH_ROUTE = "/es/assessment"
SPANISH_REPO_LABEL = "Propietario/nombre del repositorio o URL de GitHub"
SPANISH_CLIENT_LABEL = "Nombre del cliente, opcional"
SPANISH_PROJECT_LABEL = "Nombre del proyecto, opcional"
SPANISH_TERMINAL_PHASE = "Revisión interna requerida"
SPANISH_HYDRATED_WORKSPACE_SELECTOR = (
    recovery.WORKSPACE_SELECTOR
    + '[data-assessment-hydrated="true"]'
    + '[data-assessment-client-copy-verified="true"]'
)
SPANISH_PDF_MARKERS = (
    "Evaluación Técnica Integral",
    "Resumen ejecutivo",
    "Cuadro de puntuación técnica",
)
FORBIDDEN_PDF_MARKERS = (
    "NICO Comprehensive Technical Assessment",
    "missing Spanish presentation translation",
    "v2_production_publication_failed",
    "Finding ID:",
    "Category / status:",
    "Exact source:",
    "Analyzer / rule:",
    "Technical consequence:",
    "Business consequence:",
    "Specific correction:",
    "Owner / effort:",
    "Cost of inaction:",
    "Residual risk:",
    "Acceptance / exit criteria:",
    "Final exit criteria:",
)


def _bounded(value: Any, limit: int = 800) -> str:
    text = " ".join(str(value or "").split()).strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _intake_languages(requests: list[dict[str, str]]) -> list[str]:
    values: list[str] = []
    for item in requests:
        if (
            item.get("method") != "POST"
            or item.get("path") != "/api/nico/assessment/comprehensive-intake"
        ):
            continue
        try:
            payload = json.loads(item.get("body") or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            language = str(payload.get("report_language") or "").strip()
            if language:
                values.append(language)
    return values


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return " ".join(
        " ".join(page.extract_text() or "" for page in reader.pages).split()
    )


def _wait_for_spanish_hydration(page: Any, timeout_ms: int) -> None:
    """Wait for the real client boundary before asserting localized document semantics.

    The assessment workspace is server-rendered and can become visible before React
    effects bind the route locale. A production proof that asserts ``<html lang>`` at
    that earlier boundary is timing-dependent even when the deployed Spanish client is
    correct. Require NICO's explicit hydrated/copy-verified marker, then require the
    Spanish document-language binder itself. This keeps the proof fail-closed without
    accepting the pre-hydration English root as a false production failure.
    """

    page.locator(SPANISH_HYDRATED_WORKSPACE_SELECTOR).first.wait_for(
        state="visible",
        timeout=timeout_ms,
    )
    page.wait_for_function(
        """() => (
          document.documentElement.lang === 'es-MX'
          && document.documentElement.dataset.nicoAssessmentDocumentLanguage === 'es-MX'
        )""",
        timeout=timeout_ms,
    )


def _verify_spanish_terminal_artifacts(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
) -> dict[str, Any]:
    status = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            recovery.BROWSER_PROJECTION_HEADER: recovery.BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=60_000,
    )
    status_bytes = status.body()
    assert status.ok, f"Projected Spanish terminal status returned HTTP {status.status}"
    assert len(status_bytes) < 200_000, f"Projected terminal status was {len(status_bytes)} bytes"
    payload = status.json()
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    assert payload.get("run_id") == run_id
    assert payload.get("terminal") is True
    assert payload.get("human_review_required") is True
    assert payload.get("client_delivery_allowed") is False
    assert reports.get("response_bounded") is True
    assert reports.get("artifact_delivery") == "on_demand_exact_run"
    assert reports.get("pdf_available") is True
    assert reports.get("markdown_available") is True

    pdf = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/report/pdf",
        headers={"Accept": "application/pdf", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    pdf_bytes = pdf.body()
    assert pdf.ok, f"Exact-run Spanish PDF returned HTTP {pdf.status}"
    assert pdf_bytes.startswith(b"%PDF"), "Spanish report did not have a PDF signature"
    assert pdf.headers.get("x-nico-run-id") == run_id
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    header_sha = str(pdf.headers.get("x-nico-artifact-sha256") or "").lower()
    assert not header_sha or header_sha == observed_sha

    rendered = _pdf_text(pdf_bytes)
    missing = [marker for marker in SPANISH_PDF_MARKERS if marker not in rendered]
    forbidden = [marker for marker in FORBIDDEN_PDF_MARKERS if marker in rendered]
    assert not missing, f"Spanish PDF omitted required presentation markers: {missing}"
    assert not forbidden, f"Spanish PDF retained forbidden English/failure markers: {forbidden}"

    return {
        "terminal_manifest_size_bytes": len(status_bytes),
        "terminal_manifest_bounded": True,
        "report_artifact_delivery": reports.get("artifact_delivery"),
        "pdf_size_bytes": len(pdf_bytes),
        "pdf_sha256": observed_sha,
        "pdf_signature_verified": True,
        "pdf_run_identity_verified": True,
        "spanish_pdf_presentation_verified": True,
        "spanish_pdf_markers_verified": list(SPANISH_PDF_MARKERS),
        "forbidden_pdf_markers_absent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def run_proof(browser: Any, args: argparse.Namespace) -> dict[str, Any]:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="es-MX",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    requests: list[dict[str, str]] = []

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if not parsed.path.startswith("/api/nico/assessment/"):
            return
        entry = {"method": request.method, "path": parsed.path, "body": ""}
        if (
            request.method == "POST"
            and parsed.path == "/api/nico/assessment/comprehensive-intake"
        ):
            try:
                entry["body"] = str(request.post_data or "")
            except Exception:
                entry["body"] = ""
        requests.append(entry)

    page.on("request", record_request)
    started_at = time.time()
    origin = args.frontend_url.rstrip("/")
    try:
        page.goto(
            f"{origin}{SPANISH_ROUTE}?tier=comprehensive&spanish_production_probe={time.time_ns()}#assessment",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        _wait_for_spanish_hydration(page, args.navigation_timeout_ms)
        assert page.evaluate("() => document.documentElement.lang") == "es-MX"

        page.get_by_label(SPANISH_REPO_LABEL).fill(args.repository)
        page.get_by_label(SPANISH_CLIENT_LABEL).fill("")
        page.get_by_label(SPANISH_PROJECT_LABEL).fill("")
        page.locator(recovery.AUTHORIZATION_SELECTOR).check()
        page.locator(recovery.ACTION_SELECTOR).click()

        run_id, initial_stored = recovery._wait_for_run_id(page, 180.0)
        assert recovery._start_count(requests) == 1
        languages = _intake_languages(requests)
        assert languages == ["es-MX"], f"Spanish intake did not persist report_language=es-MX: {languages}"

        recovery._wait_for_terminal(page, run_id, args.timeout_seconds)
        terminal = recovery._wait_for_terminal_ui_ready(
            page,
            run_id,
            args.expected_sha,
            240.0,
        )
        assert terminal.get("phase") == SPANISH_TERMINAL_PHASE, terminal
        assert terminal.get("report_actions_present") == "true", terminal
        assert terminal.get("pdf_enabled") == "true", terminal
        assert terminal.get("markdown_enabled") == "true", terminal

        artifacts = _verify_spanish_terminal_artifacts(
            page,
            frontend_origin=origin,
            run_id=run_id,
        )
        screenshot_path = args.output.with_suffix(".png")
        screenshot_error = ""
        try:
            page.screenshot(
                path=str(screenshot_path),
                full_page=False,
                timeout=15_000,
                animations="disabled",
            )
        except Exception as exc:
            screenshot_error = f"{type(exc).__name__}: {_bounded(exc, 320)}"

        return {
            "artifact_schema": VERSION,
            "status": "passed",
            "frontend_url": origin,
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "run_id": run_id,
            "report_language_requested": "es-MX",
            "spanish_route_verified": True,
            "document_language_verified": True,
            "intake_report_language_verified": True,
            "start_request_count": recovery._start_count(requests),
            "duplicate_intake_absent": True,
            "initial_persistence": initial_stored,
            "terminal": terminal,
            "exact_run_identity_preserved": True,
            "started_at_epoch": started_at,
            "finished_at_epoch": time.time(),
            **artifacts,
            "screenshot": screenshot_path.as_posix() if screenshot_path.exists() else "",
            "screenshot_sha256": (
                hashlib.sha256(screenshot_path.read_bytes()).hexdigest()
                if screenshot_path.exists()
                else ""
            ),
            "screenshot_error": screenshot_error,
        }
    finally:
        context.close()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prove a fresh es-MX Comprehensive production run and final PDF."
    )
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=7_200.0)
    parser.add_argument("--navigation-timeout-ms", type=int, default=120_000)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                result = run_proof(browser, args)
            finally:
                browser.close()
    except Exception as exc:
        failure = {
            "artifact_schema": VERSION,
            "status": "failed",
            "frontend_url": args.frontend_url.rstrip("/"),
            "repository": args.repository,
            "expected_sha": args.expected_sha,
            "report_language_requested": "es-MX",
            "error": f"{type(exc).__name__}: {_bounded(exc, 1_500)}",
            "finished_at_epoch": time.time(),
        }
        _write(args.output, failure)
        raise

    _write(args.output, result)
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
