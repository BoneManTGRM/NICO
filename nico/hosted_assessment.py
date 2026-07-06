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
    "README.md",
    "package.json",
    "apps/web/package.json",
    "package-lock.json",
    "apps/web/package-lock.json",
    "pnpm-lock.yaml",
    "apps/web/pnpm-lock.yaml",
    "yarn.lock",
    "apps/web/yarn.lock",
    "requirements.txt",
    "pyproject.toml",
    "Pipfile",
    "Pipfile.lock",
    "poetry.lock",
    "tsconfig.json",
    "apps/web/tsconfig.json",
    "pytest.ini",
    "Dockerfile",
    "Procfile",
    "render.yaml",
    "railway.json",
    "fly.toml",
    ".env.example",
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
        self.headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": "NICO-hosted-assessment",
        }
        if token:
            self.headers["Authorization"] = f"Bearer {token}"

    def get_json(self, url: str, params: dict[str, Any] | None = None) -> tuple[Any | None, str | None]:
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=25)
        except requests.RequestException as exc:
            return None, f"GitHub request failed: {exc}"
        if response.status_code >= 400:
            return None, f"GitHub returned {response.status_code}: {response.text[:300]}"
        try:
            return response.json(), None
        except ValueError:
            return None, "GitHub returned a non-JSON response"

    def repo_url(self, repo: str, path: str = "") -> str:
        return f"{GITHUB_API}/repos/{repo}{path}"

    def get_repo(self, repo: str) -> tuple[dict[str, Any] | None, str | None]:
        data, error = self.get_json(self.repo_url(repo))
        return (data if isinstance(data, dict) else None), error

    def get_commits(self, repo: str, since_iso: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(self.repo_url(repo, "/commits"), {"since": since_iso, "per_page": 100})
        if error:
            return [], error
        return data if isinstance(data, list) else [], None

    def get_pulls(self, repo: str, since: datetime) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(
            self.repo_url(repo, "/pulls"),
            {"state": "all", "sort": "updated", "direction": "desc", "per_page": 100},
        )
        if error:
            return [], error
        pulls: list[dict[str, Any]] = []
        if isinstance(data, list):
            for pr in data:
                updated_at = parse_dt(pr.get("updated_at"))
                if updated_at and updated_at >= since:
                    pulls.append(pr)
        return pulls, None

    def get_workflow_runs(self, repo: str, since_iso: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(
            self.repo_url(repo, "/actions/runs"),
            {"created": f">={since_iso}", "per_page": 100},
        )
        if error:
            return [], error
        if isinstance(data, dict) and isinstance(data.get("workflow_runs"), list):
            return data["workflow_runs"], None
        return [], "GitHub Actions runs response did not include workflow_runs."

    def get_contents(self, repo: str, path: str = "") -> tuple[Any | None, str | None]:
        url_path = f"/contents/{path}" if path else "/contents"
        return self.get_json(self.repo_url(repo, url_path))

    def get_text_file(self, repo: str, path: str) -> tuple[str | None, str | None]:
        data, error = self.get_contents(repo, path)
        if error:
            return None, error
        if not isinstance(data, dict) or data.get("type") != "file":
            return None, f"{path} is not a file"
        if int(data.get("size") or 0) > MAX_FILE_BYTES:
            return None, f"{path} is larger than hosted text-inspection limit."
        encoded = data.get("content") or ""
        try:
            return base64.b64decode(encoded).decode("utf-8", errors="replace"), None
        except Exception as exc:
            return None, f"Could not decode {path}: {exc}"

    def get_tree(self, repo: str, branch: str) -> tuple[list[dict[str, Any]], str | None]:
        data, error = self.get_json(self.repo_url(repo, f"/git/trees/{branch}"), {"recursive": "1"})
        if error:
            return [], error
        if isinstance(data, dict) and isinstance(data.get("tree"), list):
            return data["tree"], None
        return [], "Git tree was unavailable or not a list."


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def status_color(score: int, unavailable: bool = False) -> str:
    if unavailable:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def section(section_id: str, label: str, score: int, summary: str, evidence: list[str], unavailable: list[str] | None = None, findings: list[str] | None = None) -> dict[str, Any]:
    unavailable = unavailable or []
    findings = findings or []
    score = max(0, min(100, int(score)))
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": status_color(score, bool(unavailable) and score == 0),
        "summary": summary,
        "evidence": evidence,
        "findings": findings,
        "unavailable": unavailable,
    }


def list_dir_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item.get("name", "") for item in items if isinstance(item, dict)]


def should_fetch_path(path: str, size: int | None = None) -> bool:
    parts = set(path.split("/"))
    if parts & SKIP_PATH_PARTS:
        return False
    if size is not None and size > MAX_FILE_BYTES:
        return False
    if path in KNOWN_FILE_PATHS:
        return True
    name = path.rsplit("/", 1)[-1]
    if name in {"Dockerfile", "Procfile", ".env.example"}:
        return True
    suffix = "." + name.split(".", 1)[-1] if "." in name else ""
    if suffix not in TEXT_SUFFIXES:
        return False
    if any(path.startswith(prefix) for prefix in ["tests/", "nico/", "apps/web/app/", "apps/web/styles/", "docs/", ".github/workflows/"]):
        return True
    return path.count("/") <= 1


def fetch_repository_profile(client: GitHubAssessmentClient, repo: str, repo_meta: dict[str, Any]) -> dict[str, Any]:
    branch = repo_meta.get("default_branch") or "main"
    tree, tree_error = client.get_tree(repo, branch)
    root, root_error = client.get_contents(repo)
    root_items = list_dir_names(root)
    files: dict[str, str] = {}
    unavailable: list[str] = []
    if root_error:
        unavailable.append(f"Root listing unavailable: {root_error}")
    if tree_error:
        unavailable.append(f"Recursive file tree unavailable: {tree_error}")

    tree_paths: list[str] = []
    for item in tree:
        if not isinstance(item, dict) or item.get("type") != "blob":
            continue
        path = str(item.get("path") or "")
        tree_paths.append(path)
    candidates = [path for path in KNOWN_FILE_PATHS if path in tree_paths or path in {"README.md", "requirements.txt", "package.json"}]
    candidates.extend(
        path for path in tree_paths
        if path not in candidates and should_fetch_path(path, int(next((i.get("size") or 0 for i in tree if i.get("path") == path), 0)))
    )
    for path in candidates[:MAX_TEXT_FILES]:
        text, error = client.get_text_file(repo, path)
        if text is not None:
            files[path] = text
        elif path in KNOWN_FILE_PATHS:
            unavailable.append(error or f"Could not read {path}.")
    return {"root_items": root_items, "tree_paths": tree_paths, "files": files, "unavailable": unavailable}


def fetch_workflows(client: GitHubAssessmentClient, repo: str) -> tuple[dict[str, str], list[str]]:
    workflows: dict[str, str] = {}
    unavailable: list[str] = []
    items, error = client.get_contents(repo, ".github/workflows")
    if error:
        unavailable.append("No readable .github/workflows directory was found through the GitHub contents API.")
        return workflows, unavailable
    if not isinstance(items, list):
        unavailable.append(".github/workflows exists but was not returned as a directory listing.")
        return workflows, unavailable
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


def parse_requirements(text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    for line in text.splitlines():
        raw = line.strip()
        if not raw or raw.startswith("#") or raw.startswith("-"):
            continue
        match = re.match(r"([A-Za-z0-9_.-]+)\s*(==|~=|>=|<=|>|<)?\s*([^;#\s]+)?", raw)
        if match:
            deps.append({"name": match.group(1), "operator": match.group(2) or "", "version": match.group(3) or "", "ecosystem": "PyPI", "source": "requirements.txt"})
    return deps


def parse_package_json(path: str, text: str) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    try:
        data = json.loads(text)
    except ValueError:
        return deps
    for key in ["dependencies", "devDependencies", "peerDependencies"]:
        section = data.get(key)
        if isinstance(section, dict):
            for name, spec in section.items():
                version = str(spec).lstrip("^~>=<")
                deps.append({"name": name, "operator": str(spec)[:2], "version": version, "ecosystem": "npm", "source": f"{path}:{key}"})
    return deps


def collect_dependencies(files: dict[str, str]) -> list[dict[str, str]]:
    deps: list[dict[str, str]] = []
    if "requirements.txt" in files:
        deps.extend(parse_requirements(files["requirements.txt"]))
    for path, text in files.items():
        if path.endswith("package.json"):
            deps.extend(parse_package_json(path, text))
    return deps


def query_osv(dependencies: list[dict[str, str]]) -> tuple[list[str], list[str]]:
    pinned = [dep for dep in dependencies if dep.get("version") and dep.get("version") not in {"*", "latest"}]
    pinned = pinned[:75]
    if not pinned:
        return [], ["OSV lookup skipped because no exact dependency versions were available from the inspected manifests."]
    queries = [
        {"package": {"name": dep["name"], "ecosystem": dep["ecosystem"]}, "version": dep["version"]}
        for dep in pinned
    ]
    try:
        response = requests.post(OSV_API, json={"queries": queries}, timeout=20)
    except requests.RequestException as exc:
        return [], [f"OSV lookup unavailable: {exc}"]
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
            ids = ", ".join(str(v.get("id")) for v in vulns[:5] if isinstance(v, dict))
            evidence.append(f"OSV returned {len(vulns)} vulnerability record(s) for {dep['ecosystem']}:{dep['name']}@{dep['version']}: {ids}.")
    if not evidence:
        evidence.append(f"OSV returned no vulnerability records for {len(pinned)} pinned dependency query/queries.")
    return evidence, []


def mask_secret(value: str) -> str:
    if len(value) <= 8:
        return "***"
    return f"{value[:4]}...{value[-4:]}"


def scan_files(files: dict[str, str]) -> dict[str, Any]:
    todos: list[str] = []
    risks: list[str] = []
    secrets: list[str] = []
    test_paths = [path for path in files if "test" in path.lower() or path.startswith("tests/")]
    docs = [path for path in files if path.lower().endswith(".md") or path.startswith("docs/")]
    for path, text in files.items():
        for line_no, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            upper = stripped.upper()
            if "TODO" in upper or "FIXME" in upper or "SECURITY" in upper:
                todos.append(f"{path}:{line_no}: {stripped[:140]}")
            for name, pattern, message in RISK_PATTERNS:
                if pattern.search(line):
                    risks.append(f"{path}:{line_no}: {name} — {message}")
            for name, pattern in SECRET_PATTERNS:
                match = pattern.search(line)
                if match:
                    evidence = match.group(0)
                    secrets.append(f"{path}:{line_no}: potential {name} evidence {mask_secret(evidence)}")
    return {"todos": todos, "risks": risks, "secrets": secrets, "test_paths": test_paths, "docs": docs}


def analyze_dependencies(files: dict[str, str]) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    unavailable: list[str] = []
    score = 40
    dependencies = collect_dependencies(files)

    if "requirements.txt" in files:
        req_lines = [line.strip() for line in files["requirements.txt"].splitlines() if line.strip() and not line.strip().startswith("#")]
        evidence.append(f"requirements.txt found with {len(req_lines)} active dependency lines.")
        if any("==" in line or "~=" in line for line in req_lines):
            score += 12
        if any(line and not any(op in line for op in ["==", ">=", "~=", "<=", ">", "<"]) for line in req_lines):
            findings.append("Some Python dependencies appear unpinned or loosely specified.")
            score -= 7
    else:
        findings.append("No root requirements.txt found.")

    package_paths = [path for path in files if path.endswith("package.json")]
    for path in package_paths:
        parsed = parse_package_json(path, files[path])
        evidence.append(f"{path} found with {len(parsed)} npm dependency entries across dependency sections.")
        score += 8

    lockfiles = [path for path in files if path.endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock"))]
    if lockfiles:
        evidence.append(f"Lockfile evidence found: {', '.join(lockfiles)}.")
        score += 12
    elif package_paths:
        findings.append("package.json exists but no JavaScript lockfile was found in the checked paths.")
        score -= 10

    osv_evidence, osv_unavailable = query_osv(dependencies)
    evidence.extend(osv_evidence)
    unavailable.extend(osv_unavailable)
    if any("vulnerability record" in item for item in osv_evidence):
        findings.extend([item for item in osv_evidence if "vulnerability record" in item])
        score -= 12
    elif osv_evidence:
        score += 8

    unavailable.extend([
        "pip-audit, npm audit, and OSV Scanner CLI execution are not yet run inside a sandboxed worker; hosted review uses manifest parsing plus OSV API where possible.",
    ])
    summary = "Dependency manifests and lockfile evidence were inspected from repository files. OSV API is queried when exact dependency versions are available."
    return {"score": max(30, min(score, 92)), "summary": summary, "evidence": evidence + findings, "findings": findings, "unavailable": unavailable}


def analyze_ci(workflows: dict[str, str], workflow_unavailable: list[str], workflow_runs: list[dict[str, Any]], runs_error: str | None) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    unavailable = list(workflow_unavailable)
    score = 20
    combined = "\n".join(workflows.values()).lower()
    if workflows:
        evidence.append(f"GitHub Actions workflows found: {', '.join(workflows.keys())}.")
        score = 55
        if any(term in combined for term in ["pytest", "npm run lint", "next build", "npm test", "ruff", "mypy", "eslint"]):
            score += 18
            evidence.append("Workflow text includes test, lint, or build commands.")
        else:
            findings.append("Workflow files exist but no obvious test/lint/build command was detected.")
        if "permissions:" in combined:
            score += 7
            evidence.append("Workflow text includes explicit permissions blocks.")
        else:
            findings.append("Workflow files do not show explicit permissions blocks in inspected text.")
        if any(term in combined for term in ["deploy", "vercel", "render", "railway", "flyctl", "docker"]):
            score += 8
            evidence.append("Workflow text includes deployment-related commands or providers.")
        if "secrets." in combined:
            evidence.append("Workflow text references GitHub secrets, which is expected for controlled deploy credentials but should be reviewed.")
    else:
        evidence.append("No GitHub Actions workflow files were available for analysis.")
        findings.append("No CI/CD workflow files were found through GitHub contents access.")

    if runs_error:
        unavailable.append(f"Workflow run history unavailable: {runs_error}")
    else:
        recent = workflow_runs[:100]
        success = sum(1 for run in recent if run.get("conclusion") == "success")
        failed = sum(1 for run in recent if run.get("conclusion") in {"failure", "timed_out", "cancelled"})
        evidence.append(f"GitHub Actions workflow runs returned in assessment window: {len(recent)}; success={success}; non-success={failed}.")
        if recent:
            rate = success / max(1, success + failed)
            if rate >= 0.8:
                score += 8
            elif failed:
                findings.append("Recent workflow history contains non-success runs that should be reviewed for release reliability.")
                score -= 8
    return {"score": max(20, min(score, 95)), "summary": "CI/CD maturity is based on workflow configuration, automation keywords, permissions evidence, and available workflow run history.", "evidence": evidence + findings, "findings": findings, "unavailable": unavailable}


def analyze_architecture(root_items: list[str], tree_paths: list[str], files: dict[str, str]) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    score = 35
    for marker in ["nico", "apps", "tests", "docs", ".github"]:
        if marker in root_items:
            evidence.append(f"Repository root contains {marker}/.")
            score += 8
    if "README.md" in files:
        evidence.append("README.md is present and can support onboarding/operational review.")
        score += 10
    else:
        findings.append("README.md was not readable, reducing onboarding and maintenance evidence.")
    if "apps/web/package.json" in files:
        evidence.append("apps/web/package.json indicates a separate Next.js frontend package.")
        score += 8
    if "requirements.txt" in files or "pyproject.toml" in files:
        evidence.append("Python backend/runtime dependency boundary is present.")
        score += 7
    deployment = [path for path in tree_paths if path in {"Dockerfile", "Procfile", "render.yaml", "railway.json", "fly.toml", "vercel.json"} or path.endswith("vercel.json")]
    if deployment:
        evidence.append(f"Deployment manifest evidence: {', '.join(deployment[:8])}.")
        score += 8
    test_count = len([path for path in tree_paths if "test" in path.lower()])
    evidence.append(f"Repository tree test-path signal count: {test_count}.")
    if test_count < 3:
        findings.append("Test-path signal is low for a production assessment; verify actual coverage manually.")
        score -= 7
    source_count = len([path for path in tree_paths if path.endswith((".py", ".ts", ".tsx", ".js", ".jsx"))])
    evidence.append(f"Repository tree source-file signal count: {source_count}.")
    unavailable = ["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker that checks out the repo and runs language-specific analyzers."]
    return {"score": max(35, min(score, 94)), "summary": "Architecture review uses repository layout, source-tree signals, documentation evidence, test structure, and deployment manifests.", "evidence": evidence + findings, "findings": findings, "unavailable": unavailable}


def analyze_code_activity(commits: list[dict[str, Any]], pulls: list[dict[str, Any]], since_iso: str, commit_error: str | None, pr_error: str | None, file_scan: dict[str, Any]) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    unavailable: list[str] = []
    if commit_error:
        unavailable.append(f"Commit activity unavailable: {commit_error}")
    else:
        evidence.append(f"Commits returned since {since_iso}: {len(commits)}.")
    if pr_error:
        unavailable.append(f"Pull request activity unavailable: {pr_error}")
    else:
        merged = sum(1 for pr in pulls if pr.get("merged_at"))
        open_count = sum(1 for pr in pulls if pr.get("state") == "open")
        evidence.append(f"Pull requests updated in the assessment window: {len(pulls)}; merged={merged}; open={open_count}.")

    todos = file_scan.get("todos", [])
    risks = file_scan.get("risks", [])
    tests = file_scan.get("test_paths", [])
    evidence.append(f"Text files inspected for code-risk markers: TODO/FIXME/security notes={len(todos)}, risky pattern hits={len(risks)}, test-path signals={len(tests)}.")
    evidence.extend(todos[:8])
    evidence.extend(risks[:8])

    score = 45
    if commits:
        score += 12
    if len(commits) >= 20:
        score += 8
    if pulls:
        score += 12
    if len(pulls) >= 5:
        score += 8
    if not pulls:
        findings.append("No recent pull-request evidence was found; direct-to-main work may reduce review traceability.")
        score -= 8
    if risks:
        findings.extend(risks[:8])
        score -= min(18, len(risks) * 3)
    if todos:
        findings.append("TODO/FIXME/security-note markers require triage before client-ready delivery.")
        score -= min(8, len(todos))
    if tests:
        score += 7
    else:
        findings.append("No test-path signals were found in fetched text files.")
        score -= 10
    return {"score": max(25, min(score, 94)), "summary": "Code audit uses recent commit/PR metadata plus hosted source-pattern review from the authorized repository.", "evidence": evidence + findings, "findings": findings, "unavailable": unavailable}


def analyze_secrets(file_scan: dict[str, Any]) -> dict[str, Any]:
    secrets = file_scan.get("secrets", [])
    evidence = [f"Secret-pattern hits found in fetched text files: {len(secrets)}.", "Raw secret values are masked and never printed in hosted reports."]
    evidence.extend(secrets[:15])
    findings = ["Potential secret exposure requires immediate human review and credential rotation if confirmed."] if secrets else []
    score = 92 if not secrets else max(25, 75 - len(secrets) * 12)
    unavailable = ["Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog; hosted mode currently scans fetched file contents only."]
    return {"score": score, "summary": "Secrets review uses built-in masked secret-pattern detection on fetched repository files.", "evidence": evidence + findings, "findings": findings, "unavailable": unavailable}


def analyze_static(file_scan: dict[str, Any]) -> dict[str, Any]:
    risks = file_scan.get("risks", [])
    evidence = [f"Built-in static risk-pattern hits: {len(risks)}."]
    evidence.extend(risks[:20])
    findings = risks[:20]
    score = 90 if not risks else max(40, 86 - len(risks) * 5)
    unavailable = [
        "Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode; this section uses built-in pattern checks only.",
    ]
    return {"score": score, "summary": "Static analysis uses hosted built-in pattern checks and explicitly marks external analyzer execution unavailable until the worker is expanded.", "evidence": evidence, "findings": findings, "unavailable": unavailable}


def analyze_velocity_complexity(commits: list[dict[str, Any]], pulls: list[dict[str, Any]], tree_paths: list[str], timeframe_days: int) -> dict[str, Any]:
    source_files = [path for path in tree_paths if path.endswith((".py", ".ts", ".tsx", ".js", ".jsx"))]
    weekly_commits = round(len(commits) / max(1, timeframe_days / 7), 2)
    pr_ratio = round(len(pulls) / max(1, len(commits)), 2) if commits else 0
    evidence = [
        f"Commit velocity: {len(commits)} commits over {timeframe_days} days ({weekly_commits}/week).",
        f"Pull request traceability ratio: {len(pulls)} PRs / {len(commits)} commits = {pr_ratio}.",
        f"Source-file footprint from recursive tree: {len(source_files)} files.",
    ]
    findings: list[str] = []
    score = 55
    if weekly_commits >= 1:
        score += 10
    if len(pulls) >= 3:
        score += 12
    elif commits:
        findings.append("Commit activity exists but PR traceability is limited for work-vs-expected review.")
        score -= 6
    if len(source_files) > 150:
        findings.append("Source-file footprint is large enough to require deeper complexity analysis before final client claims.")
        score -= 4
    else:
        score += 6
    return {"score": max(35, min(score, 88)), "summary": "Work-vs-expected signal estimates maturity from velocity, PR traceability, and source-footprint evidence.", "evidence": evidence + findings, "findings": findings, "unavailable": ["Precise story-point expectation, reviewer seniority, and business-value mapping require stakeholder context and human review."]}


def maturity_signal(sections: list[dict[str, Any]]) -> dict[str, Any]:
    available = [s["score"] for s in sections if s.get("status") != "gray"]
    avg = round(sum(available) / len(available)) if available else 0
    if avg >= 82:
        level = "Senior"
        summary = "Evidence suggests mature delivery foundations with documented structure, automation, and low-risk signals, pending human validation."
    elif avg >= 58:
        level = "Mid"
        summary = "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability, test, dependency, or automation gaps."
    else:
        level = "Junior"
        summary = "Evidence suggests early-stage maturity or missing access to the signals needed for confident assessment."
    return {"level": level, "score": avg, "summary": summary}


def build_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"# Express Technical Health Assessment — {result['repository']}",
        "",
        f"Generated: {result['generated_at']}",
        f"Client: {result.get('client_name') or 'Not specified'}",
        f"Project: {result.get('project_name') or 'Not specified'}",
        f"Coverage target: {result['coverage_targets']['express_technical_health_assessment']['target']}",
        "",
        "## Executive Summary",
        result["executive_summary"],
        "",
        "## Human Review Requirement",
        "NICO can automate most evidence collection and draft reporting, but final client-facing conclusions, Q&A, business context, and resourcing decisions require human review.",
        "",
        "## Maturity Semaphore",
    ]
    for key, value in result["maturity_semaphore"].items():
        lines.append(f"- **{key}**: {value}")
    lines += ["", "## Assessment Sections"]
    for item in result["sections"]:
        lines += [
            f"### {item['label']} — {item['status'].upper()} ({item['score']}/100)",
            item["summary"],
            "",
            "Evidence:",
        ]
        for evidence in item.get("evidence", []):
            lines.append(f"- {evidence}")
        if item.get("findings"):
            lines.append("Findings:")
            for finding in item.get("findings", []):
                lines.append(f"- {finding}")
        for unavailable in item.get("unavailable", []):
            lines.append(f"- Unavailable: {unavailable}")
        lines.append("")
    for title, key in [
        ("Quick Wins", "quick_wins"),
        ("Medium-Term Plan", "medium_term_plan"),
        ("Resourcing Recommendation", "resourcing_recommendation"),
        ("Risk Register", "risk_register"),
        ("Verification Checklist", "verification_checklist"),
    ]:
        lines += [f"## {title}"]
        prefix = "- [ ]" if key == "verification_checklist" else "-"
        lines += [f"{prefix} {item}" for item in result[key]]
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_html(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>NICO Express Assessment</title><style>body{{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;line-height:1.55;color:#111827}}pre{{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;padding:24px}}</style></head>
<body><pre>{safe}</pre></body>
</html>"""


def build_pdf_base64(markdown: str) -> tuple[str | None, str | None]:
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
    except Exception as exc:
        return None, f"PDF export unavailable because reportlab is not installed: {exc}"
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter)
    width, height = letter
    y = height - 48
    pdf.setFont("Helvetica", 9)
    for raw_line in markdown.splitlines():
        wrapped = textwrap.wrap(raw_line, width=100) or [""]
        for line in wrapped:
            if y < 48:
                pdf.showPage()
                pdf.setFont("Helvetica", 9)
                y = height - 48
            pdf.drawString(48, y, line[:130])
            y -= 12
    pdf.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii"), None


def run_github_assessment(payload: dict[str, Any]) -> dict[str, Any]:
    if not payload.get("authorized"):
        return {
            "status": "blocked",
            "error": "Explicit authorization is required before NICO assesses a repository.",
            "safety_boundary": "Defensive-only. Authorized repositories only. No exploitation or destructive actions.",
        }

    try:
        repo = normalize_repository(payload.get("repository", ""))
    except ValueError as exc:
        return {"status": "blocked", "error": str(exc)}

    timeframe_days = int(payload.get("timeframe_days") or 180)
    timeframe_days = max(30, min(timeframe_days, 365))
    since = _now() - timedelta(days=timeframe_days)
    since_iso = _iso(since)

    client = GitHubAssessmentClient()
    repo_meta, repo_error = client.get_repo(repo)
    if repo_error or not repo_meta:
        return {
            "status": "blocked",
            "repository": repo,
            "error": f"Repository metadata unavailable: {repo_error}",
            "safety_boundary": "Check that the repo exists, is accessible, and that NICO_GITHUB_TOKEN/GITHUB_TOKEN is set for private repositories.",
        }

    profile = fetch_repository_profile(client, repo, repo_meta)
    workflows, workflow_unavailable = fetch_workflows(client, repo)
    commits, commit_error = client.get_commits(repo, since_iso)
    pulls, pr_error = client.get_pulls(repo, since)
    workflow_runs, runs_error = client.get_workflow_runs(repo, since_iso)
    files = profile["files"]
    file_scan = scan_files(files)

    code = analyze_code_activity(commits, pulls, since_iso, commit_error, pr_error, file_scan)
    deps = analyze_dependencies(files)
    secrets = analyze_secrets(file_scan)
    static = analyze_static(file_scan)
    ci = analyze_ci(workflows, workflow_unavailable, workflow_runs, runs_error)
    arch = analyze_architecture(profile["root_items"], profile["tree_paths"], files)
    velocity = analyze_velocity_complexity(commits, pulls, profile["tree_paths"], timeframe_days)

    sections = [
        section("code_audit", "Code Audit", code["score"], code["summary"], code["evidence"], code["unavailable"], code["findings"]),
        section("dependency_health", "Dependency / Library Ecosystem", deps["score"], deps["summary"], deps["evidence"], deps["unavailable"], deps["findings"]),
        section("secrets_review", "Secrets Exposure Review", secrets["score"], secrets["summary"], secrets["evidence"], secrets["unavailable"], secrets["findings"]),
        section("static_analysis", "Static Analysis", static["score"], static["summary"], static["evidence"], static["unavailable"], static["findings"]),
        section("ci_cd", "CI/CD Analysis", ci["score"], ci["summary"], ci["evidence"], ci["unavailable"], ci["findings"]),
        section("architecture_debt", "Architecture & Technical Debt", arch["score"], arch["summary"], arch["evidence"], arch["unavailable"], arch["findings"]),
        section("velocity_complexity", "Velocity / Complexity", velocity["score"], velocity["summary"], velocity["evidence"], velocity["unavailable"], velocity["findings"]),
    ]
    maturity = maturity_signal(sections)
    maturity_semaphore = {item["label"]: item["status"] for item in sections}
    maturity_semaphore["Work vs Expected"] = maturity["level"]

    executive_summary = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repo}. "
        f"The current maturity signal is {maturity['level']} ({maturity['score']}/100). "
        "Scores are evidence-bound to GitHub metadata, repository files, workflow configuration, OSV dependency responses where available, and explicit unavailable-data notes. "
        "This supports the higher-end realistic Express target, but final client delivery still requires human review."
    )

    quick_wins = [
        "Address any confirmed secret-pattern hit first and rotate real credentials outside NICO if applicable.",
        "Add lockfiles or tighter dependency pinning where manifest evidence shows gaps.",
        "Add or strengthen CI checks for lint, tests, dependency audit, static analysis, and production build where missing.",
        "Keep assessment reports evidence-bound and mark unavailable data instead of using placeholders.",
    ]
    medium_term_plan = [
        "Add a sandboxed worker that checks out authorized repositories and runs pip-audit, npm audit, gitleaks/trufflehog, Semgrep, Bandit, ESLint, and coverage tools.",
        "Add authenticated GitHub App installation flow for private authorized repositories and richer PR/review evidence.",
        "Expand Mid assessment modules for QA evidence intake, iOS/Android parity checklists, stakeholder notes, and 6-month roadmap generation.",
        "Add Retainer Ops modules for weekly status, monthly strategy, backlog health, release readiness, and approval-gated issue creation.",
    ]
    resourcing = [
        "Product Engineering Architect: validate maturity scoring, architecture/debt conclusions, and client-facing recommendations.",
        "Product Engineer: repair high-priority findings, add scanner workers, and maintain frontend/backend integrations.",
        "Product Quality Engineer: verify QA/parity evidence, report quality, safety boundaries, and final client readiness.",
    ]
    risk_register = [
        "Private repositories require backend GitHub credentials; the browser must never receive a GitHub token.",
        "Hosted servers cannot scan a user's local filesystem; hosted mode must use authorized repository APIs only.",
        "CLI scanners are marked unavailable until a sandboxed worker executes them against an authorized checkout.",
        "Production-impacting remediation must remain human-approved.",
    ]
    verification = [
        "Backend /health returns status ok.",
        "Frontend displays the configured backend URL and API health.",
        "Assessment request requires authorization checkbox before execution.",
        "Generated report includes evidence, findings, or unavailable-data notes for every scored area.",
        "No exploit, bypass, credential theft, stealth, persistence, or destructive behavior is present.",
    ]

    result: dict[str, Any] = {
        "status": "complete",
        "repository": repo,
        "generated_at": _iso(_now()),
        "client_name": payload.get("client_name") or "",
        "project_name": payload.get("project_name") or repo_meta.get("name", repo),
        "assessment_mode": payload.get("assessment_mode") or "express",
        "timeframe_days": timeframe_days,
        "coverage_targets": SERVICE_TARGETS,
        "repository_metadata": {
            "full_name": repo_meta.get("full_name"),
            "default_branch": repo_meta.get("default_branch"),
            "visibility": repo_meta.get("visibility"),
            "private": repo_meta.get("private"),
            "html_url": repo_meta.get("html_url"),
            "files_profiled": len(files),
            "tree_paths_seen": len(profile["tree_paths"]),
        },
        "executive_summary": executive_summary,
        "maturity_signal": maturity,
        "maturity_semaphore": maturity_semaphore,
        "sections": sections,
        "findings": [finding for item in sections for finding in item.get("findings", [])] or ["No high-confidence finding was returned by available hosted checks."],
        "repairs": [
            "Triage and repair confirmed findings in risk order, starting with secrets and dependency/CI gaps.",
            "Add scanner-worker execution for pip-audit, npm audit, Semgrep, Bandit, and gitleaks/trufflehog.",
            "Expand report review checklist before client-facing delivery.",
        ],
        "quick_wins": quick_wins,
        "medium_term_plan": medium_term_plan,
        "resourcing_recommendation": resourcing,
        "risk_register": risk_register,
        "verification_checklist": verification,
        "safety_boundary": "Defensive-only. Authorized repositories only. Read-only assessment. No exploitation or destructive actions.",
        "human_review_required": True,
    }
    markdown = build_markdown(result)
    pdf_base64, pdf_error = build_pdf_base64(markdown)
    reports: dict[str, Any] = {"markdown": markdown, "html": build_html(markdown)}
    if pdf_base64:
        reports["pdf_base64"] = pdf_base64
        reports["pdf_filename"] = f"nico-express-assessment-{repo.replace('/', '-')}.pdf"
    else:
        result.setdefault("unavailable_data_notes", []).append(pdf_error or "PDF export unavailable.")
    result["reports"] = reports
    return result
