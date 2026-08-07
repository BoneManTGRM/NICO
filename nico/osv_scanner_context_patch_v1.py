from __future__ import annotations

from copy import deepcopy
from functools import wraps
from pathlib import Path
from typing import Any, Mapping

VERSION = "nico.osv-scanner-context-patch.v1"
_PARSER_MARKER = "_nico_osv_context_parser_v1"
_FALLBACK_MARKER = "_nico_osv_context_fallback_v1"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _source_path(value: Any) -> str:
    if isinstance(value, Mapping):
        return _text(value.get("path"))
    return _text(value)


def _package_context(value: Any) -> tuple[str, str, str]:
    if not isinstance(value, Mapping):
        return "", "", ""
    package = value.get("package")
    if isinstance(package, Mapping):
        name = _text(package.get("name"))
        version = _text(package.get("version"))
        ecosystem = _text(package.get("ecosystem"))
    else:
        name = _text(package)
        version = ""
        ecosystem = ""
    return (
        name or _text(value.get("name")),
        version or _text(value.get("version") or value.get("installed_version")),
        ecosystem or _text(value.get("ecosystem")),
    )


def _contextualize_vulnerability(
    vulnerability: Mapping[str, Any],
    *,
    package_name: str,
    installed_version: str,
    ecosystem: str,
    source: Any,
    groups: Any = None,
) -> dict[str, Any]:
    finding = deepcopy(dict(vulnerability))
    path = _source_path(source)

    # The scanned package is authoritative. Advisory payloads can contain nested
    # affected-package metadata for libraries that are not the dependency OSV
    # actually scanned. Keep that advisory metadata under `affected`, but never
    # let it replace the scanned package identity used for materiality.
    if package_name:
        finding["package"] = package_name
        finding["osv_scanned_package"] = package_name
    if installed_version:
        finding["installed_version"] = installed_version
        finding["osv_scanned_version"] = installed_version
    if ecosystem:
        finding["ecosystem"] = ecosystem
        finding["osv_scanned_ecosystem"] = ecosystem
    if path:
        finding["dependency_path"] = path
    if source:
        finding["dependency_manifest_source"] = deepcopy(source)
    if isinstance(groups, list) and groups:
        finding["osv_groups"] = deepcopy(groups)
    finding["scanner_context_schema"] = VERSION
    return finding


def parse_osv_findings_with_context(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Flatten OSV scanner output while preserving the actual scanned package.

    Supports current OSV Scanner result->packages->vulnerabilities output and
    legacy package/vulnerability shapes. Each flattened advisory retains package
    name, installed version, ecosystem, and manifest path when the scanner
    supplied them.
    """

    findings: list[dict[str, Any]] = []

    def append_package(package_item: Mapping[str, Any], source: Any = None) -> None:
        package_name, installed_version, ecosystem = _package_context(package_item)
        package_source = package_item.get("source") or source
        groups = package_item.get("groups")
        vulnerabilities = (
            package_item.get("vulnerabilities")
            or package_item.get("vulns")
            or []
        )
        if not isinstance(vulnerabilities, list):
            return
        for vulnerability in vulnerabilities:
            if isinstance(vulnerability, Mapping):
                findings.append(
                    _contextualize_vulnerability(
                        vulnerability,
                        package_name=package_name,
                        installed_version=installed_version,
                        ecosystem=ecosystem,
                        source=package_source,
                        groups=groups,
                    )
                )

    results = payload.get("results")
    if isinstance(results, list):
        for result in results:
            if not isinstance(result, Mapping):
                continue
            source = result.get("source")
            packages = result.get("packages")
            if isinstance(packages, list):
                for package_item in packages:
                    if isinstance(package_item, Mapping):
                        append_package(package_item, source)
            else:
                append_package(result, source)

    packages = payload.get("packages")
    if isinstance(packages, list):
        for package_item in packages:
            if isinstance(package_item, Mapping):
                append_package(package_item, package_item.get("source"))

    direct = payload.get("vulns")
    if isinstance(direct, list):
        for vulnerability in direct:
            if isinstance(vulnerability, Mapping):
                findings.append(deepcopy(dict(vulnerability)))

    return findings


def _enrich_fallback_result(result: Any, repo_dir: Path, runners: Any) -> Any:
    if not isinstance(result, dict):
        return result
    findings = result.get("findings")
    if not isinstance(findings, list):
        return result

    dependencies = runners._osv_query_dependencies(repo_dir)
    by_identity = {
        (_text(item.get("name")).casefold(), _text(item.get("version"))): item
        for item in dependencies
        if isinstance(item, Mapping)
    }
    output = deepcopy(result)
    enriched: list[Any] = []
    for raw in findings:
        if not isinstance(raw, Mapping):
            enriched.append(deepcopy(raw))
            continue
        finding = deepcopy(dict(raw))
        package_name, installed_version, ecosystem = _package_context(finding)
        dependency = by_identity.get((package_name.casefold(), installed_version))
        if dependency:
            ecosystem = ecosystem or _text(dependency.get("ecosystem"))
            source = dependency.get("source")
            if ecosystem:
                finding["ecosystem"] = ecosystem
                finding["osv_scanned_ecosystem"] = ecosystem
            if _text(source):
                finding["dependency_path"] = _text(source)
                finding["dependency_manifest_source"] = _text(source)
            if package_name:
                finding["osv_scanned_package"] = package_name
            if installed_version:
                finding["osv_scanned_version"] = installed_version
            finding["scanner_context_schema"] = VERSION
        enriched.append(finding)
    output["findings"] = runners.redact_payload(enriched)
    output["scanner_context_schema"] = VERSION
    return output


def install_osv_scanner_context_patch() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners

    current_parser = runners._osv_findings
    if not getattr(current_parser, _PARSER_MARKER, False):
        @wraps(current_parser)
        def parser_with_context(payload):
            return parse_osv_findings_with_context(payload)

        setattr(parser_with_context, _PARSER_MARKER, True)
        setattr(parser_with_context, "_nico_previous", current_parser)
        runners._osv_findings = parser_with_context

    current_fallback = runners._osv_api_fallback_tool
    if not getattr(current_fallback, _FALLBACK_MARKER, False):
        @wraps(current_fallback)
        def fallback_with_context(spec, repo_dir):
            return _enrich_fallback_result(
                current_fallback(spec, repo_dir),
                repo_dir,
                runners,
            )

        setattr(fallback_with_context, _FALLBACK_MARKER, True)
        setattr(fallback_with_context, "_nico_previous", current_fallback)
        runners._osv_api_fallback_tool = fallback_with_context

    return {
        "status": "installed",
        "version": VERSION,
        "parser_bound": getattr(runners._osv_findings, _PARSER_MARKER, False),
        "fallback_bound": getattr(
            runners._osv_api_fallback_tool,
            _FALLBACK_MARKER,
            False,
        ),
        "preserves_scanned_package_identity": True,
        "preserves_installed_version": True,
        "preserves_manifest_path": True,
    }


__all__ = [
    "VERSION",
    "install_osv_scanner_context_patch",
    "parse_osv_findings_with_context",
]
