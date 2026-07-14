from __future__ import annotations

from collections import defaultdict
from contextvars import ContextVar
from pathlib import PurePosixPath
from typing import Any, Callable

import nico.complexity_artifact_integration as complexity_integration
import nico.hosted_api_complexity_fallback as fallback
import nico.hosted_assessment as hosted


SOURCE_BOOTSTRAP_FILES = 12
MAX_REPORTED_SOURCE_FAILURES = 6
_EXPRESS_PROFILE_ENABLED: ContextVar[bool] = ContextVar(
    "nico_express_api_complexity_profile_enabled",
    default=False,
)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _bounded_error(value: Any, *, limit: int = 180) -> str:
    normalized = " ".join(str(value or "unknown error").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3] + "..."


def select_budget_aware_profile_paths(
    tree_entries: list[dict[str, Any]],
    *,
    max_files: int = hosted.MAX_TEXT_FILES,
    source_reserve: int = fallback.MAX_COMPLEXITY_SOURCE_FILES,
    source_bootstrap: int = SOURCE_BOOTSTRAP_FILES,
) -> list[str]:
    """Put a bounded source bootstrap ahead of manifest-heavy API requests.

    Public or incompletely configured installations can have a small GitHub API
    request budget. Fetching every known manifest first can exhaust that budget
    before any production source is available to the complexity analyzer.
    """

    sizes = {
        str(item.get("path") or ""): _int(item.get("size"))
        for item in tree_entries
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
    }
    known = [path for path in hosted.KNOWN_FILE_PATHS if path in sizes]
    source_limit = max(0, min(source_reserve, max_files - len(known)))
    sources = fallback._balanced_source_paths(sizes, source_limit)
    bootstrap_count = max(0, min(source_bootstrap, len(sources), max_files))
    bootstrap = sources[:bootstrap_count]
    remaining_sources = sources[bootstrap_count:]
    workflows = sorted(
        path
        for path in sizes
        if path.startswith(".github/workflows/")
        and path.endswith((".yml", ".yaml"))
        and sizes[path] <= hosted.MAX_FILE_BYTES
    )
    remainder = sorted(
        path
        for path, size in sizes.items()
        if hosted.should_fetch_path(path, size)
    )

    selected: list[str] = []
    for path in [*bootstrap, *known, *remaining_sources, *workflows, *remainder]:
        if path in selected:
            continue
        selected.append(path)
        if len(selected) >= max_files:
            break
    return selected


def fetch_repository_profile_with_budget_provenance(
    client: Any,
    repository: str,
    repo_meta: dict[str, Any],
) -> dict[str, Any]:
    """Fetch an exact-commit profile while retaining bounded request provenance."""

    branch = str(repo_meta.get("default_branch") or "main")
    commit_sha, commit_error = fallback._head_commit(client, repository, branch)
    ref = commit_sha or branch
    tree, tree_error = client.get_tree(repository, ref)
    root, root_error = fallback._contents_at_ref(client, repository, "", ref)
    root_items = [
        str(item.get("name") or "")
        for item in root
        if isinstance(item, dict)
    ] if isinstance(root, list) else []
    selected = select_budget_aware_profile_paths(tree)
    files: dict[str, str] = {}
    unavailable: list[str] = []
    source_attempted = 0
    source_fetched = 0
    source_failures: list[str] = []

    if commit_error:
        unavailable.append(f"Observed default-branch commit unavailable: {commit_error}")
    if root_error:
        unavailable.append(f"Root listing unavailable: {root_error}")
    if tree_error:
        unavailable.append(f"Recursive file tree unavailable: {tree_error}")

    for path in selected:
        is_source = fallback._eligible_source_path(path)
        if is_source:
            source_attempted += 1
        text, error = fallback._text_file_at_ref(client, repository, path, ref)
        if text is not None:
            files[path] = text
            if is_source:
                source_fetched += 1
            continue
        if is_source:
            if len(source_failures) < MAX_REPORTED_SOURCE_FAILURES:
                source_failures.append(f"{path}: {_bounded_error(error)}")
        elif path in hosted.KNOWN_FILE_PATHS:
            unavailable.append(error or f"Could not read {path} at the observed commit.")

    tree_paths = [
        str(item.get("path") or "")
        for item in tree
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
    ]
    total_source_paths = sum(1 for path in tree_paths if fallback._eligible_source_path(path))
    profile = fallback.build_api_sample_complexity_profile(
        files,
        commit_sha=commit_sha,
        total_source_paths=total_source_paths,
    )
    provenance = {
        "selected_path_count": len(selected),
        "source_bootstrap_limit": SOURCE_BOOTSTRAP_FILES,
        "source_paths_attempted": source_attempted,
        "source_paths_fetched": source_fetched,
        "source_fetch_failure_count": max(0, source_attempted - source_fetched),
        "source_fetch_failures": source_failures,
        "exact_commit": commit_sha or None,
    }
    profile["fetch_provenance"] = provenance
    profile.setdefault("evidence", []).append(
        "Hosted GitHub API complexity sampling fetched "
        f"{source_fetched} of {source_attempted} attempted production source path(s) "
        f"from commit {commit_sha or 'unavailable'}."
    )
    if source_fetched == 0:
        profile.setdefault("unavailable", []).insert(
            0,
            "Hosted GitHub API complexity sampling attempted "
            f"{source_attempted} production source path(s) but fetched none; "
            "same-run complexity measurements remain unavailable.",
        )
    for failure in source_failures:
        profile.setdefault("unavailable", []).append(
            "Hosted complexity source fetch failed: " + failure
        )

    fallback._CAPTURED_PROFILE.set(profile)
    return {
        "root_items": root_items,
        "tree_paths": tree_paths,
        "files": files,
        "unavailable": list(dict.fromkeys(unavailable)),
        "snapshot_commit_sha": commit_sha,
        "complexity_profile": profile,
    }


def attach_api_sample_complexity_with_provenance(
    result: dict[str, Any],
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    if result.get("status") != "complete" or not isinstance(profile, dict):
        return result

    valid = fallback._profile_valid(profile)
    provenance = profile.get("fetch_provenance") if isinstance(profile.get("fetch_provenance"), dict) else {}
    output = dict(result)
    output["complexity_evidence_provenance"] = {
        "status": "attached" if valid else "unavailable",
        "source": profile.get("source"),
        "commit_sha": profile.get("commit_sha"),
        "analyzed_file_count": profile.get("analyzed_file_count"),
        "total_source_paths": profile.get("source_file_count"),
        "fetch_provenance": provenance,
        "guardrail": profile.get("guardrail"),
        "human_review_required": True,
    }

    current = result.get("complexity_engine") if isinstance(result.get("complexity_engine"), dict) else {}
    if not valid:
        if not fallback._profile_valid(current):
            retained = dict(current)
            retained.setdefault("source", "checked_out_repository_complexity")
            retained["api_sample_fetch_provenance"] = provenance
            unavailable = list(retained.get("unavailable") or retained.get("unavailable_data_notes") or [])
            for line in profile.get("unavailable") or []:
                if line not in unavailable:
                    unavailable.append(line)
            retained["unavailable"] = unavailable
            output["complexity_engine"] = retained
        return output

    if fallback._profile_valid(current) and current.get("source") != "github_api_exact_commit_bounded_sample":
        return output
    output["complexity_engine"] = profile
    output.setdefault("head_sha", profile.get("commit_sha"))
    return output


def _install_unavailable_detail_bridge() -> bool:
    if getattr(complexity_integration, "_nico_complexity_unavailable_detail_bridge", False):
        return False
    original = complexity_integration._attach_unavailable

    def attach_unavailable_with_details(section: dict[str, Any], artifact: dict[str, Any]) -> None:
        original(section, artifact)
        values = section.setdefault("unavailable", [])
        if not isinstance(values, list):
            values = [values]
            section["unavailable"] = values
        for line in artifact.get("unavailable", [])[:MAX_REPORTED_SOURCE_FAILURES + 1]:
            complexity_integration._append_unique(
                values,
                "Complexity engine unavailable evidence: " + str(line),
            )

    complexity_integration._attach_unavailable = attach_unavailable_with_details
    complexity_integration._nico_complexity_unavailable_detail_bridge = True
    return True


def _bind_runtime(
    profile_dispatcher: Callable[[Any, str, dict[str, Any]], dict[str, Any]],
    assessment_runner: Callable[[dict[str, Any]], dict[str, Any]],
) -> None:
    hosted.fetch_repository_profile = profile_dispatcher
    hosted.run_github_assessment = assessment_runner
    try:
        from nico.api import main as api_main

        api_main.run_github_assessment = assessment_runner
    except Exception:
        pass


def install_hosted_api_complexity_fallback() -> dict[str, Any]:
    """Install the request-budget-aware, context-scoped Express dispatcher."""

    detail_bridge_installed = _install_unavailable_detail_bridge()

    installed = bool(getattr(hosted, "_nico_api_complexity_fallback_compat_installed", False))
    existing_dispatcher = getattr(hosted, "_nico_api_complexity_profile_dispatcher", None)
    existing_runner = getattr(hosted, "_nico_api_complexity_assessment_runner", None)
    if installed and callable(existing_dispatcher) and callable(existing_runner):
        binding_repaired = bool(
            hosted.fetch_repository_profile is not existing_dispatcher
            or hosted.run_github_assessment is not existing_runner
        )
        _bind_runtime(existing_dispatcher, existing_runner)
        return {
            "status": "already_installed",
            "version": "nico-hosted-api-complexity-fallback-v4",
            "shared_profile_override": False,
            "context_scoped_express_profile": True,
            "concurrent_express_requests_supported": True,
            "source_bootstrap_files": SOURCE_BOOTSTRAP_FILES,
            "fetch_provenance_retained": True,
            "unavailable_detail_bridge_installed": detail_bridge_installed,
            "runtime_binding_repaired": binding_repaired,
        }

    original_run = getattr(
        hosted,
        "_nico_original_run_github_assessment_api_complexity",
        hosted.run_github_assessment,
    )
    original_profile_fetcher = getattr(
        hosted,
        "_nico_original_fetch_repository_profile_api_complexity",
        hosted.fetch_repository_profile,
    )
    hosted._nico_original_run_github_assessment_api_complexity = original_run
    hosted._nico_original_fetch_repository_profile_api_complexity = original_profile_fetcher

    def profile_dispatcher(client: Any, repository: str, repo_meta: dict[str, Any]) -> dict[str, Any]:
        if _EXPRESS_PROFILE_ENABLED.get():
            return fetch_repository_profile_with_budget_provenance(client, repository, repo_meta)
        return original_profile_fetcher(client, repository, repo_meta)

    def run_github_assessment_with_api_complexity(payload: dict[str, Any]) -> dict[str, Any]:
        capture_token = fallback._CAPTURED_PROFILE.set(None)
        enabled_token = _EXPRESS_PROFILE_ENABLED.set(True)
        try:
            result = original_run(payload)
            return attach_api_sample_complexity_with_provenance(
                result,
                fallback._CAPTURED_PROFILE.get(),
            )
        finally:
            _EXPRESS_PROFILE_ENABLED.reset(enabled_token)
            fallback._CAPTURED_PROFILE.reset(capture_token)

    hosted._nico_api_complexity_profile_dispatcher = profile_dispatcher
    hosted._nico_api_complexity_assessment_runner = run_github_assessment_with_api_complexity
    _bind_runtime(profile_dispatcher, run_github_assessment_with_api_complexity)
    hosted._nico_api_complexity_fallback_compat_installed = True
    return {
        "status": "installed",
        "version": "nico-hosted-api-complexity-fallback-v4",
        "shared_profile_override": False,
        "context_scoped_express_profile": True,
        "concurrent_express_requests_supported": True,
        "source_bootstrap_files": SOURCE_BOOTSTRAP_FILES,
        "fetch_provenance_retained": True,
        "unavailable_detail_bridge_installed": detail_bridge_installed,
        "runtime_binding_repaired": False,
        "truth_boundary": "A bounded source bootstrap is attempted before manifest-heavy requests. Positive measurements can support scoring; failed fetches remain explicit and never force a score lift.",
    }


__all__ = [
    "SOURCE_BOOTSTRAP_FILES",
    "attach_api_sample_complexity_with_provenance",
    "fetch_repository_profile_with_budget_provenance",
    "install_hosted_api_complexity_fallback",
    "select_budget_aware_profile_paths",
]
