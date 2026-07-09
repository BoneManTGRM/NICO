from __future__ import annotations

import base64
import html
import io
import json
import os
import re
import textwrap
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


GITHUB_API = "https://api.github.com"
OSV_API = "https://api.osv.dev/v1/querybatch"
SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
MAX_TEXT_FILES = 90
MAX_FILE_BYTES = 240_000
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".txt", ".md", ".sh", ".html", ".css", ".xml", ".env", ".example",
}
SKIP_PATH_PARTS = {".git", "node_modules", ".next", "dist", "build", ".venv", "venv", "__pycache__"}


SERVICE_TARGETS = {
    "express_technical_health_assessment": {"current": "65-75%", "target": "90-95%"},
    "mid_technical_health_assessment": {"current": "30-40%", "target": "75-85%"},
    "ongoing_product_engineering_retainer": {"current": "15-25%", "target": "55-70%"},
    "full_client_ready_replacement": {"current": "40-50%", "target": "75-85% with human review"},
}


SECRET_PATTERNS = [
    ("private_key", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")),
    ("github_token", re.compile(r"gh[pousr]_[A-Za-z0-9_]{20,}")),
    ("aws_access_key", re.compile(r"AKIA[0-9A-Z]{16}")),
    ("generic_secret_assignment", re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[A-Za-z0-9_./+=:-]{16,}")),
]


RISK_PATTERNS = [
    ("python_eval_exec", re.compile(r"\b(eval|exec)\s*\("), "Dynamic code execution should be reviewed."),
    ("python_shell_true", re.compile(r"shell\s*=\s*True"), "subprocess shell=True expands command-injection risk."),
    ("python_os_system", re.compile(r"os\.system\s*\("), "os.system calls should be replaced with safer subprocess patterns."),
    ("unsafe_yaml_load", re.compile(r"yaml\.load\s*\("), "yaml.load can be unsafe without SafeLoader."),
    ("pickle_loads", re.compile(r"pickle\.loads?\s*\("), "pickle loading untrusted data can execute code."),
    ("js_inner_html", re.compile(r"\.innerHTML\s*="), "innerHTML assignments can create XSS risk."),
    ("react_dangerous_html", re.compile(r"dangerouslySetInnerHTML"), "dangerouslySetInnerHTML requires strict sanitization evidence."),
    ("tls_verify_disabled", re.compile(r"verify\s*=\s*False|rejectUnauthorized\s*:\s*false"), "Disabled TLS verification should not ship to production."),
]

KNOWN_FILE_PATHS = [
    "README.md", "package.json", "apps/web/package.json", "package-lock.json", "apps/web/package-lock.json",
    "pnpm-lock.yaml", "apps/web/pnpm-lock.yaml", "yarn.lock", "apps/web/yarn.lock", "requirements.txt",
    "pyproject.toml", "Pipfile", "Pipfile.lock", "poetry.lock", "tsconfig.json", "apps/web/tsconfig.json",
    "pytest.ini", "Dockerfile", "Procfile", "render.yaml", "railway.json", "fly.toml", ".env.example",
]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_repository(value: str) -> str:
    value = (value or "").strip()
    value = value.replace("https://github.com/", "").replace("http://github.com/", "")
    value = value.replace("git@github.com:", "")
    value = value.replace(".git", "")
    value = value.strip("/")
    parts = value.split("/")
    if len(parts) >= 2:
        value = "/".join(parts[:2])
    if not SAFE_REPO_RE.match(value):
        raise ValueError("repository must be owner/name or a GitHub repository URL")
    return value


class GitHubAssessmentClient:
    def __init__(self) -> None:
        token = os.getenv("NICO_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
        self.headers = {"Accept": "application/vnd.github+json", "User-Agent": "NICO-hosted-assessment"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=25)
        except requests.RequestException as exc:
            return None, f"GitHub request failed: {exc}"
        if response.status_code >= 400:
            return None, f"GitHub returned {response.status_code}: {response.text[:240]}"
        try:
            return response.json(), None
        except ValueError as exc:
            return None, f"GitHub returned non-JSON response: {exc}"

    def get_repo(self, repo: str) -> tuple[dict[str, Any] | None, str | None]:
        data, error = self.get_json(f"{GITHUB_API}/repos/{repo}")
        return (data if isinstance(data, dict) else None), error

    def get_contents(self, repo: str, path: str) -> tuple[Any | None, str | None]:
        return self.get_json(f"{GITHUB_API}/repos/{repo}/contents/{path}")

    def get_tree(self, repo: str, sha: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(f"{GITHUB_API}/repos/{repo}/git/trees/{sha}", {"recursive": "1"})
        if error:
            return [], error
        tree = data.get("tree") if isinstance(data, dict) else []
        return [item for item in tree if isinstance(item, dict)], None

    def get_commits(self, repo: str, since: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(f"{GITHUB_API}/repos/{repo}/commits", {"since": since, "per_page": 100})
        return (data if isinstance(data, list) else []), error

    def get_pulls(self, repo: str, since_dt: datetime) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(f"{GITHUB_API}/repos/{repo}/pulls", {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100})
        if error:
            return [], error
        pulls = []
        for item in data if isinstance(data, list) else []:
            updated = item.get("updated_at") or ""
            try:
                updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
            except ValueError:
                updated_dt = _now()
            if updated_dt >= since_dt:
                pulls.append(item)
        return pulls, None

    def get_workflow_runs(self, repo: str, since: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(f"{GITHUB_API}/repos/{repo}/actions/runs", {"created": f">={since}", "per_page": 100})
        if error:
            return [], error
        runs = data.get("workflow_runs") if isinstance(data, dict) else []
        return [item for item in runs if isinstance(item, dict)], None


def file_text(client: GitHubAssessmentClient, repo: str, path: str) -> tuple[str | None, str | None]:
    data, error = client.get_contents(repo, path)
    if error:
        return None, error
    if not isinstance(data, dict) or data.get("type") != "file":
        return None, f"{path} is not a file or is unavailable"
    content = data.get("content") or ""
    encoding = data.get("encoding")
    if encoding == "base64":
        try:
            return base64.b64decode(content).decode("utf-8", errors="replace"), None
        except Exception as exc:
            return None, f"Failed to decode {path}: {exc}"
    return str(content), None


def fetch_repository_profile(client: GitHubAssessmentClient, repo: str, repo_meta: dict[str, Any]) -> dict[str, Any]:
    root, root_error = client.get_contents(repo, "")
    root_items = root if isinstance(root, list) else []
    tree_paths: list[str] = []
    tree_error = None
    default_branch = repo_meta.get("default_branch") or "main"
    branch_data, branch_error = client.get_json(f"{GITHUB_API}/repos/{repo}/branches/{default_branch}")
    sha = None
    if isinstance(branch_data, dict):
        sha = branch_data.get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
    if sha:
        tree, tree_error = client.get_tree(repo, sha)
        tree_paths = [item.get("path", "") for item in tree if item.get("type") == "blob"]
    else:
        tree_error = branch_error or "Default branch tree unavailable"
    candidate_paths = sorted(set(KNOWN_FILE_PATHS + tree_paths[:400]))
    files: dict[str, str] = {}
    unavailable: list[str] = []
    for path in candidate_paths:
        if not path or any(part in SKIP_PATH_PARTS for part in path.split("/")):
            continue
        if Path(path).suffix not in TEXT_SUFFIXES and path not in KNOWN_FILE_PATHS:
            continue
        if len(files) >= MAX_TEXT_FILES:
            unavailable.append(f"File scan truncated at {MAX_TEXT_FILES} text files; deeper scan requires worker mode.")
            break
        text, error = file_text(client, repo, path)
        if error or text is None:
            continue
        if len(text.encode("utf-8", errors="ignore")) > MAX_FILE_BYTES:
            unavailable.append(f"{path} skipped because it exceeds hosted text scan size limit.")
            continue
        files[path] = text
    return {"root_items": root_items, "root_error": root_error, "tree_paths": tree_paths, "tree_error": tree_error, "files": files, "unavailable": unavailable}


def _json_loads(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _dependency_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#") and not stripped.startswith("-"):
            lines.append(stripped)
    return lines


def _requirement_query(line: str) -> tuple[str, str] | None:
    stripped = line.split("#", 1)[0].strip()
    match = re.match(r"^([A-Za-z0-9_.-]+)(?:\[[^\]]+\])?\s*(==|~=|>=|<=|>|<)\s*([^;\s]+)", stripped)
    if not match:
        return None
    name, operator, version = match.groups()
    if operator != "==":
        return None
    return name, version


def _package_lock_exact_versions(path: str, payload: dict[str, Any]) -> list[tuple[str, str, str]]:
    versions: list[tuple[str, str, str]] = []
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        return versions
    for raw_name, item in packages.items():
        if not raw_name or raw_name == "" or not isinstance(item, dict):
            continue
        version = str(item.get("version") or "").strip()
        if not version:
            continue
        name = raw_name.split("node_modules/", 1)[-1]
        if name:
            versions.append((path, name, version))
    return versions


def osv_query_batch(packages: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], str | None]:
    if not packages:
        return [], None
    try:
        response = requests.post(OSV_API, json={"queries": packages[:100]}, timeout=30)
        if response.status_code >= 400:
            return [], f"OSV returned {response.status_code}: {response.text[:180]}"
        payload = response.json()
    except Exception as exc:
        return [], f"OSV request failed: {exc}"
    results = payload.get("results") if isinstance(payload, dict) else []
    findings: list[dict[str, Any]] = []
    for query, result in zip(packages, results if isinstance(results, list) else []):
        vulns = result.get("vulns") if isinstance(result, dict) else []
        if vulns:
            for vuln in vulns:
                if isinstance(vuln, dict):
                    findings.append({"package": query.get("package", {}).get("name"), "ecosystem": query.get("package", {}).get("ecosystem"), "version": query.get("version"), "id": vuln.get("id"), "summary": vuln.get("summary")})
    return findings, None


def _section_status(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def section(section_id: str, label: str, score: int, summary: str, evidence: list[str], unavailable: list[str], findings: list[str] | None = None) -> dict[str, Any]:
    return {"id": section_id, "label": label, "score": score, "status": _section_status(score), "summary": summary, "evidence": evidence, "findings": findings or [], "unavailable": unavailable}


def _append_if(items: list[str], value: str | None) -> None:
    if value:
        items.append(value)


def analyze_code_activity(commits: list[dict[str, Any]], pulls: list[dict[str, Any]], since: str, commit_error: str | None, pr_error: str | None, file_scan: dict[str, Any]) -> dict[str, Any]:
    commit_count = len(commits)
    pr_count = len(pulls)
    merged_count = sum(1 for pr in pulls if pr.get("merged_at"))
    open_count = sum(1 for pr in pulls if pr.get("state") == "open")


def run_github_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {"status": "blocked", "error": "Explicit authorization is required before NICO assesses a repository.", "safety_boundary": "Defensive-only. Authorized repositories only. No exploitation or destructive actions."}
    return _run_github_assessment_impl(payload)
