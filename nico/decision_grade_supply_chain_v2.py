from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath
from typing import Any

VERSION = "nico.decision_grade_supply_chain.v2"

_MANIFESTS = {
    "package.json": "npm",
    "requirements.txt": "pypi",
    "pyproject.toml": "pypi",
}
_LOCKFILES = {
    "package-lock.json": "npm",
    "npm-shrinkwrap.json": "npm",
    "pnpm-lock.yaml": "npm",
    "yarn.lock": "npm",
    "poetry.lock": "pypi",
    "Pipfile.lock": "pypi",
    "uv.lock": "pypi",
}


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _parse_package_json(path: str, text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except (TypeError, ValueError):
        return []
    output: list[dict[str, Any]] = []
    for scope in ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies"):
        values = payload.get(scope)
        if not isinstance(values, dict):
            continue
        for name, version in sorted(values.items()):
            output.append({
                "name": str(name),
                "version_constraint": str(version),
                "ecosystem": "npm",
                "scope": scope,
                "source_path": path,
            })
    return output


def _parse_requirements(path: str, text: str) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or line.startswith(("-r", "--")):
            continue
        marker_free = line.split(";", 1)[0].strip()
        name = marker_free
        version = ""
        for token in ("===", "==", ">=", "<=", "~=", "!=", ">", "<"):
            if token in marker_free:
                name, version = marker_free.split(token, 1)
                version = token + version
                break
        name = name.split("[", 1)[0].strip()
        if name:
            output.append({
                "name": name,
                "version_constraint": version,
                "ecosystem": "pypi",
                "scope": "runtime",
                "source_path": path,
            })
    return output


def build_supply_chain_package(files: dict[str, str], *, repository: str = "", commit_sha: str = "") -> dict[str, Any]:
    """Build deterministic inventory, SBOM, license, lockfile, and digest evidence.

    This function does not claim vulnerability or license conclusions that are not
    present in the supplied immutable file set.
    """
    normalized = {str(path).replace("\\", "/"): str(content) for path, content in files.items()}
    components: list[dict[str, Any]] = []
    manifests: list[dict[str, str]] = []
    lockfiles: list[dict[str, str]] = []

    for path in sorted(normalized):
        name = PurePosixPath(path).name
        content = normalized[path]
        if name in _MANIFESTS:
            manifests.append({"path": path, "ecosystem": _MANIFESTS[name], "sha256": _sha256(content)})
            if name == "package.json":
                components.extend(_parse_package_json(path, content))
            elif name == "requirements.txt":
                components.extend(_parse_requirements(path, content))
        if name in _LOCKFILES:
            lockfiles.append({"path": path, "ecosystem": _LOCKFILES[name], "sha256": _sha256(content)})

    deduped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for item in components:
        key = (item["ecosystem"], item["name"].casefold(), item["version_constraint"], item["scope"])
        deduped[key] = item
    components = [deduped[key] for key in sorted(deduped)]

    manifest_ecosystems = sorted({item["ecosystem"] for item in manifests})
    lock_ecosystems = sorted({item["ecosystem"] for item in lockfiles})
    missing_lock_ecosystems = sorted(set(manifest_ecosystems) - set(lock_ecosystems))

    bom_components = [
        {
            "type": "library",
            "name": item["name"],
            "version": item["version_constraint"] or "unresolved",
            "purl": f"pkg:{item['ecosystem']}/{item['name']}" + (f"@{item['version_constraint']}" if item["version_constraint"] else ""),
            "properties": [
                {"name": "nico:scope", "value": item["scope"]},
                {"name": "nico:source_path", "value": item["source_path"]},
            ],
        }
        for item in components
    ]
    sbom = {
        "bomFormat": "CycloneDX",
        "specVersion": "1.5",
        "version": 1,
        "metadata": {
            "component": {"type": "application", "name": repository or "repository", "version": commit_sha or "unbound"},
            "properties": [{"name": "nico:artifact_schema", "value": VERSION}],
        },
        "components": bom_components,
    }
    canonical = json.dumps(sbom, sort_keys=True, separators=(",", ":"))

    return {
        "artifact_schema": VERSION,
        "repository": repository,
        "commit_sha": commit_sha,
        "dependency_inventory": components,
        "manifest_register": manifests,
        "lockfile_register": lockfiles,
        "lockfile_completeness": {
            "manifest_ecosystems": manifest_ecosystems,
            "lockfile_ecosystems": lock_ecosystems,
            "missing_lockfile_ecosystems": missing_lock_ecosystems,
            "complete": not missing_lock_ecosystems,
        },
        "cyclonedx_sbom": sbom,
        "license_register": [
            {
                "component": item["name"],
                "ecosystem": item["ecosystem"],
                "license": "UNKNOWN",
                "status": "not_assessed",
            }
            for item in components
        ],
        "vulnerability_register": [],
        "limitations": [
            "License identities require authoritative package metadata or retained scanner evidence.",
            "An empty vulnerability register means no vulnerability evidence was supplied to this builder; it does not prove absence of vulnerabilities.",
        ],
        "hashes": {
            "cyclonedx_sbom_sha256": _sha256(canonical),
            "input_file_set_sha256": _sha256(json.dumps({path: _sha256(normalized[path]) for path in sorted(normalized)}, sort_keys=True, separators=(",", ":"))),
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "build_supply_chain_package"]
