from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.decision_grade_accepted_edition_guard_v1 import (
    guard_report_package_accepted_edition,
)
from nico.decision_grade_supply_chain_v2 import (
    VERSION as SUPPLY_CHAIN_VERSION,
    build_supply_chain_package,
)

VERSION = "nico.decision_grade_supply_chain_binding.v4"
_MARKER = "__nico_decision_grade_supply_chain_binding_v4__"


def _source_files(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, str]:
    for key in ("source_files", "repository_files", "files"):
        value = kwargs.get(key)
        if isinstance(value, dict) and all(isinstance(path, str) for path in value):
            return {str(path): str(content) for path, content in value.items()}

    stages = kwargs.get("stage_results")
    if isinstance(stages, dict):
        for stage_name in (
            "repository_and_delivery_evidence",
            "immutable_repository_snapshot",
        ):
            stage = stages.get(stage_name)
            if not isinstance(stage, dict):
                continue
            for key in (
                "source_files",
                "repository_files",
                "files",
                "snapshot_files",
            ):
                value = stage.get(key)
                if isinstance(value, dict) and all(
                    isinstance(path, str) for path in value
                ):
                    return {str(path): str(content) for path, content in value.items()}
    return {}


def _identity(
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    result: dict[str, Any],
) -> tuple[str, str]:
    identity = kwargs.get("identity")
    if not isinstance(identity, dict):
        identity = (
            result.get("identity")
            if isinstance(result.get("identity"), dict)
            else {}
        )
    package = result.get("report_package")
    canonical = (
        package.get("json")
        if isinstance(package, dict) and isinstance(package.get("json"), dict)
        else {}
    )
    canonical_identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), dict)
        else {}
    )
    repository = str(
        kwargs.get("repository")
        or identity.get("repository")
        or result.get("repository")
        or canonical_identity.get("repository")
        or ""
    )
    commit_sha = str(
        kwargs.get("commit_sha")
        or identity.get("commit_sha")
        or result.get("commit_sha")
        or canonical_identity.get("commit_sha")
        or ""
    )
    return repository, commit_sha


def wrap_report_builder_with_supply_chain(
    delegate: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    if getattr(delegate, _MARKER, False):
        return delegate

    @wraps(delegate)
    def wrapped(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = delegate(*args, **kwargs)
        if not isinstance(result, dict):
            return result

        files = _source_files(args, kwargs)
        repository, commit_sha = _identity(args, kwargs, result)
        if files:
            evidence = build_supply_chain_package(
                files,
                repository=repository,
                commit_sha=commit_sha,
            )
            evidence["sbom"] = evidence.get("cyclonedx_sbom") or {}
            status = "complete"
        else:
            evidence = {
                "artifact_schema": SUPPLY_CHAIN_VERSION,
                "repository": repository,
                "commit_sha": commit_sha,
                "status": "not_assessed",
                "dependency_inventory": [],
                "manifest_register": [],
                "lockfile_register": [],
                "license_register": [],
                "vulnerability_register": [],
                "cyclonedx_sbom": {},
                "sbom": {},
                "limitations": [
                    "Immutable repository file content was not retained at the report boundary, so the supply-chain package was not generated."
                ],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            status = "not_assessed"

        result["supply_chain_evidence"] = evidence
        package = result.get("report_package")
        if isinstance(package, dict):
            package["supply_chain_evidence"] = evidence
            canonical = package.get("json")
            if isinstance(canonical, dict):
                canonical["supply_chain_evidence"] = evidence
            quality = (
                package.get("report_quality_contract")
                if isinstance(package.get("report_quality_contract"), dict)
                else package.get("quality")
                if isinstance(package.get("quality"), dict)
                else {}
            )
            quality.update(
                {
                    "decision_grade_supply_chain_binding_version": VERSION,
                    "decision_grade_supply_chain_version": SUPPLY_CHAIN_VERSION,
                    "supply_chain_status": status,
                    "supply_chain_repository_identity_present": bool(repository),
                    "supply_chain_commit_identity_present": bool(commit_sha),
                    "supply_chain_human_review_required": True,
                    "supply_chain_client_delivery_allowed": False,
                }
            )
            package["report_quality_contract"] = quality
            package["quality"] = quality
            guard_report_package_accepted_edition(package)
        return result

    setattr(wrapped, _MARKER, True)
    return wrapped


__all__ = ["VERSION", "wrap_report_builder_with_supply_chain"]
