from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

VERSION = "nico.scanner-execution-contract.v1"
SUITE_VERSION = "nico.scanner-suite-contract.v1"

# These are NICO's execution-tool pins. ESLint and TypeScript prefer the exact
# target lockfile binaries; the pinned runtime values are safe fallbacks and are
# retained as the execution contract rather than silently claiming the target
# repository used those versions.
PINNED_EXECUTORS: dict[str, dict[str, str]] = {
    "pip-audit": {"version": "2.10.1", "source": "requirements.txt"},
    "npm-audit": {"version": "10.8.2", "source": "NICO runtime package-manager contract"},
    "osv-scanner": {"version": "2.3.8", "source": "hosted binary release"},
    "bandit": {"version": "1.9.4", "source": "requirements.txt"},
    "semgrep": {"version": "1.170.0", "source": "isolated hosted virtual environment"},
    "eslint": {"version": "9.39.3", "source": "target lockfile or pinned runtime fallback"},
    "typescript": {"version": "6.0.3", "source": "target lockfile or pinned runtime fallback"},
    "gitleaks": {"version": "8.30.1", "source": "hosted binary release"},
    "trufflehog": {"version": "3.95.0", "source": "hosted binary release"},
}

_REQUIRED_TOOLS = tuple(PINNED_EXECUTORS)
_SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9_.-]+$")


def _canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    ).encode("utf-8")


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _spec_value(spec: Any, name: str, default: Any = None) -> Any:
    if isinstance(spec, Mapping):
        return spec.get(name, default)
    return getattr(spec, name, default)


def scanner_execution_contract(spec: Any) -> dict[str, Any]:
    name = str(_spec_value(spec, "name") or "").strip()
    if name not in PINNED_EXECUTORS:
        raise ValueError(f"scanner_contract.unsupported_tool:{name or 'blank'}")
    command = [str(item) for item in (_spec_value(spec, "command", ()) or ())]
    category = str(_spec_value(spec, "category") or "").strip()
    executor = PINNED_EXECUTORS[name]
    config = {
        "tool": name,
        "category": category,
        "command": command,
        "timeout_seconds": int(_spec_value(spec, "timeout_seconds", 0) or 0),
        "max_output_chars": int(_spec_value(spec, "max_output_chars", 0) or 0),
        "valid_returncodes": sorted(
            int(value)
            for value in (_spec_value(spec, "valid_returncodes", ()) or ())
        ),
        "requires_project_commands": bool(
            _spec_value(spec, "requires_project_commands", False)
        ),
        "scans_git_history": bool(_spec_value(spec, "scans_git_history", False)),
    }
    ruleset = {
        "mode": "local_or_command_bound",
        "command_sha256": _sha256(command),
        "configuration_sha256": _sha256(config),
    }
    if name == "semgrep" and "auto" in command:
        # This is an explicit limitation, not a false pin. Package 12 must not
        # call cross-date deterministic qualification complete until the
        # resolved rule payload is retained and bound.
        ruleset.update(
            {
                "mode": "dynamic_registry_auto",
                "immutable": False,
                "limitation": "Semgrep auto configuration requires a retained resolved-rules digest for cross-date reproducibility.",
            }
        )
    else:
        ruleset["immutable"] = True
    contract = {
        "artifact_schema": VERSION,
        "tool": name,
        "category": category,
        "executor_version": executor["version"],
        "executor_version_source": executor["source"],
        "version_verification_status": "bound_expected_version",
        "configuration": config,
        "ruleset": ruleset,
        "exact_commit_required": True,
        "complete_output_capture_required": True,
        "redacted_artifact_retention_required": True,
        "candidate_disposition_is_human_only": True,
    }
    contract["contract_sha256"] = _sha256(contract)
    return contract


def attach_scanner_execution_contract(result: Mapping[str, Any], spec: Any) -> dict[str, Any]:
    output = deepcopy(dict(result))
    contract = scanner_execution_contract(spec)
    output["scanner_contract"] = contract
    output["scanner_contract_sha256"] = contract["contract_sha256"]
    output["executor_expected_version"] = contract["executor_version"]
    output["executor_version_source"] = contract["executor_version_source"]
    output["candidate_disposition_status"] = "pending_human_review"
    return output


def scanner_suite_contract(specs: Iterable[Any]) -> dict[str, Any]:
    contracts = [scanner_execution_contract(spec) for spec in specs]
    by_tool = {item["tool"]: item for item in contracts}
    missing = sorted(set(_REQUIRED_TOOLS) - set(by_tool))
    duplicate_count = len(contracts) - len(by_tool)
    payload = {
        "artifact_schema": SUITE_VERSION,
        "required_tools": list(_REQUIRED_TOOLS),
        "configured_tools": sorted(by_tool),
        "missing_required_tools": missing,
        "duplicate_tool_contracts": duplicate_count,
        "contracts": by_tool,
        "all_executor_versions_bound": all(
            bool(item.get("executor_version")) for item in contracts
        ),
        "all_rulesets_immutable": all(
            item.get("ruleset", {}).get("immutable") is True for item in contracts
        ),
    }
    payload["suite_contract_sha256"] = _sha256(payload)
    return payload


def _artifact_subject(result: Mapping[str, Any]) -> dict[str, Any]:
    subject = deepcopy(dict(result))
    subject.pop("retained_redacted_artifact", None)
    subject.pop("stderr", None)
    # Parsed findings and bounded execution metadata are retained. Process stderr
    # is omitted from durable artifacts because scanner diagnostics can echo
    # target-repository content even after normal redaction.
    return subject


def persist_redacted_scanner_artifact(
    result: Mapping[str, Any],
    *,
    scan_id: str,
    root: str | Path | None = None,
) -> dict[str, Any]:
    """Persist one complete redacted scanner result atomically when configured.

    A configured-but-unwritable store is an explicit scanner evidence failure,
    not an uncaught worker exception and not an inline-only success.
    """

    output = deepcopy(dict(result))
    configured_root = str(
        root if root is not None else os.getenv("NICO_SCANNER_RAW_ARTIFACT_ROOT", "")
    ).strip()
    if not configured_root:
        output["retained_redacted_artifact"] = {
            "status": "inline_only",
            "reason": "NICO_SCANNER_RAW_ARTIFACT_ROOT is not configured",
            "sha256": _sha256(_artifact_subject(output)),
        }
        return output

    safe_scan_id = str(scan_id or "").strip()
    tool = str(output.get("tool") or "").strip()
    if not _SAFE_COMPONENT.fullmatch(safe_scan_id):
        raise ValueError("scanner_artifact.scan_id:unsafe")
    if not _SAFE_COMPONENT.fullmatch(tool):
        raise ValueError("scanner_artifact.tool:unsafe")

    destination_dir = Path(configured_root) / safe_scan_id
    destination = destination_dir / f"{tool}.redacted.json"
    subject = _artifact_subject(output)
    encoded = json.dumps(subject, indent=2, sort_keys=True, ensure_ascii=False).encode("utf-8")
    digest = hashlib.sha256(encoded).hexdigest()
    temporary: Path | None = None
    try:
        destination_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination_dir,
            prefix=f".{tool}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            handle.write(encoded)
            temporary = Path(handle.name)
        temporary.replace(destination)
    except OSError as exc:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
        output["retained_redacted_artifact"] = {
            "status": "failed",
            "reason": f"durable scanner artifact retention failed: {type(exc).__name__}",
            "sha256": digest,
            "size_bytes": len(encoded),
            "redacted": True,
            "atomic_write": False,
        }
        return output

    output["retained_redacted_artifact"] = {
        "status": "retained",
        "path": str(destination),
        "sha256": digest,
        "size_bytes": len(encoded),
        "redacted": True,
        "atomic_write": True,
    }
    return output


def validate_scanner_execution_record(
    result: Mapping[str, Any],
    *,
    expected_commit_sha: str = "",
) -> dict[str, Any]:
    errors: list[str] = []
    tool = str(result.get("tool") or "").strip()
    if tool not in PINNED_EXECUTORS:
        errors.append(f"tool:unsupported:{tool or 'blank'}")
    contract = result.get("scanner_contract")
    if not isinstance(contract, Mapping):
        errors.append("scanner_contract:required")
    elif str(result.get("scanner_contract_sha256") or "") != str(
        contract.get("contract_sha256") or ""
    ):
        errors.append("scanner_contract_sha256:mismatch")
    elif _sha256({k: v for k, v in contract.items() if k != "contract_sha256"}) != str(
        contract.get("contract_sha256") or ""
    ):
        errors.append("scanner_contract:content_mismatch")

    status = str(result.get("status") or "").strip().casefold()
    if status == "completed":
        if result.get("verified_for_this_report") is not True:
            errors.append("completed.verified_for_this_report:required")
        if result.get("output_capture_complete") is not True:
            errors.append("completed.output_capture_complete:required")
        if result.get("timed_out") is True:
            errors.append("completed.timed_out:must_be_false")
    elif result.get("verified_for_this_report") is True:
        errors.append("non_completed.verified_for_this_report:must_be_false")

    if expected_commit_sha:
        if str(result.get("snapshot_commit_sha") or "").casefold() != expected_commit_sha.casefold():
            errors.append("snapshot_commit_sha:mismatch")
        if str(result.get("actual_commit_sha") or "").casefold() != expected_commit_sha.casefold():
            errors.append("actual_commit_sha:mismatch")
        if result.get("exact_commit_match") is not True:
            errors.append("exact_commit_match:required")

    retained = result.get("retained_redacted_artifact")
    if not isinstance(retained, Mapping):
        errors.append("retained_redacted_artifact:required")
    elif retained.get("status") not in {"retained", "inline_only"}:
        errors.append("retained_redacted_artifact.status:invalid")

    return {
        "status": "valid" if not errors else "invalid",
        "validation_errors": sorted(set(errors)),
        "tool": tool,
    }


__all__ = [
    "PINNED_EXECUTORS",
    "SUITE_VERSION",
    "VERSION",
    "attach_scanner_execution_contract",
    "persist_redacted_scanner_artifact",
    "scanner_execution_contract",
    "scanner_suite_contract",
    "validate_scanner_execution_record",
]
