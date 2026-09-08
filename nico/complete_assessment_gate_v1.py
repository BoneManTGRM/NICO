"""Reject incomplete scanner evidence independently of successful PDF rendering."""
from __future__ import annotations

import re
import hashlib
from collections.abc import Mapping
from typing import Any

REQUIRED_TOOLS = ("pip-audit", "npm-audit", "osv-scanner", "bandit", "semgrep", "eslint", "typescript", "gitleaks", "trufflehog")
SCANNER_SUMMARY_POLICY = "source-input-retention-v2"
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
_COMPLETE = {"completed", "complete", "completed_clean", "completed_with_findings"}


class ScannerEvidenceBlocked(RuntimeError):
    """Keep the safe rejection receipt available to release artifact collectors."""
    def __init__(self, evidence: dict[str, Any]):
        self.evidence = evidence
        super().__init__('Complete-assessment evidence blocked: ' + '; '.join(evidence['failures']))


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
        states = {str(record[key]).casefold().replace('-', '_') for key in ('state', 'status') if key in record}
        if len(states) > 1 and not states.issubset(_COMPLETE):
            failures.append(name + ':execution_state_mismatch')
        raw = record.get('raw_artifact') or {}
        if isinstance(raw, Mapping) and 'sha256' in raw and 'raw_artifact_sha256' in record and raw['sha256'] != record['raw_artifact_sha256']:
            failures.append(name + ':raw_digest_mismatch')
        sources = [record[key] for key in ("commit_sha", "target_commit_sha", "snapshot_commit_sha") if key in record]
        if not sources or any(source != expected_commit for source in sources) or record.get("exact_commit_match") is not True:
            failures.append(name + ":source_identity_unverified")
        if record.get("run_id") and record.get("run_id") != expected_run:
            failures.append(name + ":run_identity_mismatch")
        if record.get('source_checkout_verified') is False:
            failures.append(name + ':assessed_source_changed_or_unverified')
        if state == "not_applicable":
            if name not in {"npm-audit", "typescript", "pip-audit", "osv-scanner"}:
                failures.append(name + ":applicability_inventory_unsupported")
            reason = record.get("applicability_reason")
            if record.get("applicable") is not False or not isinstance(reason, str) or not reason.strip():
                failures.append(name + ":applicability_unjustified")
            if any(record.get(k) is True for k in ("completed", "verified", "verified_complete", "verified_for_this_report")):
                failures.append(name + ":not_applicable_claimed_as_completed")
            if name == "osv-scanner":
                from nico.scanner_package_inventory_v1 import justified_no_packages
                inventory = record.get("applicability_evidence") or {}
                if not justified_no_packages(inventory, expected_commit):
                    failures.append(name + ":no_package_inventory_unverified")
                if record.get("raw_artifact_retention_complete") is not True or not _DIGEST.fullmatch(str(record.get("raw_artifact_sha256") or "")):
                    failures.append(name + ":no_package_observation_unretained")
            if name in {"npm-audit", "typescript", "pip-audit"}:
                from nico.node_scanner_applicability_v1 import justified_inapplicability, observation_bytes
                inventory = record.get("applicability_evidence") or {}
                if not justified_inapplicability(inventory, name, expected_commit):
                    failures.append(name + ":node_input_inventory_unverified")
                else:
                    expected_raw = hashlib.sha256(observation_bytes(inventory, name)).hexdigest()
                    raw = record.get("raw_artifact") or {}
                    digest = record.get("raw_artifact_sha256") or (raw.get("sha256") if isinstance(raw, Mapping) else "")
                    if record.get("raw_artifact_retention_complete") is not True or digest != expected_raw:
                        failures.append(name + ":node_input_inventory_bytes_unverified")
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


def require_retained_assessment(canonical: Mapping[str, Any], status: Mapping[str, Any], *, expected_commit: str, expected_run: str) -> dict[str, Any]:
    """Release acceptance must bind canonical claims to the fresh status authority.

    The server verifies the actual retained bytes. This consumer additionally
    checks every declared alias and the native state, never a summary percentage.
    """
    result = complete_assessment_evidence(canonical, expected_commit=expected_commit, expected_run=expected_run)
    failures = list(result['failures'])
    status = status if isinstance(status, Mapping) else {}
    receipt = status.get('scanner_evidence_verification')
    receipt = receipt if isinstance(receipt, Mapping) else {}
    if (receipt.get('schema') != 'nico.scanner-retention-verification.v1'
        or receipt.get('run_id') != expected_run or status.get('run_id') != expected_run
        or receipt.get('commit_sha') != expected_commit or status.get('commit_sha') != expected_commit
        or type(status.get('revision')) is not int or receipt.get('run_revision') != status.get('revision')
        or receipt.get('read_only') is not True or receipt.get('failures') != []
        or not receipt.get('scan_id')):
        failures.append('scanner_retention_receipt_unverified')
    native = {}
    rows = receipt.get('scanner_records')
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, Mapping) or row.get('scanner_name') not in REQUIRED_TOOLS or row.get('scanner_name') in native:
            failures.append('scanner_retention_population_invalid')
            continue
        native[row['scanner_name']] = row
    records = canonical.get('requested_scanner_records')
    if not isinstance(records, list):
        records = (canonical.get('assessment') or {}).get('requested_scanner_records')
    if not isinstance(records, list):
        records = canonical.get('scanner_execution_records') or []
    for record in records:
        if not isinstance(record, Mapping):
            continue
        name = record.get('scanner_name') or record.get('tool') or record.get('scanner')
        observed = native.get(name, {})
        raw = observed.get('raw_artifact') or {}
        declared = record.get('raw_artifact') or {}
        hashes = [record[key] for key in ('raw_artifact_sha256',) if key in record]
        if isinstance(declared, Mapping) and 'sha256' in declared:
            hashes.append(declared['sha256'])
        if (observed.get('source_identity_verified') is not True or observed.get('commit_sha') != expected_commit
            or raw.get('availability') != 'verified' or not hashes
            or not _DIGEST.fullmatch(str(raw.get('sha256') or ''))
            or any(value != raw.get('sha256') for value in hashes)):
            failures.append(str(name) + ':retained_bytes_unverified')
        if record.get('scan_id') != receipt.get('scan_id') or record.get('evidence_reference') != 'scanner_runs/' + str(receipt.get('scan_id')):
            failures.append(str(name) + ':scanner_reference_mismatch')
        state = str(record.get('state') or record.get('status') or '').casefold().replace('-', '_')
        if state == 'not_applicable':
            inventory = record.get('applicability_evidence') or {}
            if (observed.get('execution_status') != 'not_applicable' or observed.get('applicable') is not False
                or observed.get('applicability_observation_verified') is not True
                or observed.get('applicability_inventory_sha256') != inventory.get('inventory_sha256')):
                failures.append(str(name) + ':applicability_observation_unverified')
        elif (observed.get('execution_status') not in _COMPLETE
              or observed.get('execution_observed') is not True
              or observed.get('output_capture_complete') is not True
              or observed.get('timed_out') is True or observed.get('output_truncated') is True
              or observed.get('returncode_valid') is False
              or observed.get('source_checkout_verified') is False
              or observed.get('applicable') is False):
            failures.append(str(name) + ':native_execution_incomplete')
    result.update(passed=not failures, failures=sorted(set(failures)),
                  retention_verification=receipt, verification_scope='current_source_run_bound_retained_bytes')
    if failures:
        raise ScannerEvidenceBlocked(result)
    return result


def scanner_execution_summary(canonical: Mapping[str, Any], *, expected_commit: str, expected_run: str) -> dict[str, Any]:
    """Bounded current execution projection; never change the retained report.

    Reuse the independent gate. A completed orchestration stage is not a scanner
    result, and a tool with failed evidence must not receive completion credit.
    """
    from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

    assessment = canonical.get('assessment')
    assessment = assessment if isinstance(assessment, Mapping) else {}
    # Only retained source inventories and native records establish applicability.
    # Do not scan arbitrary report prose or multi-megabyte artifact strings for paths.
    source = {key: canonical[key] for key in (
        'identity', 'repository_evidence', 'file_evidence', 'dependency_evidence',
        'requested_scanner_records', 'scanner_execution_records',
    ) if key in canonical}
    source['assessment'] = {key: assessment[key] for key in (
        'repository_evidence', 'file_evidence', 'dependency_evidence',
        'requested_scanner_records', 'scanner_execution_records',
    ) if key in assessment}
    gate = complete_assessment_evidence(
        normalize_scanner_applicability_canonical(source),
        expected_commit=expected_commit, expected_run=expected_run,
    )
    failures = gate['failures']
    identity_valid = not any(value in failures for value in (
        'expected_identity_missing', 'canonical_identity_mismatch',
        'requested_scanner_records_missing',
    ))
    valid = lambda name: identity_valid and not any(value.startswith(name + ':') for value in failures)
    completed = [name for name in REQUIRED_TOOLS if name in gate['completed_tools'] and valid(name)]
    not_applicable = [name for name in REQUIRED_TOOLS if name in gate['not_applicable_tools'] and valid(name)]
    incomplete = [name for name in REQUIRED_TOOLS if name not in completed and name not in not_applicable]
    applicable_count = len(REQUIRED_TOOLS) - len(not_applicable)
    return {
        'schema': 'nico.scanner-execution-ui-summary.v1',
        'evaluation_policy': SCANNER_SUMMARY_POLICY,
        'run_id': expected_run, 'commit_sha': expected_commit,
        'status': 'complete' if gate['passed'] else 'partial' if identity_valid else 'unknown',
        'completed_count': len(completed), 'applicable_count': applicable_count,
        'percent': round(100 * len(completed) / applicable_count) if identity_valid and applicable_count else None,
        'completed_tools': completed, 'incomplete_tools': incomplete,
        'not_applicable_tools': not_applicable,
        'verification_scope': 'retained_canonical_execution_evidence',
        'assessment_mutated': False, 'human_approval_proven': False,
        'client_delivery_allowed': False,
    }
