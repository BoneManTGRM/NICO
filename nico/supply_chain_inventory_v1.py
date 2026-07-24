from __future__ import annotations

import csv
import io
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

VERSION = "nico.supply_chain_inventory.v1"
MAX_COMPONENTS = 5000


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 3)].rstrip() + "..."


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _safe_name(value: Any) -> str:
    return re.sub(r"[^A-Za-z0-9_.@/+-]+", "-", _text(value, 300)).strip("-")


def _ecosystem(value: Any, source: str = "") -> str:
    raw = _text(value, 60).casefold()
    source_lower = source.casefold()
    if raw in {"pypi", "python", "pip"} or "requirements" in source_lower or "pyproject" in source_lower:
        return "PyPI"
    if raw in {"npm", "node", "javascript", "typescript"} or "package-lock" in source_lower or "package.json" in source_lower:
        return "npm"
    if raw in {"maven", "gradle", "java"}:
        return "Maven"
    if raw in {"nuget", "dotnet"}:
        return "NuGet"
    if raw in {"cargo", "crates.io", "rust"}:
        return "Cargo"
    if raw in {"go", "golang"}:
        return "Go"
    return _text(value, 60) or "unknown"


def _purl(ecosystem: str, name: str, version: str) -> str:
    namespace_name = name.lstrip("@")
    if ecosystem == "npm":
        return f"pkg:npm/{namespace_name}@{version}" if version else f"pkg:npm/{namespace_name}"
    if ecosystem == "PyPI":
        normalized = namespace_name.replace("_", "-").casefold()
        return f"pkg:pypi/{normalized}@{version}" if version else f"pkg:pypi/{normalized}"
    normalized = namespace_name.replace(" ", "-")
    return f"pkg:generic/{normalized}@{version}" if version else f"pkg:generic/{normalized}"


def _license_value(item: dict[str, Any]) -> tuple[str, str]:
    candidates = (
        item.get("license"),
        item.get("license_id"),
        item.get("license_name"),
        _record(item.get("licenses")).get("expression"),
    )
    for candidate in candidates:
        value = _text(candidate, 240)
        if value:
            return value, "declared"
    licenses = item.get("licenses")
    if isinstance(licenses, list):
        values: list[str] = []
        for license_item in licenses:
            if isinstance(license_item, dict):
                value = _text(license_item.get("license") or license_item.get("id") or license_item.get("name"), 160)
            else:
                value = _text(license_item, 160)
            if value:
                values.append(value)
        if values:
            return " OR ".join(sorted(set(values))), "declared"
    return "UNKNOWN", "not_retained"


def _component_candidate(item: dict[str, Any], *, source: str, default_ecosystem: str = "") -> dict[str, Any] | None:
    name = _safe_name(
        item.get("name")
        or item.get("package")
        or item.get("package_name")
        or item.get("dependency")
        or item.get("module")
    )
    version = _text(
        item.get("version")
        or item.get("installed_version")
        or item.get("current_version")
        or item.get("resolved_version"),
        120,
    )
    if not name:
        return None
    ecosystem = _ecosystem(item.get("ecosystem") or default_ecosystem, source)
    license_value, license_evidence = _license_value(item)
    direct_value = item.get("direct")
    if direct_value is None:
        relationship = _text(item.get("relationship") or item.get("dependency_type"), 80).casefold()
        direct_value = relationship in {"direct", "root", "production", "development"} if relationship else None
    vulnerabilities = _records(item.get("vulnerabilities") or item.get("vulns") or item.get("advisories"))
    return {
        "type": "library",
        "name": name,
        "version": version,
        "ecosystem": ecosystem,
        "purl": _purl(ecosystem, name, version),
        "scope": _text(item.get("scope") or item.get("dependency_group"), 80) or "unknown",
        "direct": direct_value if isinstance(direct_value, bool) else None,
        "license": license_value,
        "license_evidence": license_evidence,
        "source_reference": source,
        "vulnerabilities": vulnerabilities,
        "vulnerability_count": len(vulnerabilities),
        "latest_version": _text(item.get("latest_version") or item.get("available_version"), 120),
        "deprecated": bool(item.get("deprecated") or item.get("abandoned")),
        "metadata_confidence": "high" if version and ecosystem != "unknown" else "review_limited",
    }


def _walk_dependencies(value: Any, *, source: str, default_ecosystem: str = "", depth: int = 0) -> list[dict[str, Any]]:
    if depth > 6:
        return []
    output: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value[:MAX_COMPONENTS]:
            output.extend(_walk_dependencies(item, source=source, default_ecosystem=default_ecosystem, depth=depth + 1))
        return output
    if not isinstance(value, dict):
        return output

    candidate = _component_candidate(value, source=source, default_ecosystem=default_ecosystem)
    if candidate:
        output.append(candidate)

    for key, nested in value.items():
        key_lower = str(key).casefold()
        if key_lower in {
            "dependencies", "packages", "components", "libraries", "requirements",
            "production_dependencies", "development_dependencies", "resolved_dependencies",
        }:
            nested_source = f"{source}:{key}"
            if isinstance(nested, dict):
                for package_name, package_value in list(nested.items())[:MAX_COMPONENTS]:
                    if isinstance(package_value, dict):
                        item = {"name": package_name, **package_value}
                    else:
                        item = {"name": package_name, "version": package_value}
                    output.extend(_walk_dependencies(item, source=nested_source, default_ecosystem=default_ecosystem, depth=depth + 1))
            else:
                output.extend(_walk_dependencies(nested, source=nested_source, default_ecosystem=default_ecosystem, depth=depth + 1))
    return output


def _stage_dependency_sources(stage_results: dict[str, Any]) -> list[tuple[str, Any, str]]:
    sources: list[tuple[str, Any, str]] = []
    for stage_id, stage_value in stage_results.items():
        stage = _record(stage_value)
        if not stage:
            continue
        for key in (
            "dependency_evidence", "dependencies", "dependency_inventory", "sbom",
            "scanner", "scanner_evidence", "scanner_results", "evidence",
        ):
            value = stage.get(key)
            if value in (None, "", [], {}):
                continue
            default_ecosystem = ""
            if "python" in key.casefold() or "pip" in key.casefold():
                default_ecosystem = "PyPI"
            elif "npm" in key.casefold() or "node" in key.casefold():
                default_ecosystem = "npm"
            sources.append((f"{stage_id}.{key}", value, default_ecosystem))
    return sources


def build_supply_chain_inventory(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, Any],
    assessment: dict[str, Any] | None = None,
) -> dict[str, Any]:
    components: dict[tuple[str, str, str], dict[str, Any]] = {}
    for source, value, default_ecosystem in _stage_dependency_sources(stage_results):
        for candidate in _walk_dependencies(value, source=source, default_ecosystem=default_ecosystem):
            key = (candidate["ecosystem"], candidate["name"].casefold(), candidate["version"])
            existing = components.get(key)
            if not existing:
                components[key] = candidate
                continue
            existing["vulnerabilities"] = existing.get("vulnerabilities") or candidate.get("vulnerabilities") or []
            existing["vulnerability_count"] = max(int(existing.get("vulnerability_count") or 0), int(candidate.get("vulnerability_count") or 0))
            if existing.get("license") == "UNKNOWN" and candidate.get("license") != "UNKNOWN":
                existing["license"] = candidate["license"]
                existing["license_evidence"] = candidate["license_evidence"]
            sources = sorted(set(_text(existing.get("source_reference"), 1000).split(" | ") + [_text(candidate.get("source_reference"), 1000)]))
            existing["source_reference"] = " | ".join(item for item in sources if item)

    # Retain explicit dependency findings even when the exact component inventory was unavailable.
    assessment_record = _record(assessment)
    for finding in _records(assessment_record.get("findings_register")):
        if _text(finding.get("category"), 60).casefold() != "dependency":
            continue
        candidate = _component_candidate(
            {
                "name": finding.get("package") or finding.get("title"),
                "version": finding.get("installed_version"),
                "ecosystem": finding.get("ecosystem"),
                "vulnerabilities": [finding],
            },
            source=_text(finding.get("location") or "assessment.findings_register", 500),
        )
        if candidate:
            key = (candidate["ecosystem"], candidate["name"].casefold(), candidate["version"])
            components.setdefault(key, candidate)

    ordered = sorted(components.values(), key=lambda item: (item["ecosystem"], item["name"].casefold(), item["version"]))[:MAX_COMPONENTS]
    unknown_license = [item for item in ordered if item["license"] == "UNKNOWN"]
    vulnerable = [item for item in ordered if int(item.get("vulnerability_count") or 0) > 0]
    deprecated = [item for item in ordered if item.get("deprecated") is True]
    status = "complete" if ordered and not unknown_license else "review_limited" if ordered else "unavailable"
    return {
        "artifact_schema": VERSION,
        "status": status,
        "repository": _text(identity.get("repository"), 260),
        "commit_sha": _text(identity.get("commit_sha"), 80),
        "run_id": _text(identity.get("run_id"), 180),
        "generated_at": _now(),
        "component_count": len(ordered),
        "components_with_unknown_license": len(unknown_license),
        "components_with_retained_vulnerabilities": len(vulnerable),
        "deprecated_or_abandoned_components": len(deprecated),
        "inventory_truncated": len(components) > MAX_COMPONENTS,
        "components": ordered,
        "license_assurance": "VERIFIED" if ordered and not unknown_license else "REVIEW LIMITED" if ordered else "UNAVAILABLE",
        "guardrail": "License, latest-version, direct/transitive, and vulnerability claims are included only when retained in authorized evidence. Unknown metadata remains UNKNOWN and does not become a clean claim.",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def cyclonedx_sbom(inventory: dict[str, Any]) -> dict[str, Any]:
    return {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "serialNumber": f"urn:uuid:nico-{_text(inventory.get('run_id'), 160)}",
        "version": 1,
        "metadata": {
            "timestamp": inventory.get("generated_at"),
            "tools": {"components": [{"type": "application", "name": "NICO", "version": VERSION}]},
            "component": {
                "type": "application",
                "name": inventory.get("repository") or "authorized-repository",
                "version": inventory.get("commit_sha") or "unknown",
            },
            "properties": [
                {"name": "nico:run_id", "value": inventory.get("run_id") or ""},
                {"name": "nico:evidence_status", "value": inventory.get("status") or "unavailable"},
                {"name": "nico:human_review_required", "value": "true"},
            ],
        },
        "components": [
            {
                "type": item.get("type") or "library",
                "name": item.get("name"),
                "version": item.get("version") or "unknown",
                "purl": item.get("purl"),
                "scope": item.get("scope") if item.get("scope") in {"required", "optional", "excluded"} else None,
                "licenses": ([{"license": {"id": item.get("license")}}] if item.get("license") not in {"", "UNKNOWN", None} else []),
                "properties": [
                    {"name": "nico:ecosystem", "value": item.get("ecosystem") or "unknown"},
                    {"name": "nico:direct", "value": "unknown" if item.get("direct") is None else str(bool(item.get("direct"))).lower()},
                    {"name": "nico:license_evidence", "value": item.get("license_evidence") or "not_retained"},
                    {"name": "nico:source_reference", "value": item.get("source_reference") or ""},
                    {"name": "nico:vulnerability_count", "value": str(item.get("vulnerability_count") or 0)},
                ],
            }
            for item in _records(inventory.get("components"))
        ],
    }


def _csv(rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _text(row.get(field), 5000) for field in fields})
    return buffer.getvalue()


def license_register_csv(inventory: dict[str, Any]) -> str:
    return _csv(
        _records(inventory.get("components")),
        ("ecosystem", "name", "version", "license", "license_evidence", "direct", "scope", "source_reference", "metadata_confidence"),
    )


def upgrade_register_csv(inventory: dict[str, Any]) -> str:
    return _csv(
        _records(inventory.get("components")),
        ("ecosystem", "name", "version", "latest_version", "deprecated", "vulnerability_count", "direct", "source_reference"),
    )


def inventory_json(inventory: dict[str, Any]) -> str:
    return json.dumps(inventory, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sbom_json(inventory: dict[str, Any]) -> str:
    return json.dumps(cyclonedx_sbom(inventory), ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


__all__ = [
    "MAX_COMPONENTS",
    "VERSION",
    "build_supply_chain_inventory",
    "cyclonedx_sbom",
    "inventory_json",
    "license_register_csv",
    "sbom_json",
    "upgrade_register_csv",
]
