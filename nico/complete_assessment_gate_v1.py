"""Reject incomplete scanner evidence independently of successful PDF rendering."""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REQUIRED_TOOLS = ("pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog")
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COMPLETE = {"completed", "complete", "completed_clean", "completed_with_findings"}


def complete_assessment_evidence(canonical: Mapping[str, Any], *, expected_commit: str, expected_run: str) -> dict[str, Any]:
    """Validate canonical requested records; N/A never receives scan credit.

    This evaluates execution coverage only, not the absence of vulnerabilities,
    specialist approval, provider-private access, or client-delivery permission.
    """
    failures: list[str] = []
    identity = canonical.get("identity") or {}
    if not _SHA.fullmatch(expected_commit) or not expected_run:
        failures.append("expected_identity_missing")
    if not isinstance(identity, Mapping) or identity.get("commit_sha") != expected_commit or identity.get("run_id") != expected_run:
        failures.append("canonical_identity_mismatch")
    assessment = canonical.get("assessment") or {}
    if not isinstance(assessment, Mapping):
        assessment = {}
    records = canonical.get("requested_scanner_records")
    if not isinstance(records, list):
        records = assessment.get("requested_scanner_records")
    if not isinstance(records, list):
        records = canonical.get("scanner_execution_records")
    if not isinstance(records, list) or not records:
        failures.append("requested_scanner_records_missing")
        records = []
    completed: list[str] = []
    not_applicable: list[str] = []
    seen: set[str] = set()
    for record in records:
        if not isinstance(record, Mapping):
            failures.append("malformed_scanner_record")
            continue
        name = str(record.get("scanner_name") or record.get("tool") or record.get("scanner") or "")
        if name in seen:
            failures.append(name + ":duplicate_scanner_record")
            continue
        seen.add(name)
        if name not in REQUIRED_TOOLS:
            failures.append(name + ":unexpected_scanner")
        state = str(record.get("state") or record.get("status") or "").casefold().replace("-", "_")
        source = record.get("commit_sha") or record.get("target_commit_sha") or record.get("snapshot_commit_sha")
        if source != expected_commit or record.get("exact_commit_match") is not True:
            failures.append(name + ":source_identity_unverified")
        if record.get("run_id") and record.get("run_id") != expected_run:
            failures.append(name + ":run_identity_mismatch")
        if state == "not_applicable":
            reason = record.get("applicability_reason")
            if record.get("applicable") is not False or not isinstance(reason, str) or not reason.strip():
                failures.append(name + ":applicability_unjustified")
            if any(record.get(k) is True for k in ("completed", "verified", "verified_complete", "verified_for_this_report")):
                failures.append(name + ":not_applicable_claimed_as_completed")
            if name == "osv-scanner":
                inventory = record.get("applicability_evidence") or {}
                if not isinstance(inventory, Mapping) or inventory.get("schema") != "nico.osv-package-inventory.v1" or inventory.get("inventory_complete") is not True or inventory.get("no_declared_package_sources") is not True or inventory.get("package_source_paths") != [] or not _DIGEST.fullmatch(str(inventory.get("inventory_sha256") or "")):
                    failures.append(name + ":no_package_inventory_unverified")
            not_applicable.append(name)
            continue
        if record.get("applicable") is False:
            failures.append(name + ":contradictory_applicability")
        if state not in _COMPLETE:
            failures.append(name + ":scanner_incomplete:" + (state or "missing"))
        if not any(record.get(k) is True for k in ("verified_complete", "execution_complete", "verified")):
            failures.append(name + ":execution_not_verified")
        if record.get("timed_out") is True or record.get("returncode_valid") is False:
            failures.append(name + ":execution_failed")
        if record.get("output_capture_complete") is False:
            failures.append(name + ":output_incomplete")
        retained = any(record.get(k) is True for k in ("raw_artifact_retention_complete", "artifact_retained"))
        raw = record.get("raw_artifact") or {}
        raw_digest = record.get("raw_artifact_sha256") or (raw.get("sha256") if isinstance(raw, Mapping) else "")
        # A report's own digest cannot substitute for the raw scanner artifact.
        if not retained or not _DIGEST.fullmatch(str(raw_digest or "")):
            failures.append(name + ":raw_scanner_evidence_missing")
        if state in _COMPLETE:
            completed.append(name)
    for name in REQUIRED_TOOLS:
        if name not in seen:
            failures.append(name + ":requested_scanner_missing")
    if not completed:
        failures.append("no_applicable_scanner_execution")
    return {"schema": "nico.complete-assessment-execution-gate.v1", "passed": not failures,
            "run_id": expected_run, "commit_sha": expected_commit,
            "completed_tools": completed, "not_applicable_tools": not_applicable,
            "failures": sorted(set(failures)), "not_applicable_receives_completion_credit": False,
            "no_vulnerabilities_claimed": False, "human_review_required": True,
            "human_approval_proven": False, "client_delivery_allowed": False}


def require_complete_assessment(canonical: Mapping[str, Any], *, expected_commit: str, expected_run: str) -> dict[str, Any]:
    result = complete_assessment_evidence(canonical, expected_commit=expected_commit, expected_run=expected_run)
    if not result["passed"]:
        raise RuntimeError("Complete-assessment evidence blocked: " + "; ".join(result["failures"]))
    return result
