from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable, Mapping

VERSION = "nico.scanner-runtime-truth.v2"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _source_metadata_path(finding: Mapping[str, Any]) -> str:
    metadata = finding.get("SourceMetadata")
    data = metadata.get("Data") if isinstance(metadata, Mapping) else None
    git = data.get("Git") if isinstance(data, Mapping) else None
    return _text(git.get("file") or git.get("path")) if isinstance(git, Mapping) else ""


def snapshot_finding_path(finding: Mapping[str, Any]) -> str:
    value = (
        finding.get("dependency_path")
        or finding.get("source_path")
        or finding.get("file_path")
        or finding.get("filename")
        or finding.get("path")
        or finding.get("filePath")
        or finding.get("File")
        or ((finding.get("source") or {}).get("path") if isinstance(finding.get("source"), Mapping) else "")
        or _source_metadata_path(finding)
        or ""
    )
    return str(value).replace("\\", "/")


def snapshot_test_or_example_path(path: str) -> bool:
    from nico import snapshot_scanner_worker as worker

    normalized = str(path or "").replace("\\", "/").casefold()
    if normalized in {".env.example", ".env.sample", ".env.template", "env.example", "env.sample", "env.template"}:
        return True
    previous = getattr(snapshot_test_or_example_path, "_nico_previous", None)
    if callable(previous) and previous(normalized):
        return True
    parts = [part for part in Path(normalized).parts if part]
    filename = parts[-1] if parts else ""
    return bool(
        any(part in worker._EXCLUDED_PATH_PARTS for part in parts)
        or filename.startswith("test_")
        or filename.endswith(("_test.py", ".test.ts", ".test.tsx", ".spec.ts", ".spec.tsx"))
    )


def osv_findings_with_package_context(payload: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    results = payload.get("results")
    if not isinstance(results, list):
        return findings
    for result in results:
        if not isinstance(result, Mapping):
            continue
        source = result.get("source") if isinstance(result.get("source"), Mapping) else {}
        source_path = _text(source.get("path"))
        packages = result.get("packages")
        if not isinstance(packages, list):
            continue
        for package_record in packages:
            if not isinstance(package_record, Mapping):
                continue
            package = package_record.get("package") if isinstance(package_record.get("package"), Mapping) else {}
            package_name = _text(package.get("name"))
            installed_version = _text(package.get("version"))
            ecosystem = _text(package.get("ecosystem"))
            vulnerabilities = package_record.get("vulnerabilities")
            if not isinstance(vulnerabilities, list):
                continue
            for vulnerability in vulnerabilities:
                if not isinstance(vulnerability, Mapping):
                    continue
                item = dict(vulnerability)
                item.update(
                    {
                        "package": package_name,
                        "package_name": package_name,
                        "installed_version": installed_version,
                        "resolved_version": installed_version,
                        "ecosystem": ecosystem,
                        "dependency_path": source_path,
                        "source": dict(source),
                        "scanner_source_kind": "source_manifest_resolution",
                        "reachability": item.get("reachability") or "unknown",
                        "production_relevant": item.get("production_relevant"),
                    }
                )
                findings.append(item)
    return findings


def _parse_osv_with_context(tool_name: str, result: Any) -> tuple[list[Any], bool, str] | None:
    if tool_name != "osv-scanner":
        return None
    from nico import scanner_tool_runners as runners

    raw_text, capture_complete, capture_reason = runners._complete_stdout(result)
    try:
        payload = json.loads(raw_text or "")
    except json.JSONDecodeError:
        return [], False, capture_reason or "osv-scanner JSON output could not be parsed"
    if not isinstance(payload, dict):
        return [], False, capture_reason or "osv-scanner JSON output was not an object"
    return osv_findings_with_package_context(payload), capture_complete, capture_reason


def _global_eslint_resolution(
    spec: Any,
    workspace: Any,
    preparation: Any,
) -> tuple[tuple[str, ...] | None, Path, str | None] | None:
    if str(getattr(spec, "name", "")) != "eslint":
        return None
    web_dir = workspace.repo_dir / "apps" / "web"
    if preparation is None or not getattr(preparation, "node_modules_ready", False):
        return None
    from nico import scanner_tool_runners as runners

    if not runners._has_eslint_config(web_dir):
        return None
    global_eslint = shutil.which("eslint")
    if not global_eslint:
        return None
    return (global_eslint, ".", "--format", "json"), web_dir, None


def install_scanner_runtime_truth_v2() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners
    from nico import snapshot_scanner_worker as snapshot

    changes = 0

    current_path = snapshot._finding_path
    if not getattr(current_path, "_nico_scanner_runtime_truth_v2", False):
        setattr(snapshot_finding_path, "_nico_scanner_runtime_truth_v2", True)
        setattr(snapshot_finding_path, "_nico_previous", current_path)
        snapshot._finding_path = snapshot_finding_path
        changes += 1

    current_excluded = snapshot._test_or_example_path
    if not getattr(current_excluded, "_nico_scanner_runtime_truth_v2", False):
        setattr(snapshot_test_or_example_path, "_nico_scanner_runtime_truth_v2", True)
        setattr(snapshot_test_or_example_path, "_nico_previous", current_excluded)
        snapshot._test_or_example_path = snapshot_test_or_example_path
        changes += 1

    current_parser: Callable[..., tuple[list[Any], bool, str]] = runners.parse_tool_findings
    if not getattr(current_parser, "_nico_scanner_runtime_truth_v2", False):
        def parse_tool_findings(tool_name: str, result: Any) -> tuple[list[Any], bool, str]:
            parsed = _parse_osv_with_context(tool_name, result)
            if parsed is not None:
                return parsed
            return current_parser(tool_name, result)

        setattr(parse_tool_findings, "_nico_scanner_runtime_truth_v2", True)
        setattr(parse_tool_findings, "_nico_previous", current_parser)
        runners.parse_tool_findings = parse_tool_findings
        changes += 1

    current_resolver = runners._resolve_command_and_cwd
    if not getattr(current_resolver, "_nico_scanner_runtime_truth_v2", False):
        def resolve_command_and_cwd(spec: Any, workspace: Any, preparation: Any):
            command, cwd, reason = current_resolver(spec, workspace, preparation)
            if command is not None:
                return command, cwd, reason
            fallback = _global_eslint_resolution(spec, workspace, preparation)
            return fallback if fallback is not None else (command, cwd, reason)

        setattr(resolve_command_and_cwd, "_nico_scanner_runtime_truth_v2", True)
        setattr(resolve_command_and_cwd, "_nico_previous", current_resolver)
        runners._resolve_command_and_cwd = resolve_command_and_cwd
        changes += 1

    configured_node_path = os.getenv("NODE_PATH", "")
    return {
        "status": "installed" if changes else "already_installed",
        "version": VERSION,
        "changes": changes,
        "gitleaks_uppercase_file_path_supported": True,
        "trufflehog_source_metadata_path_supported": True,
        "example_secret_placeholders_excluded_from_production_risk": True,
        "osv_package_and_version_context_preserved": True,
        "global_eslint_fallback_supported": True,
        "global_node_path_configured": bool(configured_node_path),
        "human_review_required": True,
    }


__all__ = [
    "VERSION",
    "install_scanner_runtime_truth_v2",
    "osv_findings_with_package_context",
    "snapshot_finding_path",
    "snapshot_test_or_example_path",
]
