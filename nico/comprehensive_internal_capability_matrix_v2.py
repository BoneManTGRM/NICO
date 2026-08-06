from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from nico.comprehensive_internal_capability_matrix_v1 import (
    PRODUCTION_FAILURE_ROOT_CAUSE,
    VERSION as HISTORICAL_VERSION,
    capability_matrix as historical_capability_matrix,
    validate_capability_matrix as validate_historical_capability_matrix,
)

VERSION = "nico.comprehensive_internal_capability_matrix.v2"
QUALIFIED_MAIN_SHA = "3088a04012a9068cbd6a0026953733ea2b0bf844"

QUALIFIED_DEPLOYMENT_IDENTITY: dict[str, Any] = {
    "commit_sha": QUALIFIED_MAIN_SHA,
    "origin_pull_request": 1102,
    "provider_statuses": {
        "railway": "success",
        "vercel": "success",
    },
    "workflow_runs": {
        "Unified Production Acceptance": "21009616709",
        "Mobile Restart Production Proof": "21009616706",
        "iOS WebKit Paint Proof": "21009616704",
        "File list guard": "21009616705",
    },
    "report_surfaces_required": ("json", "pdf", "html", "markdown"),
    "human_review_required": True,
    "client_delivery_allowed": False,
}

_REPAIRED_OPERATIONAL_CAPABILITIES = frozenset(
    {
        "evidence_reconciliation",
        "operational_workflow_deployment_analysis",
        "canonical_json",
        "pdf_report",
        "html_report",
        "markdown_report",
        "browser_mobile_operation",
        "restart_recovery",
    }
)

_CURRENT_SOURCE_PATH_OVERRIDES: dict[str, tuple[str, ...]] = {
    "operational_workflow_deployment_analysis": (
        "nico/comprehensive_human_review_package_cleanup_v1.py",
        "nico/snapshot_repository_evidence.py",
    ),
}
_CURRENT_ENTRY_POINT_OVERRIDES: dict[str, tuple[str, ...]] = {
    "operational_workflow_deployment_analysis": ("build_ci_operational_stage",),
}

_DEPENDENCY_PATH_PREFIXES: tuple[tuple[str, int], ...] = (
    ("nico/client_readiness_evidence_intake.py", 1085),
    ("nico/strategic_human_evidence_binding_v1.py", 1085),
    ("tests/test_client_readiness_evidence_intake.py", 1085),
    ("nico/client_readiness_candidate_triage.py", 1086),
    ("tests/test_client_readiness_candidate_triage.py", 1086),
    ("nico/client_readiness_finding_disposition.py", 1087),
    ("tests/test_client_readiness_finding_disposition.py", 1087),
    ("nico/client_readiness_exact_artifact_approval", 1089),
    ("nico/client_readiness_approved_delivery.py", 1089),
    ("nico/comprehensive_approved_delivery_v1.py", 1089),
    ("nico/comprehensive_review_decision_v1.py", 1089),
    ("tests/test_client_readiness_exact_artifact_approval.py", 1089),
    ("tests/test_comprehensive_review_decision_v1.py", 1089),
)


def _root(repo_root: str | Path | None) -> Path:
    if repo_root is not None:
        return Path(repo_root).resolve()
    return Path(__file__).resolve().parents[1]


def _dependency_issues(paths: list[str]) -> list[int]:
    issues: set[int] = set()
    for path in paths:
        for prefix, issue in _DEPENDENCY_PATH_PREFIXES:
            if path.startswith(prefix):
                issues.add(issue)
    return sorted(issues)


def current_capability_matrix(
    repo_root: str | Path | None = None,
) -> list[dict[str, Any]]:
    """Reconcile the historical 40-capability inventory to qualified main.

    The v1 artifact remains an immutable record of the production failure boundary
    that initiated Packages 1 and 2. This v2 view classifies every referenced source
    path against the exact qualified repository tree and never promotes absent later
    packages or external human evidence to an operational state.
    """

    root = _root(repo_root)
    reconciled: list[dict[str, Any]] = []

    for historical in historical_capability_matrix():
        item = deepcopy(historical)
        capability_id = str(item["capability_id"])
        historical_source_paths = [
            str(path) for path in item.get("source_paths") or []
        ]
        historical_entry_points = [
            str(value) for value in item.get("entry_points") or []
        ]
        source_paths = list(
            _CURRENT_SOURCE_PATH_OVERRIDES.get(
                capability_id,
                tuple(historical_source_paths),
            )
        )
        entry_points = list(
            _CURRENT_ENTRY_POINT_OVERRIDES.get(
                capability_id,
                tuple(historical_entry_points),
            )
        )
        item["historical_source_paths"] = historical_source_paths
        item["historical_entry_points"] = historical_entry_points
        item["source_paths"] = source_paths
        item["entry_points"] = entry_points
        existing = [path for path in source_paths if (root / path).is_file()]
        missing = [path for path in source_paths if path not in existing]

        historical_status = str(item.get("current_status") or "")
        historical_failures = [str(value) for value in item.get("known_failures") or []]
        item["historical_status"] = historical_status
        item["historical_known_failures"] = historical_failures
        item["existing_source_paths"] = existing
        item["missing_source_paths"] = missing
        item["dependency_issues"] = _dependency_issues(missing)
        item["qualified_commit_sha"] = QUALIFIED_MAIN_SHA

        if not missing:
            implementation_state = "fully_present"
        elif existing:
            implementation_state = "partially_present"
        else:
            implementation_state = "not_present"
        item["implementation_state"] = implementation_state

        if capability_id in _REPAIRED_OPERATIONAL_CAPABILITIES and not missing:
            item["current_status"] = "production_qualified_at_exact_sha"
            item["resolved_historical_failures"] = historical_failures
            item["known_failures"] = []
        elif missing:
            item["current_status"] = (
                "partially_present_dependency_pending"
                if existing
                else "dependency_package_pending"
            )
            item["known_failures"] = [
                "one or more mapped source paths are absent from qualified main"
            ]
        elif item.get("external_evidence_dependencies"):
            item["current_status"] = "external_evidence_limited"
            item["known_failures"] = []
        elif historical_status == "operational":
            item["current_status"] = "operational"
            item["known_failures"] = []
        else:
            item["current_status"] = "present_unqualified"

        reconciled.append(item)

    return reconciled


def completion_state(repo_root: str | Path | None = None) -> dict[str, Any]:
    matrix = current_capability_matrix(repo_root)
    fully_present = sum(item["implementation_state"] == "fully_present" for item in matrix)
    partial = sum(item["implementation_state"] == "partially_present" for item in matrix)
    absent = sum(item["implementation_state"] == "not_present" for item in matrix)
    pending_issues = sorted(
        {
            int(issue)
            for item in matrix
            for issue in item.get("dependency_issues") or []
        }
    )
    return {
        "artifact_schema": VERSION,
        "historical_artifact_schema": HISTORICAL_VERSION,
        "qualified_main": deepcopy(QUALIFIED_DEPLOYMENT_IDENTITY),
        "capability_count": len(matrix),
        "implementation_counts": {
            "fully_present": fully_present,
            "partially_present": partial,
            "not_present": absent,
        },
        "pending_dependency_issues": pending_issues,
        "capabilities": matrix,
        "historical_failure_record": deepcopy(PRODUCTION_FAILURE_ROOT_CAUSE),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def validate_current_capability_matrix(
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    root = _root(repo_root)
    matrix = current_capability_matrix(root)
    errors: list[str] = []

    historical_validation = validate_historical_capability_matrix()
    if historical_validation.get("status") != "valid":
        errors.append("historical_matrix_invalid")
    if len(matrix) != 40:
        errors.append(f"capability_count:{len(matrix)}!=40")

    ids = [str(item.get("capability_id") or "") for item in matrix]
    if len(set(ids)) != len(ids):
        errors.append("duplicate_capability_ids")

    for item in matrix:
        capability_id = str(item.get("capability_id") or "")
        source_paths = [str(path) for path in item.get("source_paths") or []]
        existing = [str(path) for path in item.get("existing_source_paths") or []]
        missing = [str(path) for path in item.get("missing_source_paths") or []]

        if sorted(source_paths) != sorted(existing + missing):
            errors.append(f"path_classification_mismatch:{capability_id}")
        if any(not (root / path).is_file() for path in existing):
            errors.append(f"existing_path_missing:{capability_id}")
        if any((root / path).is_file() for path in missing):
            errors.append(f"missing_path_exists:{capability_id}")
        if missing and item.get("current_status") in {
            "operational",
            "production_qualified_at_exact_sha",
        }:
            errors.append(f"absent_source_promoted:{capability_id}")
        if (
            capability_id in _REPAIRED_OPERATIONAL_CAPABILITIES
            and not missing
            and item.get("current_status") != "production_qualified_at_exact_sha"
        ):
            errors.append(f"repaired_capability_not_qualified:{capability_id}")
        if (
            capability_id in _REPAIRED_OPERATIONAL_CAPABILITIES
            and item.get("current_status") == "production_qualified_at_exact_sha"
            and item.get("known_failures")
        ):
            errors.append(f"resolved_failure_still_active:{capability_id}")

    return {
        "artifact_schema": VERSION,
        "status": "valid" if not errors else "invalid",
        "validation_errors": errors,
        "qualified_main_sha": QUALIFIED_MAIN_SHA,
        "capability_count": len(matrix),
        "capability_ids": ids,
        "historical_matrix_status": historical_validation.get("status"),
        "deployment_identity": deepcopy(QUALIFIED_DEPLOYMENT_IDENTITY),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "QUALIFIED_DEPLOYMENT_IDENTITY",
    "QUALIFIED_MAIN_SHA",
    "VERSION",
    "completion_state",
    "current_capability_matrix",
    "validate_current_capability_matrix",
]
