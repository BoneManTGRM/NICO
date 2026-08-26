#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from functools import wraps
from typing import Any

import spanish_comprehensive_live_acceptance_v1 as base
import spanish_comprehensive_live_acceptance_v2 as telemetry
from provider_neutral_repository_locator_contract_v1 import SPANISH_REPOSITORY_LABEL

VERSION = "nico.spanish_comprehensive_live_acceptance.v3.1"
SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"
SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"
SPANISH_TERMINAL_REPORT = "Completa"
SPANISH_MATURITY_LABELS = {"Excepcional", "Sólido", "Moderado", "Débil", "Crítico"}
FORBIDDEN_ENGLISH_MATURITY_LABELS = {"Exceptional", "Strong", "Moderate", "Weak", "Critical"}
_MARKER = "__nico_spanish_terminal_boundary_v3__"
_ARTIFACT_MARKER = "__nico_spanish_localized_artifact_proof_v31__"


def _verify_localized_spanish_terminal_artifacts(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
) -> dict[str, Any]:
    """Verify the customer-facing same-run localized PDF route.

    The production UI now hands review-PDF downloads to the localized same-run route.
    The older generic /report/pdf stream can remain available for compatibility, but it
    is not the browser's current artifact path and was the source of the post-merge
    Playwright read timeout. Verify the exact customer-facing route without weakening
    PDF signature, run identity, localization, or approval-state checks.
    """

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

    pdf = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/localized-report/es-MX/pdf",
        headers={"Accept": "application/pdf", "Cache-Control": "no-store"},
        timeout=120_000,
    )
    pdf_bytes = pdf.body()
    assert pdf.ok, f"Same-run localized Spanish PDF returned HTTP {pdf.status}"
    assert pdf_bytes.startswith(b"%PDF"), "Spanish report did not have a PDF signature"
    assert pdf.headers.get("x-nico-run-id") == run_id
    assert str(pdf.headers.get("x-nico-report-language") or "").lower() in {"es-mx", "es_mx"}
    assert str(pdf.headers.get("x-nico-assessment-rerun") or "false").lower() == "false"
    observed_sha = hashlib.sha256(pdf_bytes).hexdigest()
    header_sha = str(pdf.headers.get("x-nico-artifact-sha256") or "").lower()
    assert not header_sha or header_sha == observed_sha

    rendered = base._pdf_text(pdf_bytes)
    missing = [marker for marker in base.SPANISH_PDF_MARKERS if marker not in rendered]
    forbidden = [marker for marker in base.FORBIDDEN_PDF_MARKERS if marker in rendered]
    assert not missing, f"Spanish PDF omitted required presentation markers: {missing}"
    assert not forbidden, f"Spanish PDF retained forbidden English/failure markers: {forbidden}"

    return {
        "terminal_manifest_size_bytes": len(status_bytes),
        "terminal_manifest_bounded": True,
        "report_artifact_delivery": reports.get("artifact_delivery"),
        "artifact_route": "same_run_localized_es_mx_pdf",
        "pdf_size_bytes": len(pdf_bytes),
        "pdf_sha256": observed_sha,
        "pdf_signature_verified": True,
        "pdf_run_identity_verified": True,
        "spanish_pdf_presentation_verified": True,
        "spanish_pdf_markers_verified": list(base.SPANISH_PDF_MARKERS),
        "forbidden_pdf_markers_absent": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_spanish_terminal_boundary() -> None:
    """Bind current localized repository, terminal, and artifact semantics to proof."""

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


def main(argv: list[str] | None = None) -> int:
    install_spanish_terminal_boundary()
    return telemetry.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
