"""Owner-only, read-only availability of a run's retained scanner evidence.

This surface never accepts scanner IDs or storage paths from the caller, returns
raw output, starts scanners, rebuilds reports, or exercises human authority.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
import re
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from nico.comprehensive_run_store import ComprehensiveRunNotFound
from nico.scanner_evidence_pipeline_v1 import DEFAULT_RAW_ROOT
from nico.scanner_tool_runners import MAX_SCANNER_PARSE_BYTES
from nico.scanner_worker import get_scan
from nico.scanner_execution_receipt_v1 import provenance_summary
from nico.specialist_access_v1 import SPECIALIST_SCOPE
from nico.v2_scanner_reconciliation import KNOWN_SCANNERS

VERSION = "nico.comprehensive-scanner-inventory.v1"
ROUTE = "/assessment/comprehensive-run/{run_id}/scanner-evidence"
_HEADERS = {"Cache-Control": "no-store, private, max-age=0"}
_SHA256 = re.compile(r"[a-fA-F0-9]{64}")
_COMMIT = re.compile(r"[a-fA-F0-9]{40}")
_RUN = re.compile(r"comprun_[A-Za-z0-9_-]{1,120}")
_VERSION = re.compile(r"(?<![\w.])v?(\d{1,4}\.\d{1,4}(?:\.\d{1,4})?(?:[-+][0-9A-Za-z.-]{1,40})?)(?![\w.])")
_STATES = {"queued", "running", "complete", "completed", "completed_clean", "completed_with_findings", "failed", "timeout", "timed_out", "partial", "unavailable", "not_applicable", "blocked"}


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _digest(value: Any) -> str | None:
    return str(value).lower() if isinstance(value, str) and _SHA256.fullmatch(value) else None


def _number(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _hash_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _error(status: int, code: str) -> JSONResponse:
    # Codes are fixed server literals. Never include storage/parser exceptions,
    # source payloads, or a caller's purported identity in denial responses.
    return JSONResponse({"status": "blocked", "detail": {"code": code}}, status_code=status, headers=_HEADERS)


def _raw_metadata(record: Mapping[str, Any], *, binding: Mapping[str, Any]) -> dict[str, Any]:
    from nico.scanner_raw_artifact_storage_v1 import read_scanner_artifact
    read = read_scanner_artifact(
        record, binding=binding, raw_root=DEFAULT_RAW_ROOT,
        limit=MAX_SCANNER_PARSE_BYTES,
    )
    metadata = dict(read.metadata)
    if record.get('status') == 'not_applicable':
        verified = False
        inventory = _mapping(record.get('applicability_evidence'))
        name = _scanner_name(record)
        if metadata.get('availability') == 'verified' and read.raw:
            try:
                observation = json.loads(read.raw)
                if name == 'osv-scanner':
                    from nico.scanner_package_inventory_v1 import justified_no_packages
                    verified = (observation.get('schema') == 'nico.osv-applicability-observation.v1'
                                and observation.get('inventory') == inventory
                                and justified_no_packages(inventory, binding['commit_sha'])
                                and observation.get('native_exit_code') == 128
                                and 'no package sources found' in str(observation.get('native_stderr') or '').casefold()
                                and observation.get('native_json_output') is False)
                else:
                    from nico.node_scanner_applicability_v1 import justified_inapplicability, observation_bytes
                    verified = justified_inapplicability(inventory, name, binding['commit_sha']) and read.raw == observation_bytes(inventory, name)
            except (ValueError, TypeError, AttributeError):
                verified = False
        metadata['applicability_observation_verified'] = verified
    return metadata


def _scanner_name(record: Mapping[str, Any]) -> str | None:
    name = record.get("scanner_name") or record.get("tool") or record.get("scanner")
    return name if isinstance(name, str) and name in KNOWN_SCANNERS else None


def _scanner_metadata(record: Mapping[str, Any], *, scan: Mapping[str, Any], commit: str) -> dict[str, Any]:
    bindings = [record[key] for key in ("commit_sha", "snapshot_commit_sha", "target_commit_sha") if key in record]
    source_matches = bool(bindings) and all(isinstance(value, str) and value.lower() == commit for value in bindings)
    source_matches = source_matches and all(record.get(key) == scan.get(key) for key in ("run_id", "scan_id", "customer_id", "project_id", "repository") if key in record)
    version_line = record.get("scanner_tool_version")
    version_line = version_line if isinstance(version_line, str) and len(version_line) <= 500 else ""
    version = _VERSION.search(version_line)
    command = record.get("command_intent")
    command = command if isinstance(command, str) and len(command) <= 8000 else ""
    state = record.get("status")
    observed = record.get("execution_observed_for_this_report")
    observed = observed if type(observed) is bool else None
    if state in {"unavailable", "not_applicable", "blocked"} and type(record.get("exit_code", record.get("returncode"))) is not int:
        observed = False
    raw = _raw_metadata(record, binding={**{key: scan.get(key) for key in ("run_id", "scan_id", "customer_id", "project_id", "repository")}, "commit_sha": commit, "scanner_name": _scanner_name(record)}) if source_matches else {"availability": "source_mismatch"}
    return {
        "scanner_name": _scanner_name(record),
        "execution_status": state if state in _STATES else "unknown",
        "exit_code": record.get("exit_code", record.get("returncode")) if type(record.get("exit_code", record.get("returncode"))) is int else None,
        "source_identity_verified": source_matches,
        "source_checkout_verified": record.get('source_checkout_verified') if type(record.get('source_checkout_verified')) is bool else None,
        "commit_sha": commit if source_matches else None,
        "scanner_version": version.group(1) if version else None,
        "version_evidence": "parsed_from_retained_version_line" if version else "unavailable",
        "version_line_sha256": _hash_bytes(version_line.encode()) if version_line else None,
        "retained_record_artifact_sha256": _digest(record.get("artifact_hash")),
        "configuration": {
            "generated_config_sha256": _digest(record.get("generated_config_sha256")),
            "configured_rule_count": _number(record.get("configured_rule_count")),
            "retained_command_intent_sha256": _hash_bytes(command.encode()) if command else None,
            "full_configuration_verified": False,
        },
        "execution_observed": observed,
        "retained_execution_observed_claim": record.get("execution_observed_for_this_report") if type(record.get("execution_observed_for_this_report")) is bool else None,
        "output_capture_complete": record.get("output_capture_complete") if type(record.get("output_capture_complete")) is bool else None,
        "output_truncated": record.get("output_truncated") if type(record.get("output_truncated")) is bool else None,
        "timed_out": record.get("timed_out") if type(record.get("timed_out")) is bool else None,
        "applicable": record.get("applicable") if type(record.get("applicable")) is bool else None,
        "applicability_evidence_retained": bool(record.get("applicability_evidence")),
        "applicability_inventory_sha256": _digest(_mapping(record.get('applicability_evidence')).get('inventory_sha256')),
        "applicability_observation_verified": raw.get('applicability_observation_verified') is True,
        "returncode_valid": record.get('returncode_valid') if type(record.get('returncode_valid')) is bool else None,
        "scanner_error_count": _number(record.get("scanner_error_count")),
        "coverage_status": "not_evaluated_by_inventory",
        "execution_provenance": provenance_summary(record),
        "raw_artifact": raw,
    }


def inventory_for_record(record: Mapping[str, Any], *, run_id: str) -> JSONResponse:
    """Verify stored run-selected scanner bytes without granting route authority.

    Callers must supply an integrity-validated run record or its integrity-bound
    status projection. No caller-supplied scanner ID or storage path is accepted.
    """
    try:
        identity = _mapping(record.get("identity"))
        commit = identity.get("commit_sha")
        if identity.get("run_id") != run_id or not isinstance(commit, str) or not _COMMIT.fullmatch(commit):
            return _error(409, "scanner_evidence_source_mismatch")
        stages = _mapping(record.get("stage_results"))
        references: set[str] = set()
        for stage_name in ("dependency_security_static_analysis", "deep_scanner_triage"):
            stage = _mapping(stages.get(stage_name))
            for source in (stage, _mapping(stage.get("scanner")), _mapping(stage.get("scanner_triage"))):
                reference = source.get("scan_id")
                if isinstance(reference, str) and reference:
                    references.add(reference)
        if len(references) != 1:
            return _error(409, "scanner_evidence_reference_unavailable")
        scan_id = next(iter(references))
        scan = get_scan(scan_id)
        if not isinstance(scan, Mapping) or scan.get("status") == "not_found":
            return _error(409, "scanner_evidence_unavailable")
        if scan.get("scan_id") != scan_id or any(not identity.get(key) or scan.get(key) != identity[key] for key in ("run_id", "customer_id", "project_id", "repository")) or any(str(scan.get(key) or "").lower() != commit.lower() for key in ("snapshot_commit_sha", "actual_commit_sha")) or scan.get("snapshot_match") is not True:
            return _error(409, "scanner_evidence_source_mismatch")
        raw_records = scan.get("scanner_results")
        records_retained = isinstance(raw_records, list)
        raw_records = raw_records if records_retained else []
        known = [item for item in raw_records if isinstance(item, Mapping) and _scanner_name(item)]
        names = Counter(_scanner_name(item) for item in known)
        requested = scan.get("tools_requested")
        requested = requested if isinstance(requested, list) else []
        requested_names = {name for name in requested if isinstance(name, str) and name in KNOWN_SCANNERS}
        metadata = [_scanner_metadata(item, scan=scan, commit=commit.lower()) for item in known]
        for name in requested_names - names.keys():
            metadata.append({"scanner_name": name, "execution_status": "unknown", "coverage_status": "not_evaluated_by_inventory", "raw_artifact": {"availability": "scanner_record_missing"}})
        metadata.sort(key=lambda item: item["scanner_name"])
        unknown_records = len(raw_records) - len(known)
        unknown_requested = sum(1 for name in requested if not isinstance(name, str) or name not in KNOWN_SCANNERS)
        duplicates = sum(count - 1 for count in names.values())
        complete = bool(metadata) and not (unknown_records or unknown_requested or duplicates) and all(item["raw_artifact"]["availability"] == "verified" for item in metadata)
        return JSONResponse({
            "artifact_schema": VERSION,
            "status": "inventory_complete" if complete else "inventory_incomplete",
            "authenticated_authority": "nico_admin",
            "read_only": True,
            "run_id": run_id,
            "run_revision": _number(record.get("revision")),
            "repository": identity["repository"],
            "commit_sha": commit.lower(),
            "scan_id": scan_id,
            "checked_at": datetime.now(UTC).isoformat(),
            "scanner_record_count": len(raw_records) if records_retained else None,
            "unknown_scanner_record_count": unknown_records,
            "unknown_requested_scanner_count": unknown_requested,
            "duplicate_scanner_record_count": duplicates,
            "verification_byte_limit": MAX_SCANNER_PARSE_BYTES,
            "scanner_records": metadata,
            "coverage_status": "not_evaluated_by_inventory",
            "assessment_mutated": False,
            "approval_or_delivery_action_performed": False,
        }, headers=_HEADERS)
    except ComprehensiveRunNotFound:
        return _error(404, "scanner_evidence_unavailable")
    except Exception:
        # This boundary intentionally conceals exception strings: storage and
        # scanner exceptions may embed private paths, findings or credentials.
        return _error(503, "scanner_evidence_inventory_unavailable")


def _inventory(request: Request, run_id: str) -> JSONResponse:
    controller = getattr(request.app.state, "comprehensive_api_controller", None)
    service = getattr(controller, "_service", None)
    if not callable(getattr(service, "load_read_only", None)):
        return _error(503, "scanner_evidence_service_unavailable")
    try:
        record = service.load_read_only(run_id)
    except ComprehensiveRunNotFound:
        return _error(404, "scanner_evidence_unavailable")
    except Exception:
        return _error(503, "scanner_evidence_inventory_unavailable")
    return inventory_for_record(record, run_id=run_id)


def scanner_evidence_binding(record: Mapping[str, Any], canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Retain only the identity and expected artifact hashes in the small projection."""
    from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS

    identity = _mapping(record.get("identity"))
    stages = _mapping(record.get("stage_results"))
    selected = {}
    for name in ("dependency_security_static_analysis", "deep_scanner_triage"):
        stage = _mapping(stages.get(name))
        selected[name] = {key: {"scan_id": _mapping(stage.get(key)).get('scan_id')}
                          for key in ('scanner', 'scanner_triage') if _mapping(stage.get(key)).get('scan_id')}
        if stage.get('scan_id'):
            selected[name]['scan_id'] = stage['scan_id']
    records = canonical.get("requested_scanner_records") or _mapping(canonical.get("assessment")).get("requested_scanner_records") or []
    hashes = {}
    for item in records:
        if isinstance(item, Mapping) and item.get("scanner_name") in REQUIRED_TOOLS:
            hashes[item["scanner_name"]] = _digest(item.get("raw_artifact_sha256") or _mapping(item.get("raw_artifact")).get("sha256"))
    return {"identity": {key: identity.get(key) for key in ("run_id", "customer_id", "project_id", "repository", "commit_sha")},
            "revision": record.get("revision"), "stage_results": selected,
            "scanner_artifact_sha256s": hashes}


def verify_status_scanner_evidence(response: Mapping[str, Any]) -> dict[str, Any]:
    """Recheck retained bytes after either cached or freshly assembled status reads.

    The response remains a readable technical draft when evidence is unavailable.
    Only derived execution credit changes; historical reports and approvals do not.
    """
    import json
    from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS

    result = deepcopy(dict(response))
    if result.get("terminal") is not True or not isinstance(result.get("scanner_execution_summary"), Mapping):
        return result
    binding = _mapping(result.get("scanner_evidence_binding"))
    identity = _mapping(binding.get("identity"))
    expected = _mapping(binding.get("scanner_artifact_sha256s"))
    failures = []
    if not binding or any(not identity.get(key) or identity[key] != result.get(key) for key in ("run_id", "customer_id", "project_id", "repository", "commit_sha")) or binding.get("revision") != result.get("revision"):
        inventory = {}
        failures.append("scanner_status_binding_unverified")
    else:
        inspected = inventory_for_record(binding, run_id=identity["run_id"])
        inventory = json.loads(inspected.body)
        if inspected.status_code != 200:
            failures.append("scanner_retention_authority_unavailable")
    records = inventory.get("scanner_records") or []
    valid = set()
    for item in records:
        name = item.get("scanner_name")
        raw = _mapping(item.get("raw_artifact"))
        state_valid = (
            item.get('execution_status') == 'not_applicable' and item.get('applicable') is False
            and item.get('applicability_observation_verified') is True
        ) or (
            item.get('execution_status') in {'complete', 'completed', 'completed_clean', 'completed_with_findings'}
            and item.get('execution_observed') is True and item.get('output_capture_complete') is True
            and item.get('output_truncated') is not True and item.get('timed_out') is not True
            and item.get('returncode_valid') is not False and item.get('applicable') is not False
            and item.get('source_checkout_verified') is not False
        )
        if state_valid and item.get("source_identity_verified") is True and raw.get("availability") == "verified" and expected.get(name) and expected[name] == raw.get("sha256"):
            valid.add(name)
        else:
            failures.append(str(name) + ":retained_bytes_unverified")
    if any(inventory.get(key) for key in ("duplicate_scanner_record_count", "unknown_scanner_record_count", "unknown_requested_scanner_count")):
        valid.clear()
        failures.append("scanner_population_invalid")
    summary = dict(result["scanner_execution_summary"])
    states = {item['scanner_name']: item.get('execution_status') for item in records}
    completed = [name for name in summary.get("completed_tools", []) if name in valid and states.get(name) != 'not_applicable']
    not_applicable = [name for name in summary.get("not_applicable_tools", []) if name in valid and states.get(name) == 'not_applicable']
    incomplete = [name for name in REQUIRED_TOOLS if name not in completed and name not in not_applicable]
    applicable_count = len(REQUIRED_TOOLS) - len(not_applicable)
    summary.update(completed_count=len(completed), completed_tools=completed,
                   not_applicable_tools=not_applicable, incomplete_tools=incomplete,
                   applicable_count=applicable_count,
                   percent=round(100 * len(completed) / applicable_count) if applicable_count else None,
                   status="partial" if incomplete or failures else "complete",
                   verification_scope="current_source_run_bound_retained_bytes")
    result["scanner_execution_summary"] = summary
    result["scanner_evidence_verification"] = {
        "schema": "nico.scanner-retention-verification.v1", "read_only": True,
        "run_id": result.get("run_id"), "commit_sha": result.get("commit_sha"),
        "run_revision": result.get("revision"), "scan_id": inventory.get("scan_id"),
        "scanner_records": records, "failures": sorted(set(failures)),
        "verified_tools": sorted(valid), "assessment_mutated": False,
    }
    return result


def install_comprehensive_scanner_inventory(app: FastAPI) -> dict[str, Any]:
    if getattr(app.state, "nico_scanner_inventory_v1", None):
        return dict(app.state.nico_scanner_inventory_v1)

    async def inventory(run_id: str, request: Request) -> JSONResponse:
        authority = _mapping(getattr(request.state, "nico_specialist_authority", None))
        if authority.get("authority") != "nico_admin" or authority.get("scope") not in {SPECIALIST_SCOPE, "comprehensive_review_and_delivery"}:
            return _error(403, "owner_administration_required")
        if not _RUN.fullmatch(run_id) or request.query_params:
            return _error(422, "scanner_evidence_request_invalid")
        return await run_in_threadpool(_inventory, request, run_id)

    app.add_api_route(ROUTE, inventory, methods=["GET"], tags=["assessment"])
    app.openapi_schema = None
    result = {"installed": True, "artifact_schema": VERSION, "read_only": True}
    app.state.nico_scanner_inventory_v1 = result
    return dict(result)
