from __future__ import annotations

import gzip
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterable, Mapping

from nico.worker_execution import WorkerWorkspace

VERSION = "nico.scanner-result-truth.v1"

_DEPENDENCY_FILES = {
    "requirements.txt",
    "pyproject.toml",
    "poetry.lock",
    "Pipfile.lock",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
}
_EXAMPLE_SECRET_NAMES = {
    ".env.example",
    ".env.sample",
    "example.env",
    "sample.env",
    "env.example",
    "env.sample",
}
_PLACEHOLDER_MARKERS = (
    "user:password",
    "username:password",
    "changeme",
    "change-me",
    "example",
    "localhost",
    "127.0.0.1",
    "generate-a-long-random-secret",
    "replace-me",
    "replace_me",
    "your_",
    "your-",
    "dummy",
    "placeholder",
    "<password>",
    "<token>",
    "<secret>",
)


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _relative_path(value: Any, repo_dir: Path) -> str:
    raw = _text(value).replace("\\", "/")
    if not raw:
        return ""
    raw = raw.replace("file://", "")
    repo = str(repo_dir.resolve()).replace("\\", "/").rstrip("/")
    if raw.startswith(repo + "/"):
        raw = raw[len(repo) + 1 :]
    for marker in ("/repo/", "/github/workspace/", "/workspace/"):
        if marker in raw:
            raw = raw.rsplit(marker, 1)[-1]
    while raw.startswith("./"):
        raw = raw[2:]
    return raw.lstrip("/")


def _raw_json(blob: Mapping[str, Any] | None) -> Any:
    if not isinstance(blob, Mapping):
        return None
    try:
        compressed = bytes.fromhex(str(blob.get("gzip_hex") or ""))
        raw = gzip.decompress(compressed)
        return json.loads(raw.decode("utf-8", errors="replace"))
    except (ValueError, OSError, gzip.BadGzipFile, json.JSONDecodeError):
        return None


def _fixed_versions(vulnerability: Mapping[str, Any]) -> list[str]:
    fixed: list[str] = []
    for affected in vulnerability.get("affected") or []:
        if not isinstance(affected, Mapping):
            continue
        for range_item in affected.get("ranges") or []:
            if not isinstance(range_item, Mapping):
                continue
            for event in range_item.get("events") or []:
                if isinstance(event, Mapping) and _text(event.get("fixed")):
                    fixed.append(_text(event.get("fixed")))
    return list(dict.fromkeys(fixed))


def _authoritative_manifests(repo_dir: Path) -> set[str]:
    manifests: set[str] = set()
    for path in repo_dir.rglob("*"):
        if not path.is_file() or path.name not in _DEPENDENCY_FILES:
            continue
        try:
            relative = path.relative_to(repo_dir)
        except ValueError:
            continue
        if any(part in {"node_modules", ".next", "dist", "build", "coverage", ".venv", "venv", "audit-results"} for part in relative.parts):
            continue
        if path.name in {"package-lock.json", "pnpm-lock.yaml", "yarn.lock"} and not (path.parent / "package.json").is_file():
            continue
        manifests.add(str(relative).replace("\\", "/"))
    return manifests


def _osv_contextual_findings(payload: Any, repo_dir: Path) -> tuple[list[dict[str, Any]], int, list[str]]:
    manifests = _authoritative_manifests(repo_dir)
    findings: list[dict[str, Any]] = []
    ignored = 0
    seen: set[tuple[str, str, str, str]] = set()
    results = payload.get("results") if isinstance(payload, Mapping) else []
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, Mapping):
            continue
        source = result.get("source") if isinstance(result.get("source"), Mapping) else {}
        source_path = _relative_path(source.get("path"), repo_dir)
        if source_path and source_path not in manifests:
            ignored += sum(
                len(package_result.get("vulnerabilities") or package_result.get("vulns") or [])
                for package_result in result.get("packages") or []
                if isinstance(package_result, Mapping)
            )
            continue
        for package_result in result.get("packages") or []:
            if not isinstance(package_result, Mapping):
                continue
            package = package_result.get("package") if isinstance(package_result.get("package"), Mapping) else {}
            package_name = _text(package.get("name") or package_result.get("name"))
            installed_version = _text(package.get("version") or package_result.get("version"))
            ecosystem = _text(package.get("ecosystem") or package_result.get("ecosystem"))
            vulnerabilities = package_result.get("vulnerabilities") or package_result.get("vulns") or []
            for raw in vulnerabilities if isinstance(vulnerabilities, list) else []:
                if not isinstance(raw, Mapping):
                    continue
                advisory = _text(raw.get("id") or raw.get("advisory_id"))
                marker = (advisory, package_name.casefold(), installed_version, source_path)
                if marker in seen:
                    continue
                seen.add(marker)
                item = deepcopy(dict(raw))
                item.update(
                    {
                        "advisory_id": advisory,
                        "package": package_name,
                        "installed_version": installed_version,
                        "ecosystem": ecosystem,
                        "dependency_path": source_path,
                        "source": {"path": source_path, "type": _text(source.get("type"))},
                        "fixed_versions": _fixed_versions(raw),
                        "scanner_context_complete": bool(
                            advisory and package_name and installed_version and source_path
                        ),
                    }
                )
                findings.append(item)
    return findings, ignored, sorted(manifests)


def _secret_path(finding: Mapping[str, Any], repo_dir: Path) -> tuple[str, int | None]:
    source = finding.get("SourceMetadata")
    git = {}
    if isinstance(source, Mapping):
        data = source.get("Data") if isinstance(source.get("Data"), Mapping) else {}
        git = data.get("Git") if isinstance(data.get("Git"), Mapping) else {}
    path = _relative_path(
        finding.get("path")
        or finding.get("file")
        or finding.get("file_path")
        or finding.get("filename")
        or finding.get("File")
        or git.get("file"),
        repo_dir,
    )
    line_value = (
        finding.get("line")
        or finding.get("line_number")
        or finding.get("StartLine")
        or git.get("line")
    )
    try:
        line = int(line_value) if line_value is not None else None
    except (TypeError, ValueError):
        line = None
    return path, line


def _source_line(repo_dir: Path, path: str, line: int | None) -> str:
    if not path:
        return ""
    source = repo_dir / path
    if not source.is_file():
        return ""
    try:
        lines = source.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if line is not None and 1 <= line <= len(lines):
        return lines[line - 1]
    return "\n".join(lines[:80])


def _verified_secret(finding: Mapping[str, Any]) -> bool:
    return bool(
        finding.get("Verified") is True
        or finding.get("verified") is True
        or finding.get("verification_status") == "verified"
    )


def _example_placeholder(finding: Mapping[str, Any], repo_dir: Path) -> tuple[bool, str, int | None]:
    path, line = _secret_path(finding, repo_dir)
    name = Path(path).name.casefold() if path else ""
    if name not in _EXAMPLE_SECRET_NAMES or _verified_secret(finding):
        return False, path, line
    source = _source_line(repo_dir, path, line).casefold()
    if source and any(marker in source for marker in _PLACEHOLDER_MARKERS):
        return True, path, line
    return False, path, line


def _reconcile_osv(payload: dict[str, Any], blob: Mapping[str, Any] | None, workspace: WorkerWorkspace) -> dict[str, Any]:
    raw = _raw_json(blob)
    if payload.get("status") == "not_applicable" and isinstance(raw, Mapping) and raw.get("schema") == "nico.osv-applicability-observation.v1":
        payload["osv_context_status"] = "observed_no_package_sources_not_clean"
        payload["osv_context_fail_closed"] = True
        return payload
    contextual, ignored, manifests = _osv_contextual_findings(raw, workspace.repo_dir)
    if raw is None:
        payload["osv_context_status"] = "raw_json_unavailable"
        payload["osv_context_fail_closed"] = True
        return payload
    payload["findings"] = contextual
    payload["findings_count"] = len(contextual)
    payload["authoritative_manifest_paths"] = manifests
    payload["authoritative_manifest_count"] = len(manifests)
    payload["ignored_non_authoritative_candidate_count"] = ignored
    payload["osv_context_status"] = "authoritative_manifest_context_retained"
    payload["osv_context_fail_closed"] = False
    payload["execution_source"] = "canonical_osv_authoritative_manifest_projection"
    return payload


def _reconcile_secret(payload: dict[str, Any], workspace: WorkerWorkspace) -> dict[str, Any]:
    retained: list[dict[str, Any]] = []
    nonblocking: list[dict[str, Any]] = []
    for raw in payload.get("findings") or []:
        if not isinstance(raw, Mapping):
            continue
        item = deepcopy(dict(raw))
        placeholder, path, line = _example_placeholder(item, workspace.repo_dir)
        if placeholder:
            item.update(
                {
                    "path": path,
                    "line": line,
                    "disposition": "verified_example_placeholder",
                    "material": False,
                    "review_required": False,
                    "technical_score_impact": "none",
                    "nonblocking_reason": (
                        "The unverified candidate is in an example environment file and the exact "
                        "source line contains an explicit placeholder value."
                    ),
                }
            )
            nonblocking.append(item)
        else:
            retained.append(item)
    payload["findings"] = retained
    payload["findings_count"] = len(retained)
    payload["nonblocking_findings"] = nonblocking
    payload["verified_example_placeholder_count"] = len(nonblocking)
    payload["secret_candidate_disposition"] = {
        "review_required": len(retained),
        "verified_example_placeholder": len(nonblocking),
        "raw_candidate_count": len(retained) + len(nonblocking),
        "raw_artifact_preserved": True,
    }
    return payload


def reconcile_scanner_payload(
    tool_name: str,
    payload: Mapping[str, Any],
    raw_blob: Mapping[str, Any] | None,
    workspace: WorkerWorkspace,
) -> dict[str, Any]:
    """Project retained raw scanner evidence into accurate decision evidence.

    The immutable raw artifact remains unchanged. Only the client/scoring projection is
    narrowed, enriched, or dispositioned using exact repository source context.
    """

    result = deepcopy(dict(payload))
    if tool_name == "osv-scanner":
        result = _reconcile_osv(result, raw_blob, workspace)
    elif tool_name in {"gitleaks", "trufflehog"}:
        result = _reconcile_secret(result, workspace)
    result["scanner_result_truth_version"] = VERSION
    return result


__all__ = [
    "VERSION",
    "reconcile_scanner_payload",
]
