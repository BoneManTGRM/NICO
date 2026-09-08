"""Freeze verified, source/run-selected metadata while building new report truth.

This code does not execute scanners, mutate run history or grant coverage, review,
approval or delivery credit. It never accepts a caller-selected URL or blob path.
"""
from __future__ import annotations

import base64
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import time
from typing import Any, Mapping

VERSION = "nico.report-execution-provenance.v1"
FRONTEND_URL = "https://app.nicoaudit.com/api/release"
_MAX_FRONTEND_BYTES = 16_384


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def capture_frontend_release(expected_sha: str, expected_deployment_id: str) -> dict[str, Any]:
    """Observe the fixed production frontend, then match owner-verified labels.

    Configured labels alone never establish an observed deployment. The integrating
    operator must separately match these nonsecret labels to native provider records.
    No redirects, caller URLs, request credentials or environment proxies are used.
    """
    import requests

    result: dict[str, Any] = {"status": "unavailable", "source_url": FRONTEND_URL,
        "deployment_identity_verified": False, "native_provider_record_verified_by_this_code": False}
    if not expected_deployment_id or expected_deployment_id == "unavailable" or expected_sha == "unavailable":
        return {**result, "reason": "expected_frontend_deployment_unavailable"}
    try:
        with requests.Session() as session:
            session.trust_env = False
            with session.get(FRONTEND_URL, timeout=(3, 5), allow_redirects=False, stream=True,
                    headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    return {**result, "reason": "frontend_release_response_unavailable"}
                raw = bytearray()
                deadline = time.monotonic() + 8
                for chunk in response.iter_content(chunk_size=1):
                    if time.monotonic() > deadline:
                        return {**result, "reason": "frontend_release_response_timed_out"}
                    raw.extend(chunk)
                    if len(raw) > _MAX_FRONTEND_BYTES:
                        return {**result, "reason": "frontend_release_response_limit_exceeded"}
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError("frontend_release_response_invalid")
        matched = (value.get("status") == "ok" and value.get("release_sha") == expected_sha
            and value.get("deployment_id") == expected_deployment_id
            and value.get("deployment_id_source") == "VERCEL_DEPLOYMENT_ID")
        # The endpoint has a deliberately small, nonsecret contract. Retain exact
        # observation bytes only for that contract, not an unexpected HTML/error body.
        allowed = {"status", "release_sha", "deployment_id", "deployment_id_source",
            "ui_contract", "git_ref", "deployment_environment"}
        if set(value) - allowed:
            return {**result, "reason": "frontend_release_response_contract_invalid"}
        return {**result, "status": "verified" if matched else "mismatch",
            "deployment_identity_verified": matched,
            "observed_at": datetime.now(UTC).isoformat(),
            "release_sha": value.get("release_sha"), "deployment_id": value.get("deployment_id"),
            "deployment_id_source": value.get("deployment_id_source"),
            "observation_bytes_base64": base64.b64encode(raw).decode("ascii"),
            "observation_sha256": hashlib.sha256(raw).hexdigest(), "observation_size_bytes": len(raw)}
    except (requests.RequestException, ValueError, TypeError):
        return {**result, "reason": "frontend_release_observation_unavailable"}


def verify_frontend_release(value: Any, expected_sha: str, expected_deployment_id: str) -> bool:
    """Validate a retained observation without replacing it with current runtime data."""
    value = _mapping(value)
    try:
        raw = base64.b64decode(value.get("observation_bytes_base64", ""), validate=True)
        if not 0 < len(raw) <= _MAX_FRONTEND_BYTES:
            return False
        observed = json.loads(raw)
        return (value.get("status") == "verified" and value.get("deployment_identity_verified") is True
            and value.get("source_url") == FRONTEND_URL
            and value.get("observation_sha256") == hashlib.sha256(raw).hexdigest()
            and value.get("observation_size_bytes") == len(raw)
            and observed.get("status") == "ok"
            and bool(expected_deployment_id) and expected_deployment_id != "unavailable"
            and value.get("release_sha") == observed.get("release_sha") == expected_sha
            and value.get("deployment_id") == observed.get("deployment_id") == expected_deployment_id
            and value.get("deployment_id_source") == observed.get("deployment_id_source") == "VERCEL_DEPLOYMENT_ID")
    except (ValueError, TypeError, AttributeError):
        return False


def scanner_execution_evidence(identity: Mapping[str, Any], stages: Mapping[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_scanner_inventory_v1 import inventory_for_record

    # Called only by the trusted report builder on the stored run context. The
    # existing inventory authority independently verifies the scan identity and bytes.
    record = {"identity": dict(identity), "stage_results": dict(stages)}
    inspected = inventory_for_record(record, run_id=str(identity.get("run_id") or ""))
    inventory = json.loads(inspected.body)
    result: dict[str, Any] = {"artifact_schema": VERSION,
        "run_id": identity.get("run_id"), "repository": identity.get("repository"),
        "commit_sha": identity.get("commit_sha"), "evidence_ledger_id": identity.get("evidence_ledger_id"),
        "verification_status": "unverified", "scanner_records": [],
        "coverage_status": "not_evaluated_by_inventory", "assessment_mutated": False,
        "approval_or_delivery_action_performed": False}
    if inspected.status_code != 200:
        return {**result, "reason": _mapping(inventory.get("detail")).get("code") or "scanner_evidence_unavailable"}
    result.update(scan_id=inventory.get("scan_id"), inventory_status=inventory.get("status"),
        scanner_record_count=inventory.get("scanner_record_count"),
        unknown_scanner_record_count=inventory.get("unknown_scanner_record_count"),
        duplicate_scanner_record_count=inventory.get("duplicate_scanner_record_count"),
        unknown_requested_scanner_count=inventory.get("unknown_requested_scanner_count"))
    population_valid = not any(inventory.get(key) for key in
        ("unknown_scanner_record_count", "duplicate_scanner_record_count", "unknown_requested_scanner_count"))
    for original in inventory.get("scanner_records") or []:
        row = deepcopy(original)
        receipt = _mapping(_mapping(row.get("execution_provenance")).get("execution_receipt"))
        retained_provenance = _mapping(row.get("execution_provenance"))
        invocations = retained_provenance.get("invocation_receipts") or []
        invocation_count = retained_provenance.get("invocation_receipt_count")
        invocations_verified = (
            invocation_count is None and not invocations
        ) or (
            type(invocation_count) is int and invocation_count == len(invocations)
            and all(_mapping(item).get("status") == "retained_receipt_integrity_verified" for item in invocations)
        )
        row["declared_invocation_status"] = (
            "not_declared" if invocation_count is None and not invocations
            else "verified" if invocations_verified else "unverified"
        )
        bytes_verified = (population_valid and row.get("source_identity_verified") is True
            and row.get("source_checkout_verified") is True
            and _mapping(row.get("raw_artifact")).get("availability") == "verified")
        # A failed/timed-out invocation can have valid provenance. Its status is
        # preserved, and provenance is never a completed or clean-scan assertion.
        row["execution_evidence_verified"] = bool(bytes_verified
            and invocations_verified
            and row.get("execution_observed") is True
            and receipt.get("status") == "retained_receipt_integrity_verified")
        row["inapplicability_evidence_verified"] = bool(bytes_verified
            and row.get("execution_status") == "not_applicable" and row.get("applicable") is False
            and row.get("applicability_observation_verified") is True)
        result["scanner_records"].append(row)
    rows = result["scanner_records"]
    if rows and all(row["declared_invocation_status"] != "unverified"
            and (row["execution_evidence_verified"] or row["inapplicability_evidence_verified"]) for row in rows):
        result["verification_status"] = "verified"
    return result


def bind_report_execution_provenance(canonical: Mapping[str, Any], *, raw_stages: Mapping[str, Any]) -> dict[str, Any]:
    from nico.comprehensive_release_provenance_v1 import comprehensive_release_provenance

    result = deepcopy(dict(canonical))
    assessment = dict(_mapping(result.get("assessment")))
    provenance = deepcopy(_mapping(assessment.get("nico_release_provenance"))) or comprehensive_release_provenance()
    identity = _mapping(result.get("identity"))
    provenance["report_execution_provenance_schema"] = VERSION
    provenance["assessed_repository_commit"] = identity.get("commit_sha")
    provenance["assessment_run_id"] = identity.get("run_id")
    provenance["release_identity_scope"] = "report_generation_runtime; assessed repository identity is separate"
    provenance["scanner_execution_evidence"] = scanner_execution_evidence(identity, raw_stages)
    provenance["frontend_runtime_observation"] = capture_frontend_release(
        str(provenance.get("frontend_build_commit") or "unavailable"),
        str(provenance.get("frontend_deployment_id") or ""))
    provenance["frontend_deployment_identity_verified"] = verify_frontend_release(
        provenance["frontend_runtime_observation"], str(provenance.get("frontend_build_commit")),
        str(provenance.get("frontend_deployment_id")))
    assessment["nico_release_provenance"] = provenance
    result["assessment"] = assessment
    return result
