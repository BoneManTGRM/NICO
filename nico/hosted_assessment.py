import base64
import html
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import requests


GITHUB_API = "https://api.github.com"
SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


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
            response = requests.get(url, headers=self.headers, params=params, timeout=20)
        except requests.RequestException as exc:
            return None, f"GitHub request failed: {exc}"
        if response.status_code >= 400:
            message = response.text[:300]
            return None, f"GitHub returned {response.status_code}: {message}"
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
        data, error = self.get_json(
            self.repo_url(repo, "/commits"),
            {"since": since_iso, "per_page": 100},
        )
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

    def get_contents(self, repo: str, path: str = "") -> tuple[Any | None, str | None]:
        url_path = f"/contents/{path}" if path else "/contents"
        return self.get_json(self.repo_url(repo, url_path))

    def get_text_file(self, repo: str, path: str) -> tuple[str | None, str | None]:
        data, error = self.get_contents(repo, path)
        if error:
            return None, error
        if not isinstance(data, dict) or data.get("type") != "file":
            return None, f"{path} is not a file"
        encoded = data.get("content") or ""
        try:
            return base64.b64decode(encoded).decode("utf-8", errors="replace"), None
        except Exception as exc:  # defensive decode guard
            return None, f"Could not decode {path}: {exc}"


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


def section(section_id: str, label: str, score: int, summary: str, evidence: list[str], unavailable: list[str] | None = None) -> dict[str, Any]:
    unavailable = unavailable or []
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": status_color(score, bool(unavailable) and score == 0),
        "summary": summary,
        "evidence": evidence,
        "unavailable": unavailable,
    }


def list_dir_names(items: Any) -> list[str]:
    if not isinstance(items, list):
        return []
    return [item.get("name", "") for item in items if isinstance(item, dict)]


def fetch_known_files(client: GitHubAssessmentClient, repo: str) -> dict[str, str]:
    paths = [
        "README.md",
        "package.json",
        "apps/web/package.json",
        "requirements.txt",
        "pyproject.toml",
        "Pipfile",
        "pnpm-lock.yaml",
        "package-lock.json",
        "yarn.lock",
        "tsconfig.json",
        "apps/web/tsconfig.json",
        "pytest.ini",
        "Dockerfile",
        "render.yaml",
        "railway.json",
        "fly.toml",
    ]
    files: dict[str, str] = {}
    for path in paths:
        text, error = client.get_text_file(repo, path)
        if text is not None:
            files[path] = text
    return files


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


def analyze_dependencies(files: dict[str, str]) -> dict[str, Any]:
    evidence: list[str] = []
    findings: list[str] = []
    score = 35

    if "requirements.txt" in files:
        req_lines = [line.strip() for line in files["requirements.txt"].splitlines() if line.strip() and not line.strip().startswith("#")]
        evidence.append(f"requirements.txt found with {len(req_lines)} active dependency lines.")
        if any(">=" in line or "==" in line or "~=" in line for line in req_lines):
            score += 15
        if any(line and not any(op in line for op in ["==", ">=", "~=", "<=", ">", "<"]) for line in req_lines):
            findings.append("Some Python dependencies appear unpinned or loosely specified.")
    else:
        findings.append("No root requirements.txt found.")

    package_paths = [path for path in files if path.endswith("package.json")]
    for path in package_paths:
        text = files[path]
        dep_count = text.count('"dependencies"') + text.count('"devDependencies"')
        evidence.append(f"{path} found with dependency sections detected: {dep_count}.")
        score += 10

    lockfiles = [path for path in files if path.endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock"))]
    if lockfiles:
        evidence.append(f"JavaScript lockfile found: {', '.join(lockfiles)}.")
        score += 10
    elif package_paths:
        findings.append("package.json exists but no JavaScript lockfile was found in the checked paths.")

    unavailable = [
        "Hosted assessment does not yet run live vulnerability databases such as OSV or pip-audit; dependency risk is based on manifest evidence only."
    ]
    summary = "Dependency manifests were inspected from repository files."
    if findings:
        summary += " Follow-up review is needed for pinning and vulnerability status."
    return {"score": min(score, 85), "summary": summary, "evidence": evidence + findings, "unavailable": unavailable}


def analyze_ci(workflows: dict[str, str], workflow_unavailable: list[str]) -> dict[str, Any]:
    evidence: list[str] = []
    score = 20
    if workflows:
        evidence.append(f"GitHub Actions workflows found: {', '.join(workflows.keys())}.")
        combined = "\n".join(workflows.values()).lower()
        score = 55
        if any(term in combined for term in ["pytest", "npm run lint", "next build", "npm test", "ruff", "mypy"]):
            score += 20
            evidence.append("Workflow text includes test, lint, or build commands.")
        if any(term in combined for term in ["deploy", "vercel", "render", "railway", "flyctl"]):
            score += 10
            evidence.append("Workflow text includes deployment-related commands or providers.")
    else:
        evidence.append("No GitHub Actions workflow files were available for analysis.")
    return {
        "score": min(score, 90),
        "summary": "CI/CD maturity is based on readable workflow configuration and automation keywords.",
        "evidence": evidence,
        "unavailable": workflow_unavailable,
    }


def analyze_architecture(root_items: list[str], files: dict[str, str]) -> dict[str, Any]:
    evidence: list[str] = []
    score = 35
    for marker in ["nico", "apps", "tests", "docs"]:
        if marker in root_items:
            evidence.append(f"Repository root contains {marker}/.")
            score += 10
    if "README.md" in files:
        evidence.append("README.md documents NICO purpose, safety boundary, quick start, hosted frontend/backend setup, and CLI commands.")
        score += 10
    if "apps/web/package.json" in files:
        evidence.append("apps/web/package.json indicates a separate Next.js frontend package.")
        score += 10
    if "requirements.txt" in files:
        evidence.append("requirements.txt indicates a Python backend/runtime dependency boundary.")
        score += 5
    summary = "Architecture review uses repository layout and known deployment manifests as evidence."
    unavailable = ["Deep static analysis, call-graph inspection, and complexity scoring require expanded source traversal in a later backend worker."]
    return {"score": min(score, 90), "summary": summary, "evidence": evidence, "unavailable": unavailable}


def analyze_code_activity(commits: list[dict[str, Any]], pulls: list[dict[str, Any]], since_iso: str, commit_error: str | None, pr_error: str | None) -> dict[str, Any]:
    evidence: list[str] = []
    unavailable: list[str] = []
    if commit_error:
        unavailable.append(f"Commit activity unavailable: {commit_error}")
    else:
        evidence.append(f"Commits returned since {since_iso}: {len(commits)}.")
    if pr_error:
        unavailable.append(f"Pull request activity unavailable: {pr_error}")
    else:
        evidence.append(f"Pull requests updated in the assessment window: {len(pulls)}.")

    score = 40
    if commits:
        score += 15
    if len(commits) >= 10:
        score += 10
    if pulls:
        score += 15
    if len(pulls) >= 3:
        score += 10
    if not pulls:
        evidence.append("No recent pull-request evidence was found; direct-to-main work may reduce review traceability.")
    return {
        "score": min(score, 90),
        "summary": "Code audit uses recent commit and PR metadata from the authorized repository.",
        "evidence": evidence,
        "unavailable": unavailable,
    }


def maturity_signal(sections: list[dict[str, Any]]) -> dict[str, Any]:
    available = [s["score"] for s in sections if s.get("status") != "gray"]
    avg = round(sum(available) / len(available)) if available else 0
    if avg >= 75:
        level = "Senior"
        summary = "Evidence suggests a mature delivery system with documented structure and automation signals."
    elif avg >= 50:
        level = "Mid"
        summary = "Evidence suggests useful foundations exist, but operating maturity depends on closing traceability and automation gaps."
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
        "",
        "## Executive Summary",
        result["executive_summary"],
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
        for unavailable in item.get("unavailable", []):
            lines.append(f"- Unavailable: {unavailable}")
        lines.append("")
    lines += ["## Quick Wins"] + [f"- {item}" for item in result["quick_wins"]]
    lines += ["", "## Medium-Term Plan"] + [f"- {item}" for item in result["medium_term_plan"]]
    lines += ["", "## Resourcing Recommendation"] + [f"- {item}" for item in result["resourcing_recommendation"]]
    lines += ["", "## Risk Register"] + [f"- {item}" for item in result["risk_register"]]
    lines += ["", "## Verification Checklist"] + [f"- [ ] {item}" for item in result["verification_checklist"]]
    return "\n".join(lines).strip() + "\n"


def build_html(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"""<!doctype html>
<html lang=\"en\">
<head><meta charset=\"utf-8\"><title>NICO Express Assessment</title><style>body{{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;line-height:1.55;color:#111827}}pre{{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:14px;padding:24px}}</style></head>
<body><pre>{safe}</pre></body>
</html>"""


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
    if repo_error:
        return {
            "status": "blocked",
            "repository": repo,
            "error": f"Repository metadata unavailable: {repo_error}",
            "safety_boundary": "Check that the repo exists, is accessible, and that NICO_GITHUB_TOKEN/GITHUB_TOKEN is set for private repositories.",
        }

    root, root_error = client.get_contents(repo)
    root_items = list_dir_names(root)
    files = fetch_known_files(client, repo)
    workflows, workflow_unavailable = fetch_workflows(client, repo)
    commits, commit_error = client.get_commits(repo, since_iso)
    pulls, pr_error = client.get_pulls(repo, since)

    code = analyze_code_activity(commits, pulls, since_iso, commit_error, pr_error)
    deps = analyze_dependencies(files)
    ci = analyze_ci(workflows, workflow_unavailable)
    arch = analyze_architecture(root_items, files)

    sections = [
        section("code_audit", "Code Audit", code["score"], code["summary"], code["evidence"], code["unavailable"]),
        section("dependency_health", "Dependency / Library Ecosystem", deps["score"], deps["summary"], deps["evidence"], deps["unavailable"]),
        section("ci_cd", "CI/CD Analysis", ci["score"], ci["summary"], ci["evidence"], ci["unavailable"]),
        section("architecture_debt", "Architecture & Technical Debt", arch["score"], arch["summary"], arch["evidence"], arch["unavailable"]),
    ]
    maturity = maturity_signal(sections)

    maturity_semaphore = {item["label"]: item["status"] for item in sections}
    maturity_semaphore["Work vs Expected"] = maturity["level"]

    executive_summary = (
        f"NICO completed an authorized hosted Express Technical Health Assessment for {repo}. "
        f"The current maturity signal is {maturity['level']} ({maturity['score']}/100). "
        "Scores are evidence-bound to GitHub metadata, repository files, workflow configuration, and explicit unavailable-data notes."
    )

    quick_wins = [
        "Connect the hosted frontend to a live backend URL through NEXT_PUBLIC_NICO_API_URL.",
        "Keep Cloudflare DNS for app.nicoaudit.com as DNS-only while Vercel verifies the domain.",
        "Add or strengthen CI checks for lint, tests, dependency audit, and production build if missing.",
        "Keep assessment reports evidence-bound and mark unavailable data instead of using placeholders.",
    ]
    medium_term_plan = [
        "Add a background worker for deeper repository traversal, dependency audit execution, and report persistence.",
        "Add authenticated GitHub App installation flow for private authorized repositories.",
        "Add PDF export after Markdown and HTML reports are stable and reviewed.",
        "Add issue/PR creation only behind explicit human approval gates.",
    ]
    resourcing = [
        "Product Engineering Architect: define assessment criteria, architecture scoring, and technical roadmap.",
        "Product Engineer: implement backend GitHub assessment, frontend dashboard, and report exports.",
        "Product Quality Engineer: verify evidence, unavailable-data handling, safety boundaries, and report quality.",
    ]
    risk_register = [
        "Private repositories require backend GitHub credentials; the browser must never receive a GitHub token.",
        "Hosted servers cannot scan a user's local filesystem; hosted mode must use authorized repository APIs only.",
        "Dependency vulnerability status remains incomplete until an actual audit source such as OSV or pip-audit is integrated.",
        "Production-impacting remediation must remain human-approved.",
    ]
    verification = [
        "Backend /health returns status ok.",
        "Frontend displays the configured backend URL and API health.",
        "Assessment request requires authorization checkbox before execution.",
        "Generated report includes evidence or unavailable-data notes for every scored area.",
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
        "repository_metadata": {
            "full_name": repo_meta.get("full_name"),
            "default_branch": repo_meta.get("default_branch"),
            "visibility": repo_meta.get("visibility"),
            "private": repo_meta.get("private"),
            "html_url": repo_meta.get("html_url"),
        },
        "executive_summary": executive_summary,
        "maturity_signal": maturity,
        "maturity_semaphore": maturity_semaphore,
        "sections": sections,
        "findings": [evidence for item in sections for evidence in item.get("evidence", []) if "missing" in evidence.lower() or "no " in evidence.lower() or "unavailable" in evidence.lower()],
        "repairs": [
            "Add missing CI workflow checks where evidence shows coverage gaps.",
            "Add lockfiles or tighter dependency pinning where package manifests are present without lock evidence.",
            "Expand backend worker coverage for deeper architecture and dependency analysis.",
        ],
        "quick_wins": quick_wins,
        "medium_term_plan": medium_term_plan,
        "resourcing_recommendation": resourcing,
        "risk_register": risk_register,
        "verification_checklist": verification,
        "safety_boundary": "Defensive-only. Authorized repositories only. Read-only assessment. No exploitation or destructive actions.",
    }
    markdown = build_markdown(result)
    result["reports"] = {"markdown": markdown, "html": build_html(markdown)}
    return result
