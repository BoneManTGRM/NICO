"""Observed scanner invocation metadata; never a claim of complete coverage.

No environment values, raw credentials, arbitrary repository config contents or
secret findings are retained here. Only NICO-generated profile content is retained
after redaction and byte-identity checks. Reported native targets are not a
filesystem-wide coverage census.
"""
from __future__ import annotations

from collections import OrderedDict
from collections.abc import Mapping, Sequence
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

VERSION = "nico.scanner-execution-receipt.v1"
_MAX_ARG = 8192
_MAX_ARGS = 1024
_MAX_INPUT_BYTES = 16 * 1024 * 1024
_MAX_NATIVE_BYTES = 32 * 1024 * 1024
_MAX_TARGETS = 20000
_GENERATED_PROFILES: OrderedDict[str, dict[str, Any]] = OrderedDict()
_SENSITIVE = re.compile(r"(?:password|passwd|secret|token|credential|api[-_]?key|authorization|auth[-_]?header|extraheader)", re.I)
_URL = re.compile(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s]+")


def _hash(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def safe_text(value: Any) -> str:
    from nico.scanner_tool_runners import redact_text

    def url(match: re.Match[str]) -> str:
        try:
            parsed = urlsplit(match.group())
            host = parsed.netloc.rsplit("@", 1)[-1]
            return urlunsplit((parsed.scheme, host, parsed.path, "[REDACTED]" if parsed.query else "", "[REDACTED]" if parsed.fragment else ""))
        except ValueError:
            return "[REDACTED_URL]"

    text = _URL.sub(url, str(value))
    text = re.sub(r"(?i)(?:authorization\s*[:=]\s*|\b(?:bearer|basic)\s+)\S+(?:\s+\S+)?", "[REDACTED_AUTH]", text)
    return redact_text(text)


def safe_argv(arguments: Sequence[str]) -> dict[str, Any]:
    values: list[str] = []
    hide_next = False
    executable = Path(str(arguments[0])).name if arguments else ""
    complete = len(arguments) <= _MAX_ARGS
    for index, raw in enumerate(arguments[:_MAX_ARGS]):
        text = str(raw)
        key, separator, _value = text.partition("=")
        sensitive = bool(_SENSITIVE.search(key)) and (key.startswith("-") or separator)
        short_secret = key in {"-H", "--header", "-u", "--user", "-c"} or (key == "-p" and executable not in {"tsc", "tsc.js"})
        short_flags = {"-H", "-u", "-c"}
        if executable not in {"tsc", "tsc.js"}:
            short_flags.add("-p")
        attached_short = next((flag for flag in short_flags if text.startswith(flag) and len(text) > len(flag)), None)
        if hide_next:
            value = "[REDACTED]"
            hide_next = False
        elif index and attached_short:
            value = attached_short + "[REDACTED]"
        elif index and (sensitive or short_secret):
            value = key + "=[REDACTED]" if separator else text
            hide_next = not separator
        else:
            value = safe_text(text)
        if len(value) > _MAX_ARG:
            value = value[:_MAX_ARG] + "[TRUNCATED]"
            complete = False
        values.append(value)
    return {"argv": values, "argument_count": len(arguments), "captured_argument_count": len(values), "argv_capture_status": "complete_redacted" if complete else "partial_redacted", "redaction_applied": True}


def write_generated_config(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Register only profiles emitted by NICO, never arbitrary repository configs.

    A bounded process-local registration is an observation aid, not authority.
    Snapshots retain its redacted content only if observed bytes match exactly.
    """
    path.write_text(content, encoding=encoding)
    raw = content.encode(encoding)
    if len(raw) > 65536:
        return
    safe = safe_text(content)
    identity = str(path.resolve())
    _GENERATED_PROFILES[identity] = {
        "original_sha256": _hash(raw), "redacted_content": safe,
        "redacted_content_sha256": _hash(safe.encode("utf-8")),
        "content_scope": "nico_generated_profile_only",
        "content_redaction_status": "changed" if safe != content else "unchanged_after_redaction",
    }
    _GENERATED_PROFILES.move_to_end(identity)
    while len(_GENERATED_PROFILES) > 128:
        _GENERATED_PROFILES.popitem(last=False)


def _input_paths(arguments: Sequence[str], cwd: Path) -> list[tuple[str, Path]]:
    executable = Path(str(arguments[0])).name if arguments else ""
    flags = {"--config": "explicit_config"}
    if executable in {"tsc", "tsc.js"}: flags["-p"] = "project_config"
    if executable == "pip-audit": flags["-r"] = "requirements_manifest"
    paths: list[tuple[str, Path]] = []
    for index, value in enumerate(arguments):
        key, separator, attached = str(value).partition("=")
        if key not in flags: continue
        target = attached if separator else (str(arguments[index + 1]) if index + 1 < len(arguments) else "")
        if target and not _URL.search(target): paths.append((flags[key], cwd / target))
    if executable == "npm" and "audit" in arguments:
        paths.extend(("lockfile_input", cwd / name) for name in ("package-lock.json", "package.json"))
    # Discovery candidates are explicitly not evidence that a tool loaded them.
    candidates = {"bandit": (".bandit",), "gitleaks": (".gitleaks.toml",), "semgrep": (".semgrepignore", ".gitignore")}
    paths.extend(("discovery_candidate_not_proven_loaded", cwd / name) for name in candidates.get(executable, ()))
    return paths


def input_snapshot(arguments: Sequence[str], cwd: Path, *, workspace_root: Path | None = None) -> list[dict[str, Any]]:
    output = []
    # Restrict reads to this execution workspace; never follow an input symlink.
    boundary = (workspace_root or cwd).resolve()
    for kind, path in _input_paths(arguments, cwd):
        entry: dict[str, Any] = {"kind": kind, "path": safe_text(str(path)), "status": "unavailable"}
        try:
            resolved = path.resolve()
            if any(part.is_symlink() for part in (path, *path.parents)) or not resolved.is_relative_to(boundary):
                entry["status"] = "outside_input_boundary_or_symlink"
            elif not path.is_file(): entry["status"] = "missing"
            elif path.stat().st_size > _MAX_INPUT_BYTES: entry["status"] = "size_limit_exceeded"
            else:
                with path.open("rb") as handle: content = handle.read(_MAX_INPUT_BYTES + 1)
                if len(content) > _MAX_INPUT_BYTES: entry["status"] = "size_limit_exceeded"
                else:
                    entry.update(status="hashed", bytes=len(content), sha256=_hash(content))
                    generated = _GENERATED_PROFILES.get(str(resolved))
                    if generated and generated["original_sha256"] == entry["sha256"]:
                        entry["generated_profile"] = dict(generated)
        except (OSError, ValueError):
            entry["status"] = "unavailable"
        output.append(entry)
    return output


def invocation_receipt(arguments: Sequence[str], *, cwd: Path | None, before: list[dict[str, Any]], after: list[dict[str, Any]], returncode: int, timed_out: bool) -> dict[str, Any]:
    receipt: dict[str, Any] = {"artifact_schema": VERSION, **safe_argv(arguments), "cwd": safe_text(str(cwd)) if cwd is not None else None,
        "cwd_evidence": "forwarded_to_runner" if cwd is not None else "not_observed", "environment_values_retained": False,
        "input_identities_before": before, "input_identities_after": after,
        "input_identity_status": "stable_observed_inputs" if before and before == after and all(row["status"] in {"hashed", "missing"} for row in before) else "changed_unavailable_or_not_observed",
        "exit_code": returncode, "timed_out": timed_out, "full_configuration_verified": False}
    argv = receipt["argv"]
    exclusions: list[str] = []
    for index, argument in enumerate(argv):
        if argument in {"--exclude", "-x"} and index + 1 < len(argv): exclusions.append(argv[index + 1])
        elif argument.startswith("--exclude="): exclusions.append(argument.split("=", 1)[1])
    receipt["explicit_exclusion_arguments"] = exclusions
    receipt["exclusion_scope"] = "explicit_argv_only; implicit rules and effective target exclusion are not verified"
    receipt["receipt_sha256"] = _hash(_json(receipt))
    return receipt


def native_coverage_observation(tool: str, raw_blob: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {"status": "not_reported", "source": "retained_native_output", "raw_artifact_sha256": raw_blob.get("sha256"),
        "reported_targets": [], "reported_target_count": None, "native_error_count": None, "native_skipped_target_count": None, "all_repository_targets_analyzed": False, "full_coverage_verified": False,
        "applicability_status": "requires_scope_review"}
    if tool not in {"semgrep", "bandit", "eslint"}: return result
    try:
        compressed = bytes.fromhex(str(raw_blob.get("gzip_hex") or ""))
        if _hash(compressed) != raw_blob.get("gzip_sha256"):
            result["status"] = "integrity_mismatch"
            return result
        with gzip.GzipFile(fileobj=io.BytesIO(compressed)) as handle: raw = handle.read(_MAX_NATIVE_BYTES + 1)
        if len(raw) > _MAX_NATIVE_BYTES:
            result["status"] = "observation_limit_exceeded"
            return result
        if _hash(raw) != raw_blob.get("sha256"):
            result["status"] = "integrity_mismatch"
            return result
        native = json.loads(raw)
        targets = None
        if tool == "semgrep" and isinstance(native, dict):
            paths = native.get("paths")
            targets = paths.get("scanned") if isinstance(paths, dict) else None
            skipped = paths.get("skipped") if isinstance(paths, dict) else None
            result["native_skipped_target_count"] = len(skipped) if isinstance(skipped, list) else None
            errors = native.get("errors")
            result["native_error_count"] = len(errors) if isinstance(errors, list) else None
        elif tool == "bandit" and isinstance(native, dict):
            metrics = native.get("metrics")
            targets = [key for key, value in metrics.items() if key != "_totals" and isinstance(value, dict)] if isinstance(metrics, dict) else None
            errors = native.get("errors")
            result["native_error_count"] = len(errors) if isinstance(errors, list) else None
        elif tool == "eslint" and isinstance(native, list):
            targets = [row["filePath"] for row in native] if all(isinstance(row, dict) and isinstance(row.get("filePath"), str) for row in native) else None
            fatal = [row.get("fatalErrorCount") for row in native if isinstance(row, dict)]
            result["native_error_count"] = sum(fatal) if len(fatal) == len(native) and all(type(n) is int and n >= 0 for n in fatal) else None
        if isinstance(targets, list) and all(isinstance(path, str) for path in targets):
            safe = [safe_text(path) for path in targets[:_MAX_TARGETS]]
            result.update(status="reported_native_targets" if len(targets) <= _MAX_TARGETS else "partial_native_targets", reported_targets=safe,
                          reported_target_count=len(targets), captured_target_count=len(safe), reported_targets_sha256=_hash(_json(safe)))
    except (OSError, ValueError, TypeError, EOFError): result["status"] = "native_output_unparseable"
    return result


def receipt_summary(value: Any) -> dict[str, Any]:
    """Whitelist metadata for owner inventory; never expose argv, paths or content."""
    missing = {"status": "not_recorded", "receipt_sha256": None, "argv_capture_status": "unknown", "full_configuration_verified": False}
    if not isinstance(value, Mapping) or value.get("artifact_schema") != VERSION: return missing
    provided = value.get("receipt_sha256")
    if not isinstance(provided, str) or provided != _hash(_json({k: v for k, v in value.items() if k != "receipt_sha256"})):
        return {**missing, "status": "integrity_mismatch"}
    return {"status": "retained_receipt_integrity_verified", "receipt_sha256": provided,
            "argv_capture_status": value.get("argv_capture_status") if value.get("argv_capture_status") in {"complete_redacted", "partial_redacted"} else "unknown",
            "argument_count": value.get("argument_count") if type(value.get("argument_count")) is int else None,
            "input_identity_status": value.get("input_identity_status") if value.get("input_identity_status") in {"stable_observed_inputs", "changed_unavailable_or_not_observed"} else "unknown",
            "full_configuration_verified": False}


def coverage_summary(value: Any) -> dict[str, Any]:
    value = value if isinstance(value, Mapping) else {}
    statuses = {"not_reported", "observation_limit_exceeded", "reported_native_targets", "partial_native_targets", "native_output_unparseable", "integrity_mismatch"}
    result = {"status": value.get("status") if value.get("status") in statuses else "not_recorded",
              "full_coverage_verified": False, "all_repository_targets_analyzed": False,
              "applicability_status": "requires_scope_review"}
    for key in ("reported_target_count", "captured_target_count", "native_error_count", "native_skipped_target_count"):
        result[key] = value.get(key) if type(value.get(key)) is int and value[key] >= 0 else None
    for key in ("raw_artifact_sha256", "reported_targets_sha256"):
        result[key] = value.get(key) if isinstance(value.get(key), str) and re.fullmatch(r"[0-9a-f]{64}", value[key]) else None
    return result


def provenance_summary(record: Mapping[str, Any]) -> dict[str, Any]:
    version = re.search(r"(?<![\w.])v?(\d{1,4}\.\d{1,4}(?:\.\d{1,4})?(?:[-+][0-9A-Za-z.-]{1,40})?)(?![\w.])", str(record.get("scanner_tool_version") or "")[:500])
    invocations = record.get("scanner_invocation_receipts")
    return {"scanner_version": version.group(1) if version else None,
            "execution_receipt": receipt_summary(record.get("scanner_execution_receipt")),
            "invocation_receipts": [receipt_summary(item) for item in invocations[:1024]] if isinstance(invocations, list) else [],
            "invocation_receipt_count": len(invocations) if isinstance(invocations, list) else None,
            "configuration_scope": "observed_input_files_and_explicit_arguments_only",
            "full_configuration_verified": False,
            "coverage": coverage_summary(record.get("coverage_evidence"))}
