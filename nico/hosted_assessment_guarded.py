from __future__ import annotations

from typing import Any

from nico import hosted_assessment as base


def is_rate_limited(error: str | None) -> bool:
    if not error:
        return False
    lowered = error.lower()
    return "returned 429" in lowered or "rate limit" in lowered or "abuse detection" in lowered


class GuardedGitHubAssessmentClient(base.GitHubAssessmentClient):
    """GitHub client with request caching and explicit rate-limit semantics."""

    def __init__(self) -> None:
        super().__init__()
        self._json_cache: dict[tuple[str, tuple[tuple[str, Any], ...]], tuple[Any | None, str | None]] = {}

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
        key = (url, tuple(sorted((params or {}).items())))
        if key in self._json_cache:
            return self._json_cache[key]
        data, error = super().get_json(url, params)
        if is_rate_limited(error):
            error = f"GitHub metadata unavailable because the request was rate-limited; treat this section as degraded, not negative evidence. Original response: {error}"
        self._json_cache[key] = (data, error)
        return data, error


def fetch_workflows(client: base.GitHubAssessmentClient, repo: str) -> tuple[dict[str, str], list[str]]:
    workflows: dict[str, str] = {}
    unavailable: list[str] = []
    items, error = client.get_contents(repo, ".github/workflows")
    if isinstance(items, list):
        for item in items:
            if not isinstance(item, dict):
                continue
            name = item.get("name", "")
            path = item.get("path", "")
            if not name.endswith((".yml", ".yaml")):
                continue
            text, text_error = client.get_text_file(repo, path)
            if text is None:
                unavailable.append(text_error or f"Could not read {path}.")
            else:
                workflows[path] = text
        return workflows, unavailable

    if error:
        unavailable.append(f"Workflow directory listing unavailable: {error}")
    elif items is not None:
        unavailable.append(".github/workflows exists but was not returned as a directory listing.")

    repo_meta, repo_error = client.get_repo(repo)
    branch = (repo_meta or {}).get("default_branch") or "main"
    tree, tree_error = client.get_tree(repo, branch)
    if tree_error:
        unavailable.append(f"Workflow tree fallback unavailable: {tree_error}")
        return workflows, unavailable

    workflow_paths = [
        str(item.get("path") or "")
        for item in tree
        if isinstance(item, dict)
        and item.get("type") == "blob"
        and str(item.get("path") or "").startswith(".github/workflows/")
        and str(item.get("path") or "").endswith((".yml", ".yaml"))
    ]
    for path in workflow_paths[:25]:
        text, text_error = client.get_text_file(repo, path)
        if text is None:
            unavailable.append(text_error or f"Could not read {path}.")
        else:
            workflows[path] = text
    if workflows:
        unavailable.append("Workflow files were recovered from the recursive repository tree after directory listing failed.")
    elif not workflow_paths:
        unavailable.append("No .github/workflows/*.yml or *.yaml files were visible in the recursive repository tree.")
    return workflows, unavailable


def query_osv(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    exact: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    skipped_non_exact = 0
    for dep in dependencies:
        version = dep.get("version") or ""
        if dep.get("operator") != "==" or not version or version in {"*", "latest"}:
            skipped_non_exact += 1
            continue
        key = (dep.get("ecosystem", ""), dep.get("name", "").lower(), version)
        if key in seen:
            continue
        seen.add(key)
        exact.append(dep)
    if not exact:
        note = "OSV lookup skipped because no exact pinned dependency versions were available from the inspected manifests."
        if skipped_non_exact:
            note += f" {skipped_non_exact} non-exact dependency specifier(s) require lockfiles or sandboxed audit tools before vulnerability status can be confirmed."
        return [], [note]

    evidence, unavailable = base.query_osv(exact)
    deduped = list(dict.fromkeys(evidence))
    if skipped_non_exact:
        unavailable.append(f"OSV skipped {skipped_non_exact} non-exact dependency specifier(s); hosted assessment avoids treating lower-bound ranges as installed versions.")
    return deduped, unavailable


def analyze_ci(workflows: dict[str, str], workflow_unavailable: list[str], workflow_runs: list[dict[str, Any]], runs_error: str | None) -> dict[str, Any]:
    result = base.analyze_ci(workflows, workflow_unavailable, workflow_runs, runs_error)
    if workflows:
        # Real workflow files are positive evidence even if run history is rate-limited.
        result["findings"] = [item for item in result.get("findings", []) if "No CI/CD workflow files" not in item]
        result["evidence"] = [item for item in result.get("evidence", []) if "No GitHub Actions workflow files" not in item and "No CI/CD workflow files" not in item]
        if is_rate_limited(runs_error):
            result["score"] = max(int(result.get("score", 0)), 68)
            result["status_hint"] = "degraded_metadata"
        return result
    if any(is_rate_limited(item) for item in workflow_unavailable) or is_rate_limited(runs_error):
        result["score"] = max(int(result.get("score", 0)), 45)
        result["findings"] = [item for item in result.get("findings", []) if "No CI/CD workflow files" not in item]
        result["evidence"] = [item for item in result.get("evidence", []) if "No GitHub Actions workflow files" not in item and "No CI/CD workflow files" not in item]
        result["evidence"].insert(0, "CI/CD evidence is degraded because GitHub metadata was rate-limited; absence of workflow data is not treated as proof of missing CI.")
        result["status_hint"] = "degraded_metadata"
    return result


def analyze_code_activity(commits: list[dict[str, Any]], pulls: list[dict[str, Any]], since_iso: str, commit_error: str | None, pr_error: str | None, file_scan: dict[str, Any]) -> dict[str, Any]:
    result = base.analyze_code_activity(commits, pulls, since_iso, commit_error, pr_error, file_scan)
    if is_rate_limited(commit_error) or is_rate_limited(pr_error):
        result["findings"] = [item for item in result.get("findings", []) if "No recent pull-request evidence" not in item]
        result["evidence"] = [item for item in result.get("evidence", []) if "No recent pull-request evidence" not in item]
        result["evidence"].insert(0, "Commit/PR metadata is degraded because GitHub returned rate limiting; missing metadata is not treated as direct-to-main evidence.")
        result["score"] = max(int(result.get("score", 0)), 55)
        result["status_hint"] = "degraded_metadata"
    return result


def post_process_result(result: dict[str, Any]) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result
    sections = result.get("sections", [])
    degraded = False
    for item in sections:
        unavailable = item.get("unavailable", []) or []
        evidence = item.get("evidence", []) or []
        if any(is_rate_limited(str(note)) for note in unavailable + evidence):
            degraded = True
            item.setdefault("unavailable", []).append("Metadata was rate-limited during this run; rerun with authenticated GitHub access or after cooldown for stronger confidence.")
            if item.get("id") in {"code_audit", "ci_cd", "velocity_complexity"}:
                item["status"] = "yellow" if int(item.get("score", 0)) >= 45 else "gray"
    if degraded:
        result["assessment_quality"] = "degraded_metadata"
        result["executive_summary"] += " Some GitHub metadata was rate-limited, so affected sections are degraded rather than final negative evidence."
    return result


base.GitHubAssessmentClient = GuardedGitHubAssessmentClient
base.fetch_workflows = fetch_workflows
base.query_osv = query_osv
base.analyze_ci = analyze_ci
base.analyze_code_activity = analyze_code_activity


def run_github_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    return post_process_result(base.run_github_assessment(payload))
