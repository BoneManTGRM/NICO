from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any, Mapping

VERSION = "nico.dependency-materiality.v1"

_NON_PRODUCTION_PARTS = {
    "test",
    "tests",
    "fixture",
    "fixtures",
    "example",
    "examples",
    "sample",
    "samples",
    "generated",
    "vendor",
    "vendors",
    "dist",
    "build",
    "coverage",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _values(value: Any) -> list[str]:
    if isinstance(value, str):
        return [_text(value)] if _text(value) else []
    if isinstance(value, (list, tuple, set)):
        return [_text(item) for item in value if _text(item)]
    return []


def _package_context(finding: Mapping[str, Any]) -> tuple[str, str, str]:
    package_value = finding.get("package")
    package = ""
    installed = ""
    ecosystem = ""
    if isinstance(package_value, Mapping):
        package = _text(package_value.get("name"))
        installed = _text(package_value.get("version"))
        ecosystem = _text(package_value.get("ecosystem"))
    elif package_value is not None:
        package = _text(package_value)

    package = package or _text(
        finding.get("package_name")
        or finding.get("dependency")
        or finding.get("module_name")
        or finding.get("name")
    )
    installed = installed or _text(
        finding.get("installed_version")
        or finding.get("current_version")
        or finding.get("resolved_version")
        or finding.get("version")
    )
    ecosystem = ecosystem or _text(finding.get("ecosystem"))
    return package, installed, ecosystem


def _advisory_ids(finding: Mapping[str, Any]) -> list[str]:
    identifiers: list[str] = []
    for key in ("advisory_id", "vulnerability_id", "id"):
        value = _text(finding.get(key))
        if value:
            identifiers.append(value)
    identifiers.extend(_values(finding.get("advisory_ids")))
    identifiers.extend(_values(finding.get("aliases")))

    via = finding.get("via")
    for item in via if isinstance(via, list) else []:
        if isinstance(item, Mapping):
            for key in ("source", "url", "name"):
                value = _text(item.get(key))
                if value:
                    identifiers.append(value)
        elif _text(item):
            identifiers.append(_text(item))
    return list(dict.fromkeys(identifiers))


def _fixed_versions(finding: Mapping[str, Any]) -> list[str]:
    versions: list[str] = []
    for key in ("fixed_versions", "fix_versions"):
        versions.extend(_values(finding.get(key)))
    for key in ("fixed_version", "patched_version", "fixed"):
        value = _text(finding.get(key))
        if value:
            versions.append(value)

    affected = finding.get("affected")
    for affected_item in affected if isinstance(affected, list) else []:
        if not isinstance(affected_item, Mapping):
            continue
        ranges = affected_item.get("ranges")
        for range_item in ranges if isinstance(ranges, list) else []:
            if not isinstance(range_item, Mapping):
                continue
            events = range_item.get("events")
            for event in events if isinstance(events, list) else []:
                if isinstance(event, Mapping) and _text(event.get("fixed")):
                    versions.append(_text(event.get("fixed")))
    return list(dict.fromkeys(versions))


def _dependency_path(finding: Mapping[str, Any]) -> str:
    for key in (
        "dependency_path",
        "source_path",
        "manifest",
        "lockfile",
        "path",
        "file_path",
        "filename",
        "filePath",
    ):
        value = finding.get(key)
        if isinstance(value, Mapping):
            value = value.get("path")
        text = _text(value)
        if text:
            return text.replace("\\", "/")
    source = finding.get("source")
    if isinstance(source, Mapping) and _text(source.get("path")):
        return _text(source.get("path")).replace("\\", "/")
    return ""


def _scope(finding: Mapping[str, Any], path: str) -> tuple[str, bool, bool]:
    if finding.get("production_relevant") is True or finding.get("production") is True:
        return "production", True, True
    if finding.get("production_relevant") is False or finding.get("production") is False:
        return "non_production", False, True
    if finding.get("dev") is True or finding.get("development") is True:
        return "development", False, True

    explicit = _text(
        finding.get("scope")
        or finding.get("environment")
        or finding.get("dependency_scope")
    ).casefold().replace("-", "_").replace(" ", "_")
    if explicit in {"production", "runtime", "prod"}:
        return "production", True, True
    if explicit in {
        "test",
        "tests",
        "testing",
        "development",
        "dev",
        "optional",
        "build",
        "non_production",
    }:
        return explicit, False, True

    parts = {part.casefold() for part in Path(path).parts}
    if parts & _NON_PRODUCTION_PARTS:
        return "non_production", False, True
    return "unknown", False, False


def _reachability(finding: Mapping[str, Any]) -> tuple[str, bool, bool]:
    if finding.get("reachable") is True:
        return "reachable", True, True
    if finding.get("reachable") is False:
        return "unreachable", False, True
    explicit = _text(finding.get("reachability")).casefold().replace("-", "_").replace(" ", "_")
    if explicit in {"reachable", "verified", "confirmed", "true"}:
        return "reachable", True, True
    if explicit in {"unreachable", "not_reachable", "false"}:
        return "unreachable", False, True
    return "unknown", False, False


def _severity(finding: Mapping[str, Any]) -> str:
    values = [
        finding.get("severity"),
        finding.get("issue_severity"),
        finding.get("level"),
        finding.get("max_severity"),
    ]
    database_specific = finding.get("database_specific")
    if isinstance(database_specific, Mapping):
        values.append(database_specific.get("severity"))
    text = " ".join(_text(value).casefold() for value in values)
    if "critical" in text:
        return "critical"
    if "high" in text or "error" in text:
        return "high"
    if "moderate" in text or "medium" in text or "warning" in text:
        return "medium"
    if "low" in text or "info" in text:
        return "low"
    return "unknown"


def classify_dependency_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    """Classify one dependency candidate without converting uncertainty into a defect.

    A finding is technically material only when its advisory identity, affected package
    and installed version, remediation version, dependency path, production scope, and
    reachability are all verified. Everything else remains visible as assurance-limited
    triage evidence. Explicitly unreachable or non-production records are retained as
    verified non-material observations.
    """

    source = deepcopy(dict(finding))
    package, installed, ecosystem = _package_context(source)
    advisory_ids = _advisory_ids(source)
    fixed_versions = _fixed_versions(source)
    path = _dependency_path(source)
    scope, production, scope_verified = _scope(source, path)
    reachability, reachable, reachability_verified = _reachability(source)

    required = {
        "advisory_id": bool(advisory_ids),
        "package": bool(package),
        "installed_version": bool(installed),
        "fixed_version": bool(fixed_versions),
        "dependency_path": bool(path),
        "production_scope": bool(scope_verified and production),
        "reachability": bool(reachability_verified and reachable),
    }
    verified_material = all(required.values())
    verified_non_material = bool(
        (scope_verified and not production)
        or (reachability_verified and not reachable)
    )

    if verified_material:
        disposition = "verified_material"
        impact = "material"
        reason = (
            "The advisory is bound to an installed production dependency with a retained "
            "dependency path, fixed version, and verified reachable execution path."
        )
    elif verified_non_material:
        disposition = "verified_non_material"
        impact = "none"
        reason = (
            "The advisory remains in the evidence ledger but verified scope or reachability "
            "shows it is not a current production-impacting defect."
        )
    else:
        disposition = "triage_required"
        impact = "assurance_only"
        reason = (
            "The scanner candidate is retained for human review but is not scored as a "
            "confirmed production defect until all materiality fields are verified."
        )

    normalized = {
        **source,
        "dependency_materiality_version": VERSION,
        "advisory_ids": advisory_ids,
        "advisory_id": advisory_ids[0] if advisory_ids else "",
        "package": package,
        "installed_version": installed,
        "ecosystem": ecosystem,
        "fixed_versions": fixed_versions,
        "fixed_version": fixed_versions[0] if fixed_versions else "",
        "dependency_path": path,
        "severity": _severity(source),
        "scope": scope,
        "production_relevant": production if scope_verified else None,
        "reachability": reachability,
        "reachable": reachable if reachability_verified else None,
        "disposition": disposition,
        "material": verified_material,
        "review_required": disposition == "triage_required",
        "technical_score_impact": impact,
        "missing_disposition_fields": [key for key, present in required.items() if not present],
        "materiality_reason": reason,
    }
    normalized["dependency_fingerprint"] = hashlib.sha256(
        json.dumps(
            {
                "advisory_ids": advisory_ids,
                "package": package,
                "installed_version": installed,
                "dependency_path": path,
                "scope": scope,
                "reachability": reachability,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    return normalized


def is_non_production_dependency(finding: Mapping[str, Any]) -> bool:
    classified = classify_dependency_finding(finding)
    return classified.get("disposition") == "verified_non_material" and classified.get("scope") != "production"


__all__ = [
    "VERSION",
    "classify_dependency_finding",
    "is_non_production_dependency",
]
