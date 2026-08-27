#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import time
from functools import wraps
from typing import Any
from urllib.parse import urlparse

from pypdf import PdfReader

import spanish_comprehensive_live_acceptance_v1 as base
import spanish_comprehensive_live_acceptance_v2 as telemetry
from provider_neutral_repository_locator_contract_v1 import SPANISH_REPOSITORY_LABEL

VERSION = "nico.spanish_comprehensive_live_acceptance.v3.2"
SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"
SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"
SPANISH_TERMINAL_REPORT = "Completa"
SPANISH_MATURITY_LABELS = {"Excepcional", "Sólido", "Moderado", "Débil", "Crítico"}
FORBIDDEN_ENGLISH_MATURITY_LABELS = {"Exceptional", "Strong", "Moderate", "Weak", "Critical"}

PROOF_CLIENT_NAME = "NICO Acceptance Client"
PROOF_PROJECT_NAME = "NICO Acceptance Project"
PROOF_ACCESS_METHOD = "GitHub HTTPS/API - read-only"
PROOF_PRIMARY_TECHNICAL_CONTACT = "NICO Acceptance Contact"
PROOF_AUTHORIZED_SCOPE = "Full repository at exact assessed SHA - read-only"
SPANISH_ACCESS_METHOD_LABEL = "Método de acceso"
SPANISH_PRIMARY_CONTACT_LABEL = "Contacto técnico principal"
SPANISH_AUTHORIZED_SCOPE_LABEL = "Alcance autorizado"

_MARKER = "__nico_spanish_terminal_boundary_v3__"
_ARTIFACT_MARKER = "__nico_spanish_localized_artifact_proof_v32__"
_RUN_MARKER = "__nico_spanish_commercial_proof_run_v32__"


def _recursive_values(value: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if key in value:
            direct = value.get(key)
            if isinstance(direct, list):
                found.extend(str(item).strip() for item in direct if str(item).strip())
            elif str(direct or "").strip():
                found.append(str(direct).strip())
        for nested in value.values():
            found.extend(_recursive_values(nested, key))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_recursive_values(nested, key))
    return found


def _expected_engagement_metadata() -> dict[str, str]:
    return {
        "client_name": PROOF_CLIENT_NAME,
        "project_name": PROOF_PROJECT_NAME,
        "primary_technical_contact": PROOF_PRIMARY_TECHNICAL_CONTACT,
        "access_method": PROOF_ACCESS_METHOD,
        "authorized_scope": PROOF_AUTHORIZED_SCOPE,
    }


def _assert_engagement_metadata(value: Any, *, boundary: str) -> dict[str, str]:
    assert isinstance(value, dict), {
        "boundary": boundary,
        "missing_engagement_metadata": True,
        "observed_type": type(value).__name__,
    }
    expected = _expected_engagement_metadata()
    observed: dict[str, str] = {}
    for key, wanted in expected.items():
        actual = str(value.get(key) or "").strip()
        observed[key] = actual
        assert actual == wanted, {
            "boundary": boundary,
            "engagement_metadata_key": key,
            "expected": wanted,
            "observed": actual,
        }
    assert value.get("repository_inference_prohibited") is True, {
        "boundary": boundary,
        "repository_inference_prohibited": value.get("repository_inference_prohibited"),
    }
    assert value.get("directly_scored") is False, {
        "boundary": boundary,
        "directly_scored": value.get("directly_scored"),
    }
    return observed


def _verify_actual_browser_intake(requests: list[dict[str, str]]) -> dict[str, Any]:
    matches = [
        item
        for item in requests
        if item.get("method") == "POST"
        and item.get("path") == "/api/nico/assessment/comprehensive-intake"
    ]
    assert len(matches) == 1, {
        "expected_intake_requests": 1,
        "observed_intake_requests": len(matches),
    }
    raw = str(matches[0].get("body") or "")
    assert raw, "Production browser intake POST had no captured request body"
    try:
        payload = json.loads(raw)
    except Exception as exc:
        raise AssertionError("Production browser intake POST body was not valid JSON") from exc
    assert isinstance(payload, dict)
    assert str(payload.get("client_name") or "").strip() == PROOF_CLIENT_NAME
    assert str(payload.get("project_name") or "").strip() == PROOF_PROJECT_NAME
    assert str(payload.get("report_language") or "") == "es-MX"

    human = payload.get("human_evidence")
    assert isinstance(human, dict), {"human_evidence_type": type(human).__name__}
    stakeholder = human.get("stakeholder_context")
    assert isinstance(stakeholder, dict), {
        "stakeholder_context_type": type(stakeholder).__name__
    }
    evidence = stakeholder.get("evidence")
    assert isinstance(evidence, dict), {"evidence_type": type(evidence).__name__}
    expected_arrays = {
        "access_method": [PROOF_ACCESS_METHOD],
        "primary_technical_contact": [PROOF_PRIMARY_TECHNICAL_CONTACT],
        "authorized_scope": [PROOF_AUTHORIZED_SCOPE],
    }
    for key, wanted in expected_arrays.items():
        assert evidence.get(key) == wanted, {
            "browser_intake_key": key,
            "expected": wanted,
            "observed": evidence.get(key),
        }
    return {
        "actual_browser_intake_metadata_verified": True,
        "actual_browser_intake_shape_verified": True,
        "actual_browser_intake_client_name": str(payload.get("client_name") or ""),
        "actual_browser_intake_project_name": str(payload.get("project_name") or ""),
        "actual_browser_intake_report_language": str(payload.get("report_language") or ""),
    }


def _fetch_and_verify_durable_engagement(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
    boundary: str,
) -> dict[str, str]:
    response = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            base.recovery.BROWSER_PROJECTION_HEADER: base.recovery.BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=60_000,
    )
    assert response.ok, (
        f"Exact-run engagement metadata read at {boundary} returned HTTP {response.status}"
    )
    payload = response.json()
    assert isinstance(payload, dict)
    assert str(payload.get("run_id") or "") == run_id
    top_level = _assert_engagement_metadata(
        payload.get("engagement_metadata"),
        boundary=f"{boundary}:top_level",
    )
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    record_value = _assert_engagement_metadata(
        record.get("engagement_metadata"),
        boundary=f"{boundary}:record",
    )
    assert top_level == record_value, {
        "boundary": boundary,
        "top_level_engagement_metadata": top_level,
        "record_engagement_metadata": record_value,
    }
    return top_level


def _fetch_localized_pdf(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
    report_language: str,
) -> dict[str, Any]:
    response = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/localized-report/{report_language}/pdf",
        headers={"Accept": "application/pdf", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    pdf_bytes = response.body()
    assert response.ok, (
        f"Same-run localized {report_language} PDF returned HTTP {response.status}"
    )
    assert pdf_bytes.startswith(b"%PDF"), f"{report_language} report was not a PDF"
    assert response.headers.get("x-nico-run-id") == run_id
    observed_language = str(response.headers.get("x-nico-report-language") or "").lower()
    expected_languages = {"es-mx", "es_mx"} if report_language == "es-MX" else {"en"}
    assert observed_language in expected_languages, {
        "expected_report_language": report_language,
        "observed_report_language": observed_language,
    }
    assert str(response.headers.get("x-nico-assessment-rerun") or "false").lower() == "false"
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    header_sha = str(response.headers.get("x-nico-artifact-sha256") or "").lower()
    assert not header_sha or header_sha == observed_sha

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    assert 0 < page_count < 44, {
        "report_language": report_language,
        "page_count": page_count,
        "regression": "production Comprehensive PDF remained 44 pages",
    }
    rendered = base._pdf_text(pdf_bytes)
    for expected in (
        PROOF_CLIENT_NAME,
        PROOF_PROJECT_NAME,
        PROOF_PRIMARY_TECHNICAL_CONTACT,
    ):
        assert expected in rendered, {
            "report_language": report_language,
            "missing_commercial_metadata": expected,
        }

    if report_language == "es-MX":
        missing = [marker for marker in base.SPANISH_PDF_MARKERS if marker not in rendered]
        forbidden = [marker for marker in base.FORBIDDEN_PDF_MARKERS if marker in rendered]
        assert not missing, f"Spanish PDF omitted required presentation markers: {missing}"
        assert not forbidden, f"Spanish PDF retained forbidden English/failure markers: {forbidden}"

    return {
        "language": report_language,
        "size_bytes": len(pdf_bytes),
        "sha256": observed_sha,
        "page_count": page_count,
        "signature_verified": True,
        "run_identity_verified": True,
        "commercial_metadata_verified": True,
        "assessment_rerun": False,
    }


def _verify_localized_spanish_terminal_artifacts(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
) -> dict[str, Any]:
    """Verify one exact run across canonical truth and both client PDF locales."""

    status = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            base.recovery.BROWSER_PROJECTION_HEADER: base.recovery.BROWSER_PROJECTION_VALUE,
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

    terminal_top = _assert_engagement_metadata(
        payload.get("engagement_metadata"),
        boundary="terminal_status:top_level",
    )
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    terminal_record = _assert_engagement_metadata(
        record.get("engagement_metadata"),
        boundary="terminal_status:record",
    )
    assert terminal_top == terminal_record

    canonical_response = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/report/json",
        headers={"Accept": "application/json", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    assert canonical_response.ok, (
        f"Exact-run canonical report JSON returned HTTP {canonical_response.status}"
    )
    canonical = canonical_response.json()
    assert isinstance(canonical, dict)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    assert str(identity.get("run_id") or "") == run_id
    assert str(identity.get("customer_name") or identity.get("client_name") or "") == PROOF_CLIENT_NAME
    assert str(identity.get("project_name") or "") == PROOF_PROJECT_NAME

    for key, expected in (
        ("access_method", PROOF_ACCESS_METHOD),
        ("primary_technical_contact", PROOF_PRIMARY_TECHNICAL_CONTACT),
        ("authorized_scope", PROOF_AUTHORIZED_SCOPE),
    ):
        values = _recursive_values(canonical, key)
        assert expected in values, {
            "missing_human_context_key": key,
            "expected": expected,
            "observed": values[:20],
        }

    spanish_pdf = _fetch_localized_pdf(
        page,
        frontend_origin=frontend_origin,
        run_id=run_id,
        report_language="es-MX",
    )
    english_pdf = _fetch_localized_pdf(
        page,
        frontend_origin=frontend_origin,
        run_id=run_id,
        report_language="en",
    )

    return {
        "terminal_manifest_size_bytes": len(status_bytes),
        "terminal_manifest_bounded": True,
        "report_artifact_delivery": reports.get("artifact_delivery"),
        "artifact_route": "same_run_bilingual_localized_pdf",
        "pdf_size_bytes": spanish_pdf["size_bytes"],
        "pdf_sha256": spanish_pdf["sha256"],
        "pdf_signature_verified": True,
        "pdf_run_identity_verified": True,
        "spanish_pdf_presentation_verified": True,
        "spanish_pdf_markers_verified": list(base.SPANISH_PDF_MARKERS),
        "forbidden_pdf_markers_absent": True,
        "commercial_display_metadata_verified": True,
        "client_name_verified": True,
        "project_name_verified": True,
        "primary_technical_contact_verified": True,
        "access_method_verified_in_canonical_truth": True,
        "authorized_scope_verified_in_canonical_truth": True,
        "durable_engagement_metadata_verified_at_terminal": True,
        "spanish_pdf_page_count": spanish_pdf["page_count"],
        "english_pdf_page_count": english_pdf["page_count"],
        "same_run_bilingual_pdf_verified": True,
        "same_run_bilingual_assessment_rerun": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _commercial_spanish_run_proof(browser: Any, args: Any) -> dict[str, Any]:
    """Run the real compact-mobile intake with distinctive commercial metadata."""

    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        locale="es-MX",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    requests: list[dict[str, str]] = []
    run_id = ""
    proof_completed = False
    origin = args.frontend_url.rstrip("/")
    base._install_reserved_proof_scope(page)

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
    try:
        page.goto(
            f"{origin}{base.SPANISH_ROUTE}?tier=comprehensive&spanish_production_probe={time.time_ns()}#assessment",
            wait_until="domcontentloaded",
            timeout=args.navigation_timeout_ms,
        )
        base._wait_for_spanish_hydration(page, args.navigation_timeout_ms)
        assert page.evaluate("() => document.documentElement.lang") == "es-MX"

        page.get_by_label(base.SPANISH_REPO_LABEL).fill(args.repository)
        page.get_by_label(base.SPANISH_CLIENT_LABEL).fill(PROOF_CLIENT_NAME)
        page.get_by_label(base.SPANISH_PROJECT_LABEL).fill(PROOF_PROJECT_NAME)
        page.get_by_label(SPANISH_ACCESS_METHOD_LABEL).fill(PROOF_ACCESS_METHOD)
        page.get_by_label(SPANISH_PRIMARY_CONTACT_LABEL).fill(PROOF_PRIMARY_TECHNICAL_CONTACT)
        page.get_by_label(SPANISH_AUTHORIZED_SCOPE_LABEL).fill(PROOF_AUTHORIZED_SCOPE)
        page.locator(base.recovery.AUTHORIZATION_SELECTOR).check()
        page.locator(base.recovery.ACTION_SELECTOR).click()

        run_id, initial_stored = base.recovery._wait_for_run_id(page, 180.0)
        args.proof_run_id = run_id
        assert base.recovery._start_count(requests) == 1
        languages = base._intake_languages(requests)
        assert languages == ["es-MX"], (
            f"Spanish intake did not persist report_language=es-MX: {languages}"
        )
        browser_intake = _verify_actual_browser_intake(requests)
        initial_engagement = _fetch_and_verify_durable_engagement(
            page,
            frontend_origin=origin,
            run_id=run_id,
            boundary="immediately_after_intake",
        )
        proof_scope = base._verify_proof_scope(page, origin, run_id)

        base.recovery._wait_for_terminal(page, run_id, args.timeout_seconds)
        terminal = base.recovery._wait_for_terminal_ui_ready(
            page,
            run_id,
            args.expected_sha,
            240.0,
        )
        assert terminal.get("phase") == SPANISH_TERMINAL_PHASE, terminal
        assert terminal.get("report_actions_present") == "true", terminal
        assert terminal.get("pdf_enabled") == "true", terminal
        assert terminal.get("markdown_enabled") == "true", terminal

        artifacts = base._verify_spanish_terminal_artifacts(
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
            screenshot_error = f"{type(exc).__name__}: {base._bounded(exc, 320)}"

        proof_completed = True
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
            **proof_scope,
            **browser_intake,
            "start_request_count": base.recovery._start_count(requests),
            "duplicate_intake_absent": True,
            "initial_persistence": initial_stored,
            "durable_engagement_metadata_verified_at_intake": True,
            "durable_engagement_metadata_at_intake": initial_engagement,
            "terminal": terminal,
            "exact_run_identity_preserved": True,
            "commercial_proof_client_name": PROOF_CLIENT_NAME,
            "commercial_proof_project_name": PROOF_PROJECT_NAME,
            "commercial_proof_primary_technical_contact": PROOF_PRIMARY_TECHNICAL_CONTACT,
            "commercial_proof_access_method": PROOF_ACCESS_METHOD,
            "commercial_proof_authorized_scope": PROOF_AUTHORIZED_SCOPE,
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
        if run_id and not proof_completed:
            args.proof_cleanup = base._cancel_proof_run(page, origin, run_id)
        context.close()


def install_spanish_terminal_boundary() -> None:
    """Bind current localized repository, terminal, artifact, and commercial semantics."""

    base.SPANISH_REPO_LABEL = SPANISH_REPOSITORY_LABEL
    base.SPANISH_TERMINAL_PHASE = SPANISH_TERMINAL_PHASE
    current = base.recovery._wait_for_terminal_ui_ready
    if not getattr(current, _MARKER, False):

        @wraps(current)
        def wait_for_terminal_ui_ready(*args: Any, **kwargs: Any) -> dict[str, Any]:
            terminal = current(*args, **kwargs)
            assert terminal.get("phase") == SPANISH_TERMINAL_PHASE, terminal
            assert terminal.get("review") == SPANISH_TERMINAL_REVIEW, terminal
            assert terminal.get("report") == SPANISH_TERMINAL_REPORT, terminal
            score = str(terminal.get("score") or "").strip()
            maturity = score.split("·", 1)[0].strip()
            assert maturity in SPANISH_MATURITY_LABELS, terminal
            assert not any(label in score for label in FORBIDDEN_ENGLISH_MATURITY_LABELS), terminal
            return terminal

        setattr(wait_for_terminal_ui_ready, _MARKER, True)
        setattr(wait_for_terminal_ui_ready, "_nico_previous", current)
        base.recovery._wait_for_terminal_ui_ready = wait_for_terminal_ui_ready
        telemetry.recovery._wait_for_terminal_ui_ready = wait_for_terminal_ui_ready

    current_artifact = base._verify_spanish_terminal_artifacts
    if not getattr(current_artifact, _ARTIFACT_MARKER, False):
        setattr(_verify_localized_spanish_terminal_artifacts, _ARTIFACT_MARKER, True)
        setattr(_verify_localized_spanish_terminal_artifacts, "_nico_previous", current_artifact)
        base._verify_spanish_terminal_artifacts = _verify_localized_spanish_terminal_artifacts

    current_run = base.run_proof
    if not getattr(current_run, _RUN_MARKER, False):
        setattr(_commercial_spanish_run_proof, _RUN_MARKER, True)
        setattr(_commercial_spanish_run_proof, "_nico_previous", current_run)
        base.run_proof = _commercial_spanish_run_proof


def main(argv: list[str] | None = None) -> int:
    install_spanish_terminal_boundary()
    return telemetry.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
