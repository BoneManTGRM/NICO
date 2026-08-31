#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import sys
import time
from functools import wraps
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pypdf import PdfReader

# Release automation invokes this file by path, which otherwise exposes only the
# scripts directory on sys.path. Add the repository root before importing NICO.
_REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
if str(_REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPOSITORY_ROOT))

from comprehensive_production_run_handoff_v1 import (
    require_canonical_json_digest,
    require_matching_canonical_truth_digest,
    source_binding_marker,
)
from nico.comprehensive_client_ready_projection_v1 import MAX_CLIENT_PDF_PAGES
from nico.spanish_client_evidence_summary_contract_v1 import (
    client_evidence_summary_has_five_fields,
)
import spanish_comprehensive_live_acceptance_v1 as base
import spanish_comprehensive_live_acceptance_v2 as telemetry
from provider_neutral_repository_locator_contract_v1 import SPANISH_REPOSITORY_LABEL

VERSION = "nico.spanish_comprehensive_live_acceptance.v3.2"
SPANISH_TERMINAL_PHASE = "Se requiere revisión experta"
SPANISH_TERMINAL_REVIEW = "Revisión interna requerida"
SPANISH_TERMINAL_REPORT = "Completa"
SPANISH_MATURITY_LABELS = {"Excepcional", "Sólido", "Moderado", "Débil", "Crítico"}
FORBIDDEN_ENGLISH_MATURITY_LABELS = {"Exceptional", "Strong", "Moderate", "Weak", "Critical"}
LOCALIZED_PDF_CONNECT_TIMEOUT_SECONDS = 300.0
LOCALIZED_PDF_READ_TIMEOUT_SECONDS = 300.0
CANONICAL_JSON_CONNECT_TIMEOUT_SECONDS = 300.0
CANONICAL_JSON_READ_TIMEOUT_SECONDS = 300.0
ENGAGEMENT_VISIBILITY_TIMEOUT_SECONDS = 180.0
ENGAGEMENT_VISIBILITY_RETRY_MILLISECONDS = 250

PROOF_CLIENT_NAME = "Cody Jenkins"
PROOF_PROJECT_NAME = "NICO Audit"
PROOF_PRIMARY_TECHNICAL_CONTACT = "Cody — Repository owner / project lead"
PROOF_ACCESS_METHOD = "Public GitHub repository via HTTPS/API — read-only access"
PROOF_AUTHORIZED_SCOPE = (
    "BoneManTGRM/NICO — entire repository, current main branch, including source "
    "code, configuration, CI/CD workflows, dependency manifests, documentation, "
    "and repository metadata. Read-only technical and security assessment."
)
SPANISH_ACCESS_METHOD_LABEL = "Método de acceso"
SPANISH_PRIMARY_CONTACT_LABEL = "Contacto técnico principal"
SPANISH_AUTHORIZED_SCOPE_LABEL = "Alcance autorizado"
EXCLUDED_ENGAGEMENT_FIELDS = (
    "primary_technical_contact",
    "access_method",
    "authorized_scope",
)
ENGAGEMENT_PROOF_FIXTURE_ENV = "NICO_SPANISH_PROOF_ENGAGEMENT_FIXTURE"

_MARKER = "__nico_spanish_terminal_boundary_v3__"
_ARTIFACT_MARKER = "__nico_spanish_localized_artifact_proof_v32__"
_RUN_MARKER = "__nico_spanish_commercial_proof_run_v32__"


def _exclusion_fixture() -> bool:
    fixture = str(os.getenv(ENGAGEMENT_PROOF_FIXTURE_ENV, "supplied") or "").strip()
    assert fixture in {"supplied", "excluded"}, {
        "unsupported_engagement_proof_fixture": fixture,
    }
    return fixture == "excluded"


def _recursive_values(value: Any, key: str) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        if key in value:
            direct = value.get(key)
            if isinstance(direct, list):
                found.extend(str(item) for item in direct if str(item))
            elif str(direct or ""):
                found.append(str(direct))
        for nested in value.values():
            found.extend(_recursive_values(nested, key))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_recursive_values(nested, key))
    return found


def _expected_engagement_metadata() -> dict[str, str]:
    expected = {
        "client_name": PROOF_CLIENT_NAME,
        "project_name": PROOF_PROJECT_NAME,
        "primary_technical_contact": PROOF_PRIMARY_TECHNICAL_CONTACT,
        "access_method": PROOF_ACCESS_METHOD,
        "authorized_scope": PROOF_AUTHORIZED_SCOPE,
    }
    if _exclusion_fixture():
        for field in EXCLUDED_ENGAGEMENT_FIELDS:
            expected[field] = ""
    return expected


def _expected_client_summary_values(report_language: str) -> tuple[str, ...]:
    expected = _expected_engagement_metadata()
    if not _exclusion_fixture():
        return tuple(expected.values())
    excluded_label = (
        "Excluido del alcance" if report_language == "es-MX" else "Excluded from scope"
    )
    return (
        expected["client_name"],
        expected["project_name"],
        excluded_label,
        excluded_label,
        excluded_label,
    )


def _recursive_field_state_records(value: Any, field: str) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    if isinstance(value, dict):
        direct = value.get(field)
        if isinstance(direct, dict) and (
            "state" in direct or "canonical_state" in direct
        ):
            found.append(direct)
        for nested in value.values():
            found.extend(_recursive_field_state_records(nested, field))
    elif isinstance(value, list):
        for nested in value:
            found.extend(_recursive_field_state_records(nested, field))
    return found


def _assert_excluded_field_states(value: Any, *, boundary: str) -> None:
    if not _exclusion_fixture():
        return
    for field in EXCLUDED_ENGAGEMENT_FIELDS:
        records = _recursive_field_state_records(value, field)
        assert records, {"boundary": boundary, "missing_field_state": field}
        assert any(
            str(record.get("state") or record.get("canonical_state") or "")
            == "excluded_from_scope"
            and record.get("value") in (None, "")
            and str(record.get("source") or "") == "user_action"
            for record in records
        ), {
            "boundary": boundary,
            "field": field,
            "expected_state": "excluded_from_scope",
            "observed_records": records[:20],
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
        actual = str(value.get(key) or "")
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


def _assert_pending_human_review_state(
    payload: dict[str, Any],
    *,
    boundary: str,
) -> dict[str, Any]:
    """Prove that automation stopped before any human approval or delivery act."""

    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    review_decision_absent = (
        "review_decision" not in payload and "review_decision" not in record
    )
    delivery_authorization_absent = (
        "delivery_authorization" not in payload
        and "delivery_authorization" not in record
    )
    approved_delivery_package_absent = (
        "approved_delivery_package" not in payload
        and "approved_delivery_package" not in record
    )
    observed = {
        "human_review_required": payload.get("human_review_required"),
        "human_review_completed": payload.get("human_review_completed"),
        "client_delivery_allowed": payload.get("client_delivery_allowed"),
        "approval_status": str(payload.get("approval_status") or ""),
        "delivery_status": str(payload.get("delivery_status") or ""),
        "accepted_edition_absent": (
            "accepted_edition" not in payload and "accepted_edition" not in record
        ),
        "review_decision_absent": review_decision_absent,
        "approved_final_absent": str(payload.get("approval_status") or "")
        != "approved_final",
        "delivery_authorization_absent": (
            payload.get("client_delivery_allowed") is False
            and str(payload.get("delivery_status") or "") == "blocked"
            and delivery_authorization_absent
        ),
        "approved_delivery_package_absent": approved_delivery_package_absent,
    }
    expected = {
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked",
        "accepted_edition_absent": True,
        "review_decision_absent": True,
        "approved_final_absent": True,
        "delivery_authorization_absent": True,
        "approved_delivery_package_absent": True,
    }
    assert observed == expected, {"boundary": boundary, "observed": observed}
    assert str(payload.get("status") or "") == "review_required", {
        "boundary": boundary,
        "status": payload.get("status"),
    }
    assert record.get("human_review_required") is True, {
        "boundary": boundary,
        "record_human_review_required": record.get("human_review_required"),
    }
    assert record.get("human_review_completed") is False, {
        "boundary": boundary,
        "record_human_review_completed": record.get("human_review_completed"),
    }
    assert record.get("client_delivery_allowed") is False, {
        "boundary": boundary,
        "record_client_delivery_allowed": record.get("client_delivery_allowed"),
    }
    assert str(record.get("delivery_status") or "") == "blocked", {
        "boundary": boundary,
        "record_delivery_status": record.get("delivery_status"),
    }
    assert "accepted_edition" not in record, {
        "boundary": boundary,
        "record_accepted_edition_present": True,
    }
    return expected


def _terminal_mutation_snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    record = payload.get("record") if isinstance(payload.get("record"), dict) else {}
    reports = payload.get("reports") if isinstance(payload.get("reports"), dict) else {}
    return {
        "run_id": payload.get("run_id"),
        "commit_sha": payload.get("commit_sha"),
        "status": payload.get("status"),
        "current_stage": payload.get("current_stage"),
        "terminal": payload.get("terminal"),
        "revision": payload.get("revision"),
        "integrity_sha256": payload.get("integrity_sha256"),
        "attempt": payload.get("attempt"),
        "run_attempt": payload.get("run_attempt"),
        "stage_attempts": payload.get("stage_attempts", record.get("stage_attempts")),
        "record_revision": record.get("revision"),
        "record_integrity_sha256": record.get("integrity_sha256"),
        "record_current_stage": record.get("current_stage"),
        "canonical_truth_sha256": reports.get("canonical_truth_sha256"),
        "human_review_required": payload.get("human_review_required"),
        "human_review_completed": payload.get("human_review_completed"),
        "client_delivery_allowed": payload.get("client_delivery_allowed"),
        "approval_status": payload.get("approval_status"),
        "delivery_status": payload.get("delivery_status"),
        "accepted_edition_present": "accepted_edition" in payload,
        "review_decision_present": "review_decision" in payload
        or "review_decision" in record,
        "delivery_authorization_present": "delivery_authorization" in payload
        or "delivery_authorization" in record,
        "approved_delivery_package_present": "approved_delivery_package" in payload
        or "approved_delivery_package" in record,
    }


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
    assert str(payload.get("client_name") or "") == PROOF_CLIENT_NAME
    assert str(payload.get("project_name") or "") == PROOF_PROJECT_NAME
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
    if _exclusion_fixture():
        for key in EXCLUDED_ENGAGEMENT_FIELDS:
            assert evidence.get(key) in (None, []), {
                "browser_intake_key": key,
                "expected": "excluded value omitted",
                "observed": evidence.get(key),
            }
        _assert_excluded_field_states(payload, boundary="browser_intake_request")
    else:
        for key, wanted in expected_arrays.items():
            assert evidence.get(key) == wanted, {
                "browser_intake_key": key,
                "expected": wanted,
                "observed": evidence.get(key),
            }
    expected = _expected_engagement_metadata()
    return {
        "actual_browser_intake_metadata_verified": True,
        "actual_browser_intake_shape_verified": True,
        "actual_browser_intake_exclusion_states_verified": _exclusion_fixture(),
        "actual_browser_intake_client_name": str(payload.get("client_name") or ""),
        "actual_browser_intake_project_name": str(payload.get("project_name") or ""),
        "actual_browser_intake_primary_technical_contact": expected[
            "primary_technical_contact"
        ],
        "actual_browser_intake_access_method": expected["access_method"],
        "actual_browser_intake_authorized_scope": expected["authorized_scope"],
        "actual_browser_intake_report_language": str(payload.get("report_language") or ""),
    }


def _fetch_and_verify_durable_engagement(
    page: Any,
    *,
    frontend_origin: str,
    run_id: str,
    boundary: str,
) -> dict[str, Any]:
    url = f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}"
    headers = {
        "Accept": "application/json",
        base.recovery.BROWSER_PROJECTION_HEADER: base.recovery.BROWSER_PROJECTION_VALUE,
        "Cache-Control": "no-store",
    }
    deadline = time.monotonic() + ENGAGEMENT_VISIBILITY_TIMEOUT_SECONDS
    attempts = 0
    not_found_reads = 0
    pending_reads = 0
    payload: Any = None
    last_status = 0
    while time.monotonic() < deadline:
        attempts += 1
        response = page.request.get(url, headers=headers, timeout=60_000)
        last_status = int(response.status)
        if response.ok:
            candidate = response.json()
            assert isinstance(candidate, dict)
            if candidate.get("intake_reserved") is not True:
                payload = candidate
                break
            if (
                candidate.get("operation") == "intake_pending"
                and candidate.get("terminal") is not True
            ):
                pending_reads += 1
            else:
                raise AssertionError(
                    f"Exact-run intake ended before engagement metadata became visible "
                    f"at {boundary}: {candidate.get('failure_code') or 'unknown_failure'}"
                )
        elif response.status == 404:
            not_found_reads += 1
        else:
            raise AssertionError(
                f"Exact-run engagement metadata read at {boundary} returned HTTP "
                f"{response.status}"
            )
        page.wait_for_timeout(ENGAGEMENT_VISIBILITY_RETRY_MILLISECONDS)
    assert isinstance(payload, dict), (
        f"Exact-run engagement metadata was not durably visible at {boundary} "
        f"within {ENGAGEMENT_VISIBILITY_TIMEOUT_SECONDS:.0f}s "
        f"(last HTTP {last_status}, attempts {attempts})"
    )
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
    _assert_excluded_field_states(payload, boundary=f"{boundary}:projected_status")
    assert top_level == record_value, {
        "boundary": boundary,
        "top_level_engagement_metadata": top_level,
        "record_engagement_metadata": record_value,
    }
    return {
        **top_level,
        "excluded_field_states_verified": _exclusion_fixture(),
        "visibility_read_attempt_count": attempts,
        "visibility_not_found_read_count": not_found_reads,
        "visibility_pending_read_count": pending_reads,
    }


def _fetch_localized_pdf(
    *,
    frontend_origin: str,
    run_id: str,
    report_language: str,
) -> dict[str, Any]:
    transport = httpx.HTTPTransport(verify=True, trust_env=False, retries=0)
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(
            connect=LOCALIZED_PDF_CONNECT_TIMEOUT_SECONDS,
            read=LOCALIZED_PDF_READ_TIMEOUT_SECONDS,
            write=30.0,
            pool=30.0,
        ),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(
            f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/localized-report/{report_language}/pdf",
            headers={
                "Accept": "application/pdf",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-store",
            },
        )
        pdf_bytes = response.content
    assert response.status_code == 200, (
        f"Same-run localized {report_language} PDF returned HTTP {response.status_code}"
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
    assert len(header_sha) == 64 and set(header_sha) <= set("0123456789abcdef"), {
        "report_language": report_language,
        "missing_or_invalid_artifact_sha256_header": header_sha,
    }
    assert header_sha == observed_sha, {
        "report_language": report_language,
        "artifact_sha256_header": header_sha,
        "computed_artifact_sha256": observed_sha,
    }
    canonical_truth_sha256 = str(
        response.headers.get("x-nico-canonical-truth-sha256") or ""
    ).lower()

    reader = PdfReader(io.BytesIO(pdf_bytes))
    page_count = len(reader.pages)
    assert 0 < page_count <= MAX_CLIENT_PDF_PAGES, {
        "report_language": report_language,
        "page_count": page_count,
        "renderer_page_boundary": MAX_CLIENT_PDF_PAGES,
    }
    rendered = base._pdf_text(pdf_bytes)
    rendered_compact = " ".join(rendered.split())
    for expected in _expected_engagement_metadata().values():
        if not expected:
            continue
        assert expected in rendered_compact, {
            "report_language": report_language,
            "missing_commercial_metadata": expected,
        }

    summary_values = _expected_client_summary_values(report_language)
    summary_verified = client_evidence_summary_has_five_fields(
        rendered_compact,
        report_language=report_language,
        expected_values=summary_values,
    )
    assert summary_verified, {
        "report_language": report_language,
        "client_evidence_summary_five_fields_consolidated": False,
    }

    if report_language == "es-MX":
        missing = [marker for marker in base.SPANISH_PDF_MARKERS if marker not in rendered]
        forbidden = [marker for marker in base.FORBIDDEN_PDF_MARKERS if marker in rendered]
        assert not missing, f"Spanish PDF omitted required presentation markers: {missing}"
        assert not forbidden, f"Spanish PDF retained forbidden English/failure markers: {forbidden}"

    locale_filename = "es-MX" if report_language == "es-MX" else "en"
    fixture_filename = "-excluded-context" if _exclusion_fixture() else ""
    artifact_path = Path("audit-results") / (
        f"nico-comprehensive-{locale_filename}{fixture_filename}-"
        "automated-draft-pending-human-approval.pdf"
    )
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(pdf_bytes)
    assert hashlib.sha256(artifact_path.read_bytes()).hexdigest() == observed_sha

    return {
        "language": report_language,
        "size_bytes": len(pdf_bytes),
        "sha256": observed_sha,
        "page_count": page_count,
        "renderer_page_boundary": MAX_CLIENT_PDF_PAGES,
        "signature_verified": True,
        "run_identity_verified": True,
        "commercial_metadata_verified": True,
        "all_five_engagement_literals_verified": not _exclusion_fixture(),
        "excluded_engagement_states_verified": _exclusion_fixture(),
        "client_evidence_summary_five_fields_consolidated": True,
        "assessment_rerun": False,
        "canonical_truth_sha256": canonical_truth_sha256,
        "artifact_path": artifact_path.as_posix(),
        "approval_boundary_in_filename": "pending-human-approval",
    }


def _fetch_canonical_json(
    *,
    frontend_origin: str,
    run_id: str,
) -> tuple[dict[str, Any], str, str]:
    """Read large immutable canonical truth outside Playwright's socket lifecycle."""

    transport = httpx.HTTPTransport(verify=True, trust_env=False, retries=0)
    with httpx.Client(
        transport=transport,
        timeout=httpx.Timeout(
            connect=CANONICAL_JSON_CONNECT_TIMEOUT_SECONDS,
            read=CANONICAL_JSON_READ_TIMEOUT_SECONDS,
            write=30.0,
            pool=30.0,
        ),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        response = client.get(
            f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}/report/json",
            headers={
                "Accept": "application/json",
                "Accept-Encoding": "identity",
                "Cache-Control": "no-store",
            },
        )
        canonical_bytes = response.content
    assert response.status_code == 200, (
        f"Exact-run canonical report JSON returned HTTP {response.status_code}"
    )
    canonical = json.loads(canonical_bytes.decode("utf-8"))
    assert isinstance(canonical, dict)
    canonical_digest_header = str(
        response.headers.get("x-nico-canonical-truth-sha256") or ""
    ).lower()
    computed_digest = require_canonical_json_digest(
        canonical,
        canonical_digest_header,
    )
    return canonical, canonical_digest_header, computed_digest


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
    pending_human_review = _assert_pending_human_review_state(
        payload,
        boundary="terminal_status_before_localized_reads",
    )
    assert reports.get("response_bounded") is True
    assert reports.get("artifact_delivery") == "on_demand_exact_run"
    assert reports.get("pdf_available") is True
    assert reports.get("markdown_available") is True
    manifest_canonical_truth_sha256 = str(
        reports.get("canonical_truth_sha256") or ""
    ).lower()
    terminal_state_before_localized_reads = _terminal_mutation_snapshot(payload)

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
    _assert_excluded_field_states(payload, boundary="terminal_status")

    (
        canonical,
        canonical_response_sha256,
        computed_canonical_truth_sha256,
    ) = _fetch_canonical_json(
        frontend_origin=frontend_origin,
        run_id=run_id,
    )
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), dict) else {}
    assert str(identity.get("run_id") or "") == run_id
    assert str(identity.get("customer_name") or identity.get("client_name") or "") == PROOF_CLIENT_NAME
    assert str(identity.get("project_name") or "") == PROOF_PROJECT_NAME

    if _exclusion_fixture():
        _assert_excluded_field_states(canonical, boundary="canonical_report_json")
    else:
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
        frontend_origin=frontend_origin,
        run_id=run_id,
        report_language="es-MX",
    )
    english_pdf = _fetch_localized_pdf(
        frontend_origin=frontend_origin,
        run_id=run_id,
        report_language="en",
    )
    (
        canonical_after_payload,
        _canonical_after_response_sha256,
        canonical_after_computed_sha256,
    ) = _fetch_canonical_json(
        frontend_origin=frontend_origin,
        run_id=run_id,
    )
    _assert_excluded_field_states(
        canonical_after_payload,
        boundary="canonical_report_json_after_localized_reads",
    )
    status_after = page.request.get(
        f"{frontend_origin}/api/nico/assessment/comprehensive-run/{run_id}",
        headers={
            "Accept": "application/json",
            base.recovery.BROWSER_PROJECTION_HEADER: base.recovery.BROWSER_PROJECTION_VALUE,
            "Cache-Control": "no-store",
        },
        timeout=60_000,
    )
    assert status_after.ok, (
        "Exact terminal status could not be refetched after localized report reads: "
        f"HTTP {status_after.status}"
    )
    status_after_payload = status_after.json()
    assert isinstance(status_after_payload, dict)
    _assert_excluded_field_states(
        status_after_payload,
        boundary="terminal_status_after_localized_reads",
    )
    pending_human_review_after = _assert_pending_human_review_state(
        status_after_payload,
        boundary="terminal_status_after_localized_reads",
    )
    assert pending_human_review_after == pending_human_review
    terminal_state_after_localized_reads = _terminal_mutation_snapshot(
        status_after_payload
    )
    assert terminal_state_after_localized_reads == terminal_state_before_localized_reads, {
        "terminal_state_before_localized_reads": terminal_state_before_localized_reads,
        "terminal_state_after_localized_reads": terminal_state_after_localized_reads,
    }
    canonical_truth_sha256 = require_matching_canonical_truth_digest(
        manifest_canonical_truth_sha256,
        canonical_response_sha256,
        computed_canonical_truth_sha256,
        spanish_pdf["canonical_truth_sha256"],
        english_pdf["canonical_truth_sha256"],
        canonical_after_computed_sha256,
        terminal_state_after_localized_reads["canonical_truth_sha256"],
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
        "primary_technical_contact_verified": not _exclusion_fixture(),
        "access_method_verified_in_canonical_truth": not _exclusion_fixture(),
        "authorized_scope_verified_in_canonical_truth": not _exclusion_fixture(),
        "excluded_engagement_fields_verified_in_canonical_truth": _exclusion_fixture(),
        "durable_engagement_metadata_verified_at_terminal": True,
        "spanish_pdf_page_count": spanish_pdf["page_count"],
        "english_pdf_page_count": english_pdf["page_count"],
        "spanish_pdf_path": spanish_pdf["artifact_path"],
        "spanish_pdf_sha256": spanish_pdf["sha256"],
        "english_pdf_path": english_pdf["artifact_path"],
        "english_pdf_sha256": english_pdf["sha256"],
        "localized_pdf_artifacts_pending_human_approval": True,
        "five_field_literals_verified_in_both_pdfs": all(
            item["all_five_engagement_literals_verified"]
            for item in (spanish_pdf, english_pdf)
        ),
        "excluded_engagement_states_verified_in_both_pdfs": all(
            item["excluded_engagement_states_verified"]
            for item in (spanish_pdf, english_pdf)
        ),
        "five_fields_consolidated_in_both_client_evidence_summaries": all(
            item["client_evidence_summary_five_fields_consolidated"]
            for item in (spanish_pdf, english_pdf)
        ),
        "same_run_bilingual_pdf_verified": True,
        "same_run_bilingual_assessment_rerun": False,
        "canonical_truth_sha256": canonical_truth_sha256,
        "canonical_truth_unchanged_after_localized_rendering": True,
        "canonical_truth_digest_computed_from_json": True,
        "localized_pdf_artifact_hash_headers_verified": True,
        "localized_report_get_count": 2,
        "localized_report_mutation_request_count": 0,
        "terminal_state_before_localized_reads": terminal_state_before_localized_reads,
        "terminal_state_after_localized_reads": terminal_state_after_localized_reads,
        "terminal_state_unchanged_after_localized_reads": True,
        "pdf_renderer_page_boundary": MAX_CLIENT_PDF_PAGES,
        **pending_human_review,
    }


def _commercial_spanish_run_proof(browser: Any, args: Any) -> dict[str, Any]:
    """Run the real compact-mobile intake with distinctive commercial metadata."""

    exclusion_fixture = _exclusion_fixture()
    context = browser.new_context(
        viewport=(
            {"width": 1440, "height": 1000}
            if exclusion_fixture
            else {"width": 390, "height": 844}
        ),
        locale="es-MX",
        service_workers="block",
        extra_http_headers={"Cache-Control": "no-store", "Pragma": "no-cache"},
    )
    page = context.new_page()
    requests: list[dict[str, str]] = []
    run_id = ""
    proof_completed = False
    origin = args.frontend_url.rstrip("/")
    source_marker = source_binding_marker(
        args.source_workflow_run_id,
        args.source_workflow_run_attempt,
    )
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
        if exclusion_fixture:
            stakeholder_module = page.get_by_role(
                "button",
                name=re.compile(
                    r"Contexto de interesados, encargo y autorizaci[oó]n",
                    re.IGNORECASE,
                ),
            ).first
            stakeholder_module.click()
            page.get_by_role(
                "button",
                name="Excluir del alcance",
                exact=True,
            ).click()
            for field in EXCLUDED_ENGAGEMENT_FIELDS:
                container = page.locator(
                    f'[data-engagement-field="{field}"]'
                ).first
                assert container.get_attribute("data-engagement-state") == (
                    "excluded_from_scope"
                )
                assert container.locator("textarea").first.input_value() == ""
        else:
            page.get_by_label(SPANISH_ACCESS_METHOD_LABEL).fill(PROOF_ACCESS_METHOD)
            page.get_by_label(SPANISH_PRIMARY_CONTACT_LABEL).fill(
                PROOF_PRIMARY_TECHNICAL_CONTACT
            )
            page.get_by_label(SPANISH_AUTHORIZED_SCOPE_LABEL).fill(
                PROOF_AUTHORIZED_SCOPE
            )
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

        running_reload = base.recovery._reload_and_restore(
            page,
            run_id,
            args.navigation_timeout_ms,
            expect_active_storage=True,
        )
        assert base.recovery._start_count(requests) == 1
        running_visibility = base.recovery._prove_visibility_hidden_visible(
            page,
            context,
            timeout_ms=args.navigation_timeout_ms,
        )
        running_after_foreground = base.recovery._wait_for_same_run_ui(
            page,
            run_id,
            120.0,
        )
        assert base.recovery._start_count(requests) == 1

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
            "source_workflow_run_id": str(args.source_workflow_run_id),
            "source_workflow_run_attempt": str(args.source_workflow_run_attempt),
            "source_binding": source_marker.removeprefix("source:"),
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
            "running_reload": running_reload,
            "running_after_foreground": running_after_foreground,
            "running_visibility": running_visibility,
            "running_visibility_transitions": ["hidden", "visible"],
            "running_reload_recovery_verified": True,
            "running_background_foreground_recovery_verified": True,
            "durable_engagement_metadata_verified_at_intake": True,
            "durable_engagement_metadata_at_intake": initial_engagement,
            "terminal": terminal,
            "exact_run_identity_preserved": True,
            "engagement_fixture": (
                "excluded" if exclusion_fixture else "supplied"
            ),
            "module_exclusion_verified": exclusion_fixture,
            "excluded_engagement_fields": (
                list(EXCLUDED_ENGAGEMENT_FIELDS) if exclusion_fixture else []
            ),
            "commercial_proof_client_name": PROOF_CLIENT_NAME,
            "commercial_proof_project_name": PROOF_PROJECT_NAME,
            "commercial_proof_primary_technical_contact": (
                _expected_engagement_metadata()["primary_technical_contact"]
            ),
            "commercial_proof_access_method": (
                _expected_engagement_metadata()["access_method"]
            ),
            "commercial_proof_authorized_scope": (
                _expected_engagement_metadata()["authorized_scope"]
            ),
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
