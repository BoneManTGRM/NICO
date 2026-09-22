"""Verified remote native receipts published under the durable job's lease lock.

The initial profile is the existing prepared standalone Cppcheck pass. It makes
no compilation-database, build, header-context, runtime or qualification claim.
No profile is selected automatically or enabled by public intake parameters.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import base64
import binascii
import gzip
import hashlib
import html
import json
import re
from pathlib import PurePosixPath
import xml.etree.ElementTree as ET

from nico.assessment_worker_jobs import JobConflict, JobIdentity, JobLimits, WorkerJobs, _digest
from nico.cppcheck_native_output import NativeOutputRedactionRequired, parse_native
from nico.scanner_raw_artifact_storage_v1 import ScannerArtifactStore

MAX_RECEIPT_BYTES = 8 * 1024 * 1024
CONFIGURATION = {"platform": "unix64", "c_standard": "c11", "cpp_standard": "c++20",
                 "max_configs": 12, "checks": ["warning", "style", "performance", "portability", "information"]}


def enqueue_snapshot_scan(scan: dict, contract: dict, adapter):
    """Internal typed dispatch, never selected from a public request's dictionary."""
    from nico.github_actions_proof_auth_v1 import expected_release_sha
    contract = validate_contract(contract)
    if (scan.get("provider_access_mode") != "anonymous_public"
            or scan.get("provider_credential_used") is not False):
        raise ValueError("worker_source_access_unsupported")
    release = expected_release_sha()
    contract_sha = _digest(contract)
    scan = deepcopy(scan)
    requested = sorted(set([*(scan.get("tools_requested") or []), "cppcheck"]))
    scan["scan_id"] = "scan_worker_" + _digest({key: scan[key] for key in (
        "customer_id", "project_id", "run_id", "repository", "snapshot_commit_sha")}
        | {"contract_sha256": contract_sha, "release_revision": release,
           "tools_requested": requested})[:40]
    identity = JobIdentity(scan["customer_id"], scan["project_id"], scan["run_id"], scan["scan_id"],
                           scan["repository"], scan["snapshot_commit_sha"], contract_sha, release)
    scan.update(worker_job_id=identity.job_id, tools_requested=requested)
    WorkerJobs(adapter).enqueue(identity, JobLimits(**contract["limits"]), contract=contract, scan=scan)
    return adapter.get("scanner_runs", identity.scan_id)


def canonical_bytes(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def validate_contract(contract: dict) -> dict:
    required = {"profile", "tool_version", "image_digest", "configuration", "targets", "limits", "max_receipt_bytes"}
    if not isinstance(contract, dict) or set(contract) != required:
        raise ValueError("worker_contract_invalid")
    if (not isinstance(contract["tool_version"], str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+(?:\.[0-9]+)?", contract["tool_version"])
            or not isinstance(contract["image_digest"], str)
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", contract["image_digest"])):
        raise ValueError("worker_contract_tool_invalid")
    targets = contract["targets"]
    if not isinstance(targets, dict) or not 1 <= len(targets) <= 20000:
        raise ValueError("worker_contract_targets_invalid")
    for path, digest in targets.items():
        if (not isinstance(path, str) or not path or len(path) > 1000
                or any(ord(char) < 32 or char == "\\" for char in path)
                or path.startswith("/") or ":" in path or PurePosixPath(path).as_posix() != path
                or any(part in {".", ".."} for part in path.split("/"))
                or not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest)):
            raise ValueError("worker_contract_path_or_digest_invalid")
    if contract['profile'] in {'cpp-configured-v1', 'cpp-sanitized-v1', 'cpp-runtime-cases-v1'}:
        from nico.assessment_cpp_configuration import validate_configuration
        validate_configuration(contract['configuration'], targets,
            sanitized=contract['profile'] == 'cpp-sanitized-v1',
            runtime=contract['profile'] == 'cpp-runtime-cases-v1')
    elif contract['profile'] != 'cppcheck-standalone-v1' or contract['configuration'] != CONFIGURATION:
        raise ValueError('worker_contract_tool_invalid')
    JobLimits(**contract["limits"])
    if (type(contract["max_receipt_bytes"]) is not int
            or not 1024 <= contract["max_receipt_bytes"] <= MAX_RECEIPT_BYTES
            or len(canonical_bytes(contract)) > 4 * 1024 * 1024):
        raise ValueError("worker_contract_size_invalid")
    return deepcopy(contract)


def validate_receipt(identity: JobIdentity, contract: dict, lease: str, worker: str, receipt: dict):
    contract = validate_contract(contract)
    if _digest(contract) != identity.contract_sha256:
        raise ValueError("worker_contract_digest_mismatch")
    required = {"schema", "identity", "lease_id", "worker_id", "image_digest", "tool_version",
                "configuration_sha256", "target_hashes", "native", "native_sha256"}
    if not isinstance(receipt, dict) or set(receipt) != required:
        raise ValueError("worker_receipt_schema_invalid")
    if receipt["schema"] not in {"nico.worker-native-receipt.v1", "nico.worker-native-receipt.v2", "nico.worker-native-receipt.v3", "nico.worker-native-receipt.v4", "nico.worker-native-receipt.v5"}:
        raise ValueError("worker_receipt_schema_invalid")
    if (receipt['schema'].endswith('.v3')) != (contract['profile'] == 'cpp-configured-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v4')) != (contract['profile'] == 'cpp-sanitized-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    if (receipt['schema'].endswith('.v5')) != (contract['profile'] == 'cpp-runtime-cases-v1'):
        raise ValueError('worker_receipt_profile_mismatch')
    expected = {"identity": asdict(identity),
        "lease_id": lease, "worker_id": worker, "image_digest": contract["image_digest"],
        "tool_version": contract["tool_version"], "configuration_sha256": _digest(contract["configuration"]),
        "target_hashes": contract["targets"]}
    if any(receipt.get(key) != value for key, value in expected.items()):
        raise ValueError("worker_receipt_binding_mismatch")
    encoded = canonical_bytes(receipt)
    if len(encoded) > contract["max_receipt_bytes"]:
        raise ValueError("worker_receipt_size_invalid")
    native = receipt["native"]
    if receipt['schema'].endswith(('.v3', '.v4', '.v5')):
        if _digest(native) != receipt['native_sha256']:
            raise ValueError('worker_native_digest_or_schema_invalid')
        return _configured_record(identity, contract, receipt, encoded)
    execution_keys = {"exit_code", "timed_out", "output_truncated", "duration_ms", "invocation"}
    streams = ({"xml", "progress"} if receipt["schema"].endswith(".v1")
               else {"xml", "stdout", "stderr", "encoding"})
    if (not isinstance(native, dict) or set(native) != execution_keys | streams
            or _digest(native) != receipt["native_sha256"]):
        raise ValueError("worker_native_digest_or_schema_invalid")
    decoding_failed = False
    if receipt["schema"].endswith(".v2"):
        if native["encoding"] != "base64":
            raise ValueError("worker_native_encoding_invalid")
        decoded = {}
        from nico.scanner_tool_runners import redact_text
        for key in ("xml", "stdout", "stderr"):
            if not isinstance(native[key], str):
                raise ValueError("worker_native_encoding_invalid")
            try:
                raw_stream = base64.b64decode(native[key], validate=True)
                text = raw_stream.decode("utf-8")
            except (binascii.Error, ValueError) as error:
                if not isinstance(error, UnicodeDecodeError):
                    raise ValueError("worker_native_encoding_invalid") from None
                text = raw_stream.decode("utf-8", errors="replace")
                decoding_failed = True
            if redact_text(text) != text or redact_text(html.unescape(text)) != html.unescape(text):
                raise ValueError("worker_native_redaction_required")
            decoded[key] = text
        native = {**{key: native[key] for key in execution_keys}, "xml": decoded["xml"],
                  "progress": decoded["stdout"] + decoded["stderr"]}
    invocation = ["cppcheck", "--xml", "--enable=warning,style,performance,portability,information",
        "--check-level=normal", "--max-configs=12", "--std=c++20", "--std=c11", "--platform=unix64",
        "-j2", "--file-list=/work/cppcheck-inputs.txt", "--output-file=/work/cppcheck.xml"]
    if (not isinstance(native["xml"], str) or not isinstance(native["progress"], str)
            or type(native["exit_code"]) is not int or not -255 <= native["exit_code"] <= 255
            or type(native["timed_out"]) is not bool or type(native["output_truncated"]) is not bool
            or type(native["duration_ms"]) is not int
            or not 0 <= native["duration_ms"] <= contract["limits"]["wall_seconds"] * 1000
            or native["invocation"] != invocation):
        raise ValueError("worker_native_execution_invalid")
    from nico.scanner_tool_runners import redact_text
    if any(redact_text(native[key]) != native[key] for key in ("xml", "progress")):
        raise ValueError("worker_native_redaction_required")
    paths = sorted(contract["targets"])
    findings, limitations, observed = [], [], []
    parsed = False
    try:
        if decoding_failed:
            raise ValueError("native_output_encoding_invalid")
        findings, limitations, observed = parse_native(native["xml"], native["progress"], paths,
                                                       version=contract["tool_version"])
        parsed = True
    except NativeOutputRedactionRequired:
        raise ValueError("worker_native_redaction_required") from None
    except (ValueError, ET.ParseError):
        limitations = [{"rule_id": "native_output_invalid", "message": "Native XML was not completely parsed."}]
    complete = (parsed and native["exit_code"] == 0 and not native["timed_out"]
                and not native["output_truncated"] and observed == paths
                and not any(row["rule_id"] != "checkersReport" for row in limitations))
    status = ("completed" if complete else "timed_out" if native["timed_out"] else
              "failed" if not parsed or native["exit_code"] != 0 else "partial")
    receipt_sha = hashlib.sha256(encoded).hexdigest()
    binding = {"run_id": identity.run_id, "scan_id": identity.scan_id, "customer_id": identity.customer_id,
        "project_id": identity.project_id, "repository": identity.repository_id,
        "commit_sha": identity.revision, "scanner_name": "cppcheck"}
    for finding in findings:
        finding.update(commit_sha=identity.revision, configuration_sha256=receipt["configuration_sha256"],
                       evidence_reference="worker_receipt:" + receipt_sha)
        finding["observation_id"] = "cppcheck_" + _digest({key: finding[key] for key in (
            "rule_id", "path", "line", "column", "commit_sha", "configuration_sha256")})
    record = {**binding, "tool": "cppcheck", "category": "static", "status": status,
        "completed": complete, "verified_complete": complete, "verified_for_this_report": complete,
        "current_run": True, "execution_observed_for_this_report": True,
        "exact_commit_match": True, "snapshot_commit_sha": identity.revision,
        "output_capture_complete": parsed and not native["output_truncated"], "raw_artifact_capture_complete": True,
        "returncode_valid": native["exit_code"] == 0, "exit_code": native["exit_code"],
        "timed_out": native["timed_out"], "output_truncated": native["output_truncated"],
        "duration_seconds": native["duration_ms"] / 1000, "findings": findings, "finding_count": len(findings),
        "scanner_tool_version": contract["tool_version"], "applicable": True, "evidence_required": True,
        "reason": "" if complete else "Native target execution or parsing is incomplete; retained observations require review.",
        "worker_provenance": {"job_id": identity.job_id, "worker_id": worker,
            "release_revision": identity.release_revision, "image_digest": contract["image_digest"],
            "contract_sha256": identity.contract_sha256, "configuration_sha256": receipt["configuration_sha256"],
            "receipt_sha256": receipt_sha, "profile": contract["profile"]},
        "cppcheck_source_coverage": {"requested_targets": paths, "requested_target_count": len(paths),
            "observed_targets": observed, "observed_target_count": len(observed),
            "unobserved_targets": sorted(set(paths) - set(observed)), "limitations": limitations,
            "population_sha256": _digest(contract["targets"]), "configuration_aware": False,
            "header_context_verified": False, "repository_build_executed": False,
            "all_repository_configurations_analyzed": False},
        "human_review_required": True, "client_delivery_allowed": False}
    return encoded, record, binding


def _configured_record(identity, contract, receipt, encoded):
    from nico.assessment_cpp_configuration import validate_native
    result = validate_native(receipt['native'], contract)
    receipt_sha = hashlib.sha256(encoded).hexdigest()
    binding = {'run_id': identity.run_id, 'scan_id': identity.scan_id, 'customer_id': identity.customer_id,
        'project_id': identity.project_id, 'repository': identity.repository_id,
        'commit_sha': identity.revision, 'scanner_name': 'cppcheck'}
    for finding in result['findings']:
        finding.update(commit_sha=identity.revision, configuration_sha256=receipt['configuration_sha256'],
                       evidence_reference='worker_receipt:' + receipt_sha)
        finding['observation_id'] = 'cppcheck_' + _digest({key: finding[key] for key in (
            'rule_id', 'path', 'line', 'column', 'commit_sha', 'configuration_sha256',
            'translation_unit', 'unit_configuration_sha256')})
    complete = result['complete']
    record = {**binding, 'tool': 'cppcheck', 'category': 'static', 'status': result['status'],
        'completed': complete, 'verified_complete': complete, 'verified_for_this_report': complete,
        'current_run': True, 'execution_observed_for_this_report': True, 'exact_commit_match': True,
        'snapshot_commit_sha': identity.revision, 'output_capture_complete': not result['output_truncated'],
        'raw_artifact_capture_complete': True, 'returncode_valid': complete, 'exit_code': 0 if complete else None,
        'timed_out': result['status'] == 'timed_out', 'output_truncated': result['output_truncated'],
        'duration_seconds': result['duration_ms'] / 1000, 'findings': result['findings'],
        'finding_count': len(result['findings']), 'scanner_tool_version': contract['tool_version'],
        'applicable': True, 'evidence_required': True,
        'reason': '' if complete else 'Native target execution or parsing is incomplete; retained observations require review.',
        'worker_provenance': {'job_id': identity.job_id, 'worker_id': receipt['worker_id'],
            'release_revision': identity.release_revision, 'image_digest': contract['image_digest'],
            'contract_sha256': identity.contract_sha256, 'configuration_sha256': receipt['configuration_sha256'],
            'receipt_sha256': receipt_sha, 'profile': contract['profile']},
        'cppcheck_source_coverage': result['coverage'], 'cpp_build_evidence': result['build'],
        'human_review_required': True, 'client_delivery_allowed': False}
    return encoded, record, binding


def publish_receipt(jobs: WorkerJobs, identity: JobIdentity, lease: str, worker: str, receipt: dict):
    job = jobs.get(identity)
    if job is None or not isinstance(job.get("contract"), dict):
        raise JobConflict("worker_contract_missing")
    raw, record, binding = validate_receipt(identity, job["contract"], lease, worker, receipt)
    compressed = gzip.compress(raw, mtime=0)
    raw_sha = hashlib.sha256(raw).hexdigest()
    store = ScannerArtifactStore(jobs.adapter._connect)

    def publish(connection, _job):
        row = connection.execute("SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE",
                                 (identity.scan_id,)).fetchone()
        scan = row["payload"] if row else {}
        if any(scan.get(key) != value for key, value in {
            "worker_job_id": identity.job_id, "customer_id": identity.customer_id,
            "project_id": identity.project_id, "run_id": identity.run_id,
            "repository": identity.repository_id, "snapshot_commit_sha": identity.revision,
        }.items()):
            raise JobConflict("worker_scan_binding_mismatch")
        artifact_id = store.put_in_transaction(connection, binding, compressed, raw_sha)
        record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=raw_sha,
            raw_artifact={"storage_backend": "postgres", "artifact_id": artifact_id,
                "sha256": raw_sha, "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
                "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True})
        # The prepared C++ profile cannot erase the assessment's other requested
        # scanners. They remain explicitly unavailable until supported dispatch
        # for the full qualified contract exists.
        unsupported = [name for name in scan.get("tools_requested", []) if name != "cppcheck"]
        missing_records = [{**binding, "scanner_name": name, "tool": name, "status": "unavailable",
            "completed": False, "verified_complete": False, "verified_for_this_report": False,
            "applicability_state": "unproven", "execution_state": "unavailable",
            "reason": "The selected worker profile does not execute this requested tool.",
            "raw_artifact_retention_complete": False, "findings": [],
            "human_review_required": True, "client_delivery_allowed": False} for name in unsupported]
        # No worker-supplied canonical status, findings, score or human decision is accepted.
        scan.update(status="complete", current_stage="worker_receipt_retained", progress_percent=100,
            actual_commit_sha=identity.revision, snapshot_match=True, scanner_results=[record, *missing_records],
            unavailable_tools=unsupported,
            receipt_sha256=raw_sha, tools_run=["cppcheck"] if record["completed"] else [],
            failed_tools=["cppcheck"] if record["status"] in {"failed", "partial"} else [],
            timed_out_tools=["cppcheck"] if record["timed_out"] else [],
            finding_summary={"raw_total": len(record["findings"]), "material_total": 0,
                "review_required_total": len(record["findings"]), "approved_or_nonblocking_total": 0,
                "excluded_test_only_total": 0, "by_tool": {"cppcheck": {
                    "raw": len(record["findings"]), "material": 0,
                    "review_required": len(record["findings"]), "approved_or_nonblocking": 0,
                    "excluded_test_only": 0}}, "by_category": {}},
            human_review_required=True, client_delivery_allowed=False)
        connection.execute("UPDATE scanner_runs SET status=%s,payload=%s,updated_at=clock_timestamp() "
            "WHERE scan_id=%s AND customer_id=%s AND project_id=%s",
            (scan["status"], jobs.adapter._jsonb(scan), identity.scan_id, identity.customer_id, identity.project_id))

    return jobs.complete(identity, lease, raw_sha, worker_id=worker, publish=publish)
