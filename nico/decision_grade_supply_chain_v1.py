from __future__ import annotations

import csv
import hashlib
import io
import json
from copy import deepcopy
from typing import Any

VERSION = "nico.decision_grade_supply_chain.v1"


def _text(value: Any, limit: int = 2000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _purl(item: dict[str, Any]) -> str:
    supplied = _text(item.get("purl"), 500)
    if supplied:
        return supplied
    ecosystem = _text(item.get("ecosystem") or item.get("package_manager"), 80).casefold()
    name = _text(item.get("name"), 300)
    version = _text(item.get("version"), 120)
    namespace = _text(item.get("namespace"), 200)
    package_name = f"{namespace}/{name}" if namespace else name
    return f"pkg:{ecosystem or 'generic'}/{package_name}@{version}" if name and version else ""


def normalize_dependency(item: dict[str, Any]) -> dict[str, Any]:
    name = _text(item.get("name"), 300)
    version = _text(item.get("version"), 120)
    direct = bool(item.get("direct") is True or str(item.get("dependency_type") or "").casefold() == "direct")
    vulnerabilities = _records(item.get("vulnerabilities"))
    unresolved = [v for v in vulnerabilities if str(v.get("status") or "open").casefold() not in {"resolved", "fixed", "accepted"}]
    license_name = _text(item.get("license") or item.get("license_name"), 200)
    evidence_reference = _text(item.get("evidence_reference") or item.get("source_reference"), 700)
    return {
        "name": name,
        "version": version,
        "ecosystem": _text(item.get("ecosystem") or item.get("package_manager"), 80),
        "purl": _purl(item),
        "dependency_type": "direct" if direct else "transitive",
        "scope": _text(item.get("scope") or "runtime", 80),
        "license": license_name or "UNKNOWN",
        "license_evidence_status": "complete" if license_name else "missing",
        "locked": bool(item.get("locked") is True),
        "latest_version": _text(item.get("latest_version"), 120),
        "outdated": bool(item.get("outdated") is True),
        "vulnerabilities": vulnerabilities,
        "unresolved_vulnerability_count": len(unresolved),
        "evidence_reference": evidence_reference,
        "source_manifest": _text(item.get("source_manifest"), 500),
    }


def build_supply_chain_package(
    dependencies: list[dict[str, Any]] | None,
    *,
    repository: str = "",
    commit_sha: str = "",
    scanner_status: str = "complete",
    lockfile_status: str = "complete",
) -> dict[str, Any]:
    normalized = [normalize_dependency(item) for item in _records(dependencies)]
    normalized.sort(key=lambda item: (item["ecosystem"], item["name"], item["version"]))
    duplicate_keys = []
    seen: set[tuple[str, str, str]] = set()
    for item in normalized:
        key = (item["ecosystem"], item["name"], item["version"])
        if key in seen:
            duplicate_keys.append("|".join(key))
        seen.add(key)
    unresolved = sum(int(item["unresolved_vulnerability_count"]) for item in normalized)
    unknown_licenses = sum(item["license"] == "UNKNOWN" for item in normalized)
    unlocked = sum(not item["locked"] for item in normalized)
    outdated = sum(item["outdated"] for item in normalized)
    scanner_complete = scanner_status.casefold() == "complete"
    lock_complete = lockfile_status.casefold() == "complete"
    complete = bool(normalized) and scanner_complete and lock_complete and not duplicate_keys
    return {
        "artifact_schema": VERSION,
        "repository": _text(repository, 300),
        "commit_sha": _text(commit_sha, 80),
        "status": "complete" if complete else "partial",
        "assurance": "VERIFIED" if complete else "REVIEW LIMITED",
        "scanner_status": scanner_status,
        "lockfile_status": lockfile_status,
        "dependency_count": len(normalized),
        "direct_dependency_count": sum(item["dependency_type"] == "direct" for item in normalized),
        "transitive_dependency_count": sum(item["dependency_type"] == "transitive" for item in normalized),
        "unresolved_vulnerability_count": unresolved,
        "unknown_license_count": unknown_licenses,
        "unlocked_dependency_count": unlocked,
        "outdated_dependency_count": outdated,
        "duplicate_component_keys": duplicate_keys,
        "components": normalized,
        "guardrail": (
            "The package reports only observed components and scanner results. Missing lockfiles, incomplete scanners, unknown licenses, "
            "or absent dependency evidence cannot be represented as healthy. This output is not legal advice or compliance certification."
        ),
        "human_review_required": not complete or bool(unresolved or unknown_licenses or unlocked),
        "client_delivery_allowed": False,
    }


def cyclonedx_json(package: dict[str, Any]) -> str:
    components = []
    for item in _records(package.get("components")):
        components.append({
            "type": "library",
            "name": item.get("name"),
            "version": item.get("version"),
            "purl": item.get("purl"),
            "licenses": [{"license": {"name": item.get("license")}}],
            "properties": [
                {"name": "nico:dependency_type", "value": item.get("dependency_type")},
                {"name": "nico:scope", "value": item.get("scope")},
                {"name": "nico:evidence_reference", "value": item.get("evidence_reference")},
            ],
        })
    document = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": package.get("repository"), "version": package.get("commit_sha")},
            "properties": [{"name": "nico:artifact_schema", "value": VERSION}],
        },
        "components": components,
    }
    return json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def license_register_csv(package: dict[str, Any]) -> str:
    fields = ("name", "version", "ecosystem", "dependency_type", "scope", "license", "license_evidence_status", "evidence_reference")
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(_records(package.get("components")))
    return buffer.getvalue()


def vulnerability_register_csv(package: dict[str, Any]) -> str:
    fields = ("component", "version", "vulnerability_id", "severity", "status", "fixed_version", "evidence_reference")
    rows: list[dict[str, Any]] = []
    for item in _records(package.get("components")):
        for vuln in _records(item.get("vulnerabilities")):
            rows.append({
                "component": item.get("name"),
                "version": item.get("version"),
                "vulnerability_id": vuln.get("id") or vuln.get("vulnerability_id"),
                "severity": vuln.get("severity"),
                "status": vuln.get("status") or "open",
                "fixed_version": vuln.get("fixed_version"),
                "evidence_reference": vuln.get("evidence_reference") or item.get("evidence_reference"),
            })
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n", extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buffer.getvalue()


def supply_chain_exports(package: dict[str, Any]) -> dict[str, Any]:
    sbom = cyclonedx_json(package)
    licenses = license_register_csv(package)
    vulnerabilities = vulnerability_register_csv(package)
    return {
        "schema_version": VERSION,
        "package": package,
        "cyclonedx_json": sbom,
        "license_register_csv": licenses,
        "vulnerability_register_csv": vulnerabilities,
        "hashes": {
            "cyclonedx_json_sha256": hashlib.sha256(sbom.encode("utf-8")).hexdigest(),
            "license_register_csv_sha256": hashlib.sha256(licenses.encode("utf-8")).hexdigest(),
            "vulnerability_register_csv_sha256": hashlib.sha256(vulnerabilities.encode("utf-8")).hexdigest(),
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "build_supply_chain_package",
    "cyclonedx_json",
    "license_register_csv",
    "normalize_dependency",
    "supply_chain_exports",
    "vulnerability_register_csv",
]
