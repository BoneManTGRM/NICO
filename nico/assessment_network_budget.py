from __future__ import annotations

import base64
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import requests

import nico.hosted_assessment as hosted
import nico.snapshot_repository_evidence as snapshot_evidence
from nico.assessment_block_messages import install_assessment_block_messages


def _env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


GITHUB_REQUEST_TIMEOUT_SECONDS = _env_int("NICO_GITHUB_REQUEST_TIMEOUT_SECONDS", 8, 2, 25)
GITHUB_COLLECTION_BUDGET_SECONDS = _env_int("NICO_GITHUB_COLLECTION_BUDGET_SECONDS", 75, 30, 180)
GITHUB_FILE_FETCH_WORKERS = _env_int("NICO_GITHUB_FILE_FETCH_WORKERS", 8, 1, 12)
OSV_REQUEST_TIMEOUT_SECONDS = _env_int("NICO_OSV_REQUEST_TIMEOUT_SECONDS", 8, 2, 20)


def _remaining(client: Any) -> float:
    deadline = float(getattr(client, "_nico_collection_deadline", 0.0) or 0.0)
    if deadline <= 0:
        return float(GITHUB_COLLECTION_BUDGET_SECONDS)
    return max(0.0, deadline - time.monotonic())


def collection_budget_status(client: Any) -> dict[str, Any]:
    started = float(getattr(client, "_nico_collection_started", time.monotonic()))
    elapsed = max(0.0, time.monotonic() - started)
    remaining = _remaining(client)
    return {
        "budget_seconds": GITHUB_COLLECTION_BUDGET_SECONDS,
        "request_timeout_seconds": GITHUB_REQUEST_TIMEOUT_SECONDS,
        "file_fetch_workers": GITHUB_FILE_FETCH_WORKERS,
        "elapsed_seconds": round(elapsed, 2),
        "remaining_seconds": round(remaining, 2),
        "budget_exhausted": remaining <= 0,
    }


def _bounded_get_json(self: Any, url: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
    remaining = _remaining(self)
    if remaining <= 0:
        return None, "GitHub collection time budget was exhausted; remaining evidence is unavailable for this run."
    timeout = max(0.5, min(float(GITHUB_REQUEST_TIMEOUT_SECONDS), remaining))
    try:
        response = requests.get(url, headers=self.headers, params=params, timeout=timeout)
    except requests.RequestException:
        return None, "GitHub request did not complete within the bounded collection window."
    if response.status_code >= 400:
        return None, f"GitHub returned HTTP {response.status_code}; this evidence source is unavailable."
    try:
        return response.json(), None
    except ValueError:
        return None, "GitHub returned a non-JSON response."


def _parallel_fetch(
    paths: list[str],
    fetcher: Callable[[str], tuple[str | None, str | None]],
) -> dict[str, tuple[str | None, str | None]]:
    ordered = list(dict.fromkeys(str(path) for path in paths if str(path)))
    if not ordered:
        return {}
    workers = max(1, min(GITHUB_FILE_FETCH_WORKERS, len(ordered)))
    results: dict[str, tuple[str | None, str | None]] = {}
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="nico-github-file") as executor:
        future_paths = {executor.submit(fetcher, path): path for path in ordered}
        for future in as_completed(future_paths):
            path = future_paths[future]
            try:
                results[path] = future.result()
            except Exception:
                results[path] = (None, f"{path} could not be read within the bounded collection window.")
    return results


def _bounded_repository_profile(client: Any, repo: str, repo_meta: dict[str, Any]) -> dict[str, Any]:
    branch = repo_meta.get("default_branch") or "main"
    tree, tree_error = client.get_tree(repo, branch)
    root, root_error = client.get_contents(repo)
    root_items = hosted.list_dir_names(root)
    unavailable: list[str] = []
    if root_error:
        unavailable.append(f"Root listing unavailable: {root_error}")
    if tree_error:
        unavailable.append(f"Recursive file tree unavailable: {tree_error}")

    blobs = [item for item in tree if isinstance(item, dict) and item.get("type") == "blob"]
    tree_paths = [str(item.get("path") or "") for item in blobs if item.get("path")]
    sizes = {str(item.get("path") or ""): int(item.get("size") or 0) for item in blobs if item.get("path")}
    candidates = [path for path in hosted.KNOWN_FILE_PATHS if path in tree_paths]
    candidates.extend(
        path for path in tree_paths
        if path not in candidates and hosted.should_fetch_path(path, sizes.get(path, 0))
    )
    selected = candidates[: hosted.MAX_TEXT_FILES]
    fetched = _parallel_fetch(selected, lambda path: client.get_text_file(repo, path))
    files: dict[str, str] = {}
    for path in selected:
        text, error = fetched.get(path, (None, "File collection did not return a result."))
        if text is not None:
            files[path] = text
        elif path in hosted.KNOWN_FILE_PATHS:
            unavailable.append(error or f"Could not read {path}.")
    budget = collection_budget_status(client)
    if budget["budget_exhausted"]:
        unavailable.append("GitHub collection reached its bounded runtime; unfetched evidence is marked unavailable rather than leaving the assessment request running indefinitely.")
    return {
        "root_items": root_items,
        "tree_paths": tree_paths,
        "files": files,
        "unavailable": sorted(set(unavailable)),
        "collection_budget": budget,
    }


def _bounded_workflows(client: Any, repo: str) -> tuple[dict[str, str], list[str]]:
    workflows: dict[str, str] = {}
    unavailable: list[str] = []
    items, error = client.get_contents(repo, ".github/workflows")
    if error:
        unavailable.append("No readable .github/workflows directory was found through the bounded GitHub contents API.")
        return workflows, unavailable
    if not isinstance(items, list):
        unavailable.append(".github/workflows exists but was not returned as a directory listing.")
        return workflows, unavailable
    paths = [
        str(item.get("path") or "")
        for item in items
        if isinstance(item, dict) and str(item.get("name") or "").endswith((".yml", ".yaml")) and item.get("path")
    ]
    fetched = _parallel_fetch(paths, lambda path: client.get_text_file(repo, path))
    for path in paths:
        text, text_error = fetched.get(path, (None, "Workflow collection did not return a result."))
        if text is None:
            unavailable.append(text_error or f"Could not read {path}.")
        else:
            workflows[path] = text
    return workflows, unavailable


def _snapshot_text_file(client: Any, repository: str, path: str, ref: str) -> tuple[str | None, str | None]:
    value, error = snapshot_evidence._contents(client, repository, path, ref)
    if error:
        return None, error
    if not isinstance(value, dict) or value.get("type") != "file":
        return None, f"{path} is not a file at the captured commit."
    if int(value.get("size") or 0) > hosted.MAX_FILE_BYTES:
        return None, f"{path} exceeds the hosted text-inspection limit."
    try:
        return base64.b64decode(value.get("content") or "").decode("utf-8", errors="replace"), None
    except Exception:
        return None, f"{path} could not be decoded at the captured commit."


def _bounded_snapshot_profile(client: Any, repository: str, snapshot: dict[str, Any]) -> dict[str, Any]:
    commit_sha = str(snapshot.get("commit_sha") or "")
    tree_ref = str(snapshot.get("tree_sha") or commit_sha)
    tree_value, tree_error = snapshot_evidence._get_json(
        client,
        repository,
        f"/git/trees/{snapshot_evidence.quote(tree_ref, safe='')}",
        {"recursive": "1"},
    )
    tree = tree_value.get("tree") if isinstance(tree_value, dict) and isinstance(tree_value.get("tree"), list) else []
    root, root_error = snapshot_evidence._contents(client, repository, "", commit_sha)
    root_items = [str(item.get("name") or "") for item in root if isinstance(item, dict)] if isinstance(root, list) else []
    unavailable: list[str] = []
    if tree_error or not tree:
        unavailable.append(snapshot_evidence._safe_note("Captured-commit recursive file tree", tree_error))
    if root_error:
        unavailable.append(snapshot_evidence._safe_note("Captured-commit root listing", root_error))

    blobs = [item for item in tree if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")]
    sizes = {str(item["path"]): int(item.get("size") or 0) for item in blobs}
    candidates = [path for path in hosted.KNOWN_FILE_PATHS if path in sizes]
    candidates.extend(path for path in sizes if path not in candidates and hosted.should_fetch_path(path, sizes[path]))
    selected = candidates[: hosted.MAX_TEXT_FILES]
    fetched = _parallel_fetch(selected, lambda path: _snapshot_text_file(client, repository, path, commit_sha))
    files: dict[str, str] = {}
    for path in selected:
        text, error = fetched.get(path, (None, "Captured-commit collection did not return a result."))
        if text is not None:
            files[path] = text
        elif path in hosted.KNOWN_FILE_PATHS:
            unavailable.append(snapshot_evidence._safe_note(f"Captured-commit file {path}", error))
    budget = collection_budget_status(client)
    if budget["budget_exhausted"]:
        unavailable.append("Captured-commit collection reached its bounded runtime; remaining files are unavailable for this run.")
    return {
        "files": files,
        "tree_paths": list(sizes),
        "root_items": root_items,
        "unavailable": sorted(set(unavailable)),
        "collection_budget": budget,
    }


def _bounded_query_osv(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    pinned = [dep for dep in dependencies if dep.get("version") and dep.get("version") not in {"*", "latest"}][:75]
    if not pinned:
        return [], ["OSV lookup skipped because no exact dependency versions were available from the inspected manifests."]
    queries = [
        {"package": {"name": dep["name"], "ecosystem": dep["ecosystem"]}, "version": dep["version"]}
        for dep in pinned
    ]
    try:
        response = requests.post(hosted.OSV_API, json={"queries": queries}, timeout=OSV_REQUEST_TIMEOUT_SECONDS)
    except requests.RequestException:
        return [], ["OSV lookup did not complete within the bounded dependency-review window."]
    if response.status_code >= 400:
        return [], [f"OSV lookup returned HTTP {response.status_code}; dependency vulnerability status is incomplete."]
    try:
        data = response.json()
    except ValueError:
        return [], ["OSV lookup returned a non-JSON response."]
    evidence: list[str] = []
    results = data.get("results", []) if isinstance(data, dict) else []
    for dep, result in zip(pinned, results):
        vulns = result.get("vulns", []) if isinstance(result, dict) else []
        if vulns:
            ids = ", ".join(str(item.get("id")) for item in vulns[:5] if isinstance(item, dict))
            evidence.append(f"OSV returned {len(vulns)} vulnerability record(s) for {dep['ecosystem']}:{dep['name']}@{dep['version']}: {ids}.")
    if not evidence:
        evidence.append(f"OSV returned no vulnerability records for {len(pinned)} pinned dependency query/queries.")
    return evidence, []


def _rebind_collectors() -> None:
    """Restore bounded module-level collectors if another compatibility patch replaced them."""

    hosted.fetch_repository_profile = _bounded_repository_profile
    hosted.fetch_workflows = _bounded_workflows
    hosted.query_osv = _bounded_query_osv
    snapshot_evidence._profile = _bounded_snapshot_profile


def install_assessment_network_budget() -> dict[str, Any]:
    """Install one bounded network policy for hosted Express and Mid collection."""

    block_messages = install_assessment_block_messages()
    client_cls = hosted.GitHubAssessmentClient
    already_installed = bool(getattr(client_cls, "_nico_budget_installed", False))
    if not already_installed:
        original_init = client_cls.__init__

        def bounded_init(self: Any) -> None:
            original_init(self)
            self._nico_collection_started = time.monotonic()
            self._nico_collection_deadline = self._nico_collection_started + GITHUB_COLLECTION_BUDGET_SECONDS

        client_cls.__init__ = bounded_init
        client_cls.get_json = _bounded_get_json
        client_cls.collection_budget_status = collection_budget_status
        client_cls._nico_budget_installed = True

    _rebind_collectors()
    return {
        "status": "already_installed" if already_installed else "installed",
        "block_messages": block_messages,
        **collection_policy(),
    }


def collection_policy() -> dict[str, Any]:
    return {
        "github_request_timeout_seconds": GITHUB_REQUEST_TIMEOUT_SECONDS,
        "github_collection_budget_seconds": GITHUB_COLLECTION_BUDGET_SECONDS,
        "github_file_fetch_workers": GITHUB_FILE_FETCH_WORKERS,
        "osv_request_timeout_seconds": OSV_REQUEST_TIMEOUT_SECONDS,
        "rule": "When the bounded collection window is exhausted, remaining evidence is marked unavailable and the assessment returns instead of waiting indefinitely.",
    }


__all__ = [
    "GITHUB_REQUEST_TIMEOUT_SECONDS",
    "GITHUB_COLLECTION_BUDGET_SECONDS",
    "GITHUB_FILE_FETCH_WORKERS",
    "OSV_REQUEST_TIMEOUT_SECONDS",
    "collection_budget_status",
    "collection_policy",
    "install_assessment_network_budget",
]
