from __future__ import annotations

import base64
import json
from collections import defaultdict
from contextvars import ContextVar
from pathlib import PurePosixPath
from typing import Any, Iterable
from urllib.parse import quote

import nico.full_assessment_complexity_evidence as complexity_evidence
import nico.hosted_assessment as hosted


MAX_COMPLEXITY_SOURCE_FILES = 48
SOURCE_SUFFIXES = (".py", ".js", ".jsx", ".ts", ".tsx")
SKIP_PARTS = {
    ".git",
    "node_modules",
    ".next",
    "dist",
    "build",
    "coverage",
    ".venv",
    "venv",
    "__pycache__",
    "vendor",
}
TEST_MARKERS = ("/test/", "/tests/", "test_", "_test.", ".test.", ".spec.")
_CAPTURED_PROFILE: ContextVar[dict[str, Any] | None] = ContextVar(
    "nico_hosted_api_complexity_profile",
    default=None,
)


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _eligible_source_path(path: str) -> bool:
    normalized = str(PurePosixPath(path))
    lowered = f"/{normalized.lower()}"
    if not lowered.endswith(SOURCE_SUFFIXES):
        return False
    parts = {part.lower() for part in PurePosixPath(normalized).parts}
    if parts & SKIP_PARTS:
        return False
    return not any(marker in lowered for marker in TEST_MARKERS)


def _balanced_source_paths(paths: Iterable[str], limit: int) -> list[str]:
    groups: dict[str, list[str]] = defaultdict(list)
    for path in sorted({str(item) for item in paths if _eligible_source_path(str(item))}):
        parts = PurePosixPath(path).parts
        group = parts[0] if len(parts) > 1 else "."
        groups[group].append(path)

    ordered_groups = sorted(groups, key=lambda item: (item != ".", item))
    selected: list[str] = []
    index = 0
    while len(selected) < limit:
        added = False
        for group in ordered_groups:
            values = groups[group]
            if index < len(values):
                selected.append(values[index])
                added = True
                if len(selected) >= limit:
                    break
        if not added:
            break
        index += 1
    return selected


def select_balanced_profile_paths(
    tree_entries: list[dict[str, Any]],
    *,
    max_files: int = hosted.MAX_TEXT_FILES,
    source_reserve: int = MAX_COMPLEXITY_SOURCE_FILES,
) -> list[str]:
    """Select a deterministic bounded profile with reserved production-source coverage."""

    sizes = {
        str(item.get("path") or ""): _int(item.get("size"))
        for item in tree_entries
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
    }
    known = [path for path in hosted.KNOWN_FILE_PATHS if path in sizes]
    source_limit = max(0, min(source_reserve, max_files - len(known)))
    sources = _balanced_source_paths(sizes, source_limit)
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
    for path in [*known, *sources, *workflows, *remainder]:
        if path in selected:
            continue
        selected.append(path)
        if len(selected) >= max_files:
            break
    return selected


def _contents_at_ref(client: Any, repository: str, path: str, ref: str) -> tuple[Any | None, str | None]:
    suffix = f"/contents/{quote(path, safe='/')}" if path else "/contents"
    return client.get_json(client.repo_url(repository, suffix), {"ref": ref})


def _text_file_at_ref(client: Any, repository: str, path: str, ref: str) -> tuple[str | None, str | None]:
    value, error = _contents_at_ref(client, repository, path, ref)
    if error:
        return None, error
    if not isinstance(value, dict) or value.get("type") != "file":
        return None, f"{path} is not a file at the observed commit."
    if _int(value.get("size")) > hosted.MAX_FILE_BYTES:
        return None, f"{path} exceeds the hosted text-inspection limit."
    try:
        return base64.b64decode(value.get("content") or "").decode("utf-8", errors="replace"), None
    except Exception:
        return None, f"{path} could not be decoded at the observed commit."


def _head_commit(client: Any, repository: str, branch: str) -> tuple[str, str | None]:
    value, error = client.get_json(
        client.repo_url(repository, f"/commits/{quote(branch, safe='')}")
    )
    sha = str(value.get("sha") or "") if isinstance(value, dict) else ""
    if sha:
        return sha, None
    return "", error or "The default-branch commit SHA was unavailable."


def _manifest_dependency_count(files: dict[str, str]) -> int:
    count = 0
    requirements = files.get("requirements.txt")
    if requirements:
        count += sum(
            1
            for line in requirements.splitlines()
            if line.strip() and not line.strip().startswith(("#", "-"))
        )
    for path, text in files.items():
        if not path.endswith("package.json"):
            continue
        try:
            payload = json.loads(text)
        except ValueError:
            continue
        for key in ("dependencies", "devDependencies", "peerDependencies"):
            values = payload.get(key)
            if isinstance(values, dict):
                count += len(values)
    return count


def _sample_score(measured: dict[str, Any], total_source_paths: int) -> tuple[int, str, list[str]]:
    score = 88
    findings: list[str] = []
    total_loc = _int(measured.get("total_source_loc"))
    maximum = _int(measured.get("maximum_cyclomatic_complexity"))
    high_complexity = _int(measured.get("high_complexity_functions"))
    duplicate = measured.get("duplicate_evidence") if isinstance(measured.get("duplicate_evidence"), dict) else {}
    duplicate_ratio = float(duplicate.get("duplicate_line_ratio") or 0.0)

    if total_source_paths > 250:
        score -= 10
        findings.append("The repository source footprint is large enough to require deeper whole-repository architecture review.")
    elif total_source_paths > 120:
        score -= 4
    if total_loc > 50_000:
        score -= 8
        findings.append("The bounded source sample contains more than 50,000 source LOC and increases review depth.")
    if maximum >= 60:
        score -= 15
        findings.append("The bounded sample contains a very-high-complexity function unit.")
    elif maximum >= 35:
        score -= 8
        findings.append("The bounded sample contains an elevated-complexity function unit.")
    if high_complexity >= 5:
        score -= 6
        findings.append("Multiple sampled function units have elevated complexity.")
    if duplicate_ratio >= 0.15:
        score -= 5
        findings.append("The bounded sample contains a material cross-file duplicate-line signal.")

    score = max(35, min(92, score))
    risk = "high" if score < 70 else "medium" if score < 82 else "low"
    return score, risk, findings


def build_api_sample_complexity_profile(
    files: dict[str, str],
    *,
    commit_sha: str,
    total_source_paths: int,
) -> dict[str, Any]:
    """Normalize exact-commit GitHub API sample metrics into the report profile contract."""

    source_files = {path: text for path, text in files.items() if _eligible_source_path(path)}
    measured = complexity_evidence.collect_complexity_evidence(source_files)
    analyzed = _int(measured.get("files_analyzed"))
    total_loc = _int(measured.get("total_source_loc"))
    functions = _int(measured.get("functions_measured"))
    score, risk, score_findings = _sample_score(measured, total_source_paths)
    if not commit_sha or analyzed <= 0 or total_loc <= 0 or functions <= 0:
        risk = "review_required"

    raw_hotspots = measured.get("hotspots") if isinstance(measured.get("hotspots"), list) else []
    hotspots = [
        {
            "path": item.get("path"),
            "name": item.get("name"),
            "line": item.get("line"),
            "loc": item.get("loc"),
            "cyclomatic_complexity": item.get("cyclomatic_complexity"),
            "max_nesting": item.get("max_nesting"),
            "hotspot_score": item.get("hotspot_score"),
            "churn": None,
            "primary_owner": "unavailable_in_api_sample",
            "owner_concentration": None,
        }
        for item in raw_hotspots[:12]
        if isinstance(item, dict)
    ]
    unavailable = list(dict.fromkeys(
        [
            *[str(item) for item in measured.get("unavailable_data_notes") or []],
            "Git churn and ownership concentration require a checked-out repository history and are not inferred from the GitHub API text sample.",
            "A full call graph is unavailable in the bounded API sample; internal import edges are retained as a coupling signal instead.",
        ]
    ))
    evidence = [
        f"Exact-commit GitHub API complexity sample analyzed {analyzed} of {total_source_paths} eligible production source path(s).",
        f"Bounded sample measured {total_loc} source LOC and {functions} function-like units; maximum measured function complexity={_int(measured.get('maximum_cyclomatic_complexity'))}.",
        f"Bounded coupling evidence contains {_int(measured.get('internal_import_edges'))} internal import edge(s); duplicate-line ratio={float((measured.get('duplicate_evidence') or {}).get('duplicate_line_ratio') or 0.0):.4f}.",
    ]
    return {
        "artifact_schema": "nico.complexity.api_sample.v1",
        "source": "github_api_exact_commit_bounded_sample",
        "evidence_scope": "Bounded production-source sample fetched read-only from the observed default-branch commit through the authorized GitHub API.",
        "commit_sha": commit_sha,
        "source_file_count": total_source_paths,
        "analyzed_file_count": analyzed,
        "total_loc": total_loc,
        "total_functions": functions,
        "call_graph_edge_count": 0,
        "internal_import_edge_count": _int(measured.get("internal_import_edges")),
        "max_file_cyclomatic_complexity": _int(measured.get("maximum_cyclomatic_complexity")),
        "average_cyclomatic_per_file": measured.get("average_cyclomatic_complexity"),
        "manifest_dependency_count": _manifest_dependency_count(files),
        "hotspots": hotspots,
        "complexity_score": score,
        "architecture_score": max(45, min(92, score + 2)),
        "velocity_score": max(45, min(90, score)),
        "risk_level": risk,
        "evidence": evidence,
        "findings": list(dict.fromkeys([*score_findings, *[str(item) for item in measured.get("parse_notes") or []]])),
        "unavailable": unavailable,
        "sampled_paths": sorted(source_files),
        "analyzer_version": measured.get("analyzer_version") or "unknown",
        "guardrail": "This profile is verified only for the bounded exact-commit GitHub API sample. It does not establish whole-repository absence of complexity, duplication, coupling, ownership, or maintainability risk.",
        "human_review_required": True,
    }


def fetch_repository_profile_with_complexity(
    client: Any,
    repository: str,
    repo_meta: dict[str, Any],
) -> dict[str, Any]:
    """Fetch one balanced exact-commit profile and retain a bounded complexity sample."""

    branch = str(repo_meta.get("default_branch") or "main")
    commit_sha, commit_error = _head_commit(client, repository, branch)
    ref = commit_sha or branch
    tree, tree_error = client.get_tree(repository, ref)
    root, root_error = _contents_at_ref(client, repository, "", ref)
    root_items = [str(item.get("name") or "") for item in root if isinstance(item, dict)] if isinstance(root, list) else []
    selected = select_balanced_profile_paths(tree)
    files: dict[str, str] = {}
    unavailable: list[str] = []
    if commit_error:
        unavailable.append(f"Observed default-branch commit unavailable: {commit_error}")
    if root_error:
        unavailable.append(f"Root listing unavailable: {root_error}")
    if tree_error:
        unavailable.append(f"Recursive file tree unavailable: {tree_error}")

    for path in selected:
        text, error = _text_file_at_ref(client, repository, path, ref)
        if text is not None:
            files[path] = text
        elif path in hosted.KNOWN_FILE_PATHS:
            unavailable.append(error or f"Could not read {path} at the observed commit.")

    tree_paths = [
        str(item.get("path") or "")
        for item in tree
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path")
    ]
    total_source_paths = sum(1 for path in tree_paths if _eligible_source_path(path))
    profile = build_api_sample_complexity_profile(
        files,
        commit_sha=commit_sha,
        total_source_paths=total_source_paths,
    )
    _CAPTURED_PROFILE.set(profile)
    return {
        "root_items": root_items,
        "tree_paths": tree_paths,
        "files": files,
        "unavailable": list(dict.fromkeys(unavailable)),
        "snapshot_commit_sha": commit_sha,
        "complexity_profile": profile,
    }


def _profile_valid(profile: dict[str, Any]) -> bool:
    return bool(
        profile.get("commit_sha")
        and _int(profile.get("analyzed_file_count")) > 0
        and _int(profile.get("total_loc")) > 0
        and _int(profile.get("total_functions")) > 0
        and str(profile.get("risk_level") or "") not in {"review_required", "unavailable", "unknown"}
    )


def attach_api_sample_complexity(
    result: dict[str, Any],
    profile: dict[str, Any] | None,
) -> dict[str, Any]:
    if result.get("status") != "complete" or not isinstance(profile, dict) or not _profile_valid(profile):
        return result
    current = result.get("complexity_engine") if isinstance(result.get("complexity_engine"), dict) else {}
    if _profile_valid(current) and current.get("source") != "github_api_exact_commit_bounded_sample":
        return result
    output = dict(result)
    output["complexity_engine"] = profile
    output.setdefault("head_sha", profile.get("commit_sha"))
    output["complexity_evidence_provenance"] = {
        "status": "attached",
        "source": profile.get("source"),
        "commit_sha": profile.get("commit_sha"),
        "analyzed_file_count": profile.get("analyzed_file_count"),
        "total_source_paths": profile.get("source_file_count"),
        "guardrail": profile.get("guardrail"),
        "human_review_required": True,
    }
    return output


def install_hosted_api_complexity_fallback() -> dict[str, Any]:
    """Install the balanced API-sample fallback on the production Express path."""

    installed = bool(getattr(hosted, "_nico_api_complexity_fallback_installed", False))
    if installed:
        return {
            "status": "already_installed",
            "version": "nico-hosted-api-complexity-fallback-v1",
            "max_source_files": MAX_COMPLEXITY_SOURCE_FILES,
        }

    original_run = hosted.run_github_assessment
    hosted._nico_original_run_github_assessment_api_complexity = original_run
    hosted.fetch_repository_profile = fetch_repository_profile_with_complexity

    def run_github_assessment_with_api_complexity(payload: dict[str, Any]) -> dict[str, Any]:
        token = _CAPTURED_PROFILE.set(None)
        try:
            result = original_run(payload)
            return attach_api_sample_complexity(result, _CAPTURED_PROFILE.get())
        finally:
            _CAPTURED_PROFILE.reset(token)

    hosted.run_github_assessment = run_github_assessment_with_api_complexity
    try:
        from nico.api import main as api_main

        api_main.run_github_assessment = run_github_assessment_with_api_complexity
    except Exception:
        pass
    hosted._nico_api_complexity_fallback_installed = True
    return {
        "status": "installed",
        "version": "nico-hosted-api-complexity-fallback-v1",
        "max_source_files": MAX_COMPLEXITY_SOURCE_FILES,
        "truth_boundary": "A positive exact-commit bounded API sample can support complexity scoring; checkout-only churn, ownership, and full call-graph claims remain unavailable.",
    }


__all__ = [
    "MAX_COMPLEXITY_SOURCE_FILES",
    "attach_api_sample_complexity",
    "build_api_sample_complexity_profile",
    "fetch_repository_profile_with_complexity",
    "install_hosted_api_complexity_fallback",
    "select_balanced_profile_paths",
]
