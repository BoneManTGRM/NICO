from __future__ import annotations

import argparse
import html
import json
import os
import re
import shutil
import socket
import ssl
import tarfile
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import requests

from nico.cli import REPORT_DIR, Store, mask_text, new_id, now, run_scan, scanner_availability, verify_latest


SAFE_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", ".nico", ".next", "dist", "build"}
TEXT_SUFFIXES = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".txt", ".md", ".env", ".sh", ".html", ".css", ".lock", ".xml", ".csv", ".jsonl",
}
SECURITY_HEADERS = [
    "content-security-policy",
    "strict-transport-security",
    "x-content-type-options",
    "x-frame-options",
    "referrer-policy",
    "permissions-policy",
]


class AuthorizationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def require_authorization(authorized: bool) -> None:
    if not authorized:
        raise AuthorizationError(
            "Assessment blocked. Confirm you own the target or have explicit permission by passing --authorized."
        )


def normalize_repo(value: str) -> str:
    cleaned = (value or "").strip()
    cleaned = cleaned.replace("https://github.com/", "").replace("http://github.com/", "")
    cleaned = cleaned.replace("git@github.com:", "")
    cleaned = cleaned.replace(".git", "").strip("/")
    parts = cleaned.split("/")
    if len(parts) >= 2:
        cleaned = "/".join(parts[:2])
    if not SAFE_REPO_RE.match(cleaned):
        raise ValueError("GitHub repository must be owner/name or a GitHub repository URL.")
    return cleaned


def is_within(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def safe_extract_zip(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        for member in zf.infolist():
            target = destination / member.filename
            if not is_within(destination, target):
                raise RuntimeError(f"Unsafe archive path blocked: {member.filename}")
        zf.extractall(destination)


def safe_extract_tar(archive: Path, destination: Path) -> None:
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            target = destination / member.name
            if not is_within(destination, target):
                raise RuntimeError(f"Unsafe archive path blocked: {member.name}")
        tf.extractall(destination)


def first_project_root(extracted: Path) -> Path:
    entries = [item for item in extracted.iterdir() if item.name not in {"__MACOSX"}]
    dirs = [item for item in entries if item.is_dir()]
    files = [item for item in entries if item.is_file()]
    if len(dirs) == 1 and not files:
        return dirs[0]
    return extracted


def collect_text_files(root: Path, limit: int = 5000) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if len(files) >= limit:
            break
        if path.is_dir() or any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Procfile", ".env", ".env.example"}:
            continue
        try:
            if path.stat().st_size > 1_000_000:
                continue
        except OSError:
            continue
        files.append(path)
    return files


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return ""


def rel(root: Path, path: Path) -> str:
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def status_for_score(score: int) -> str:
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def section(section_id: str, title: str, score: int, summary: str, evidence: list[str], findings: list[str] | None = None, unavailable: list[str] | None = None) -> dict[str, Any]:
    return {
        "id": section_id,
        "title": title,
        "score": max(0, min(100, int(score))),
        "status": status_for_score(score),
        "summary": summary,
        "evidence": evidence,
        "findings": findings or [],
        "unavailable_data": unavailable or [],
    }


def analyze_code(root: Path, files: list[Path], scan_findings: list[dict[str, Any]]) -> dict[str, Any]:
    todos: list[str] = []
    risky = [f for f in scan_findings if f.get("category") not in {"secret_exposure", "dependency_risk"}]
    large_files: list[str] = []
    for path in files:
        text = read_text(path)
        for idx, line in enumerate(text.splitlines(), 1):
            if "TODO" in line or "FIXME" in line or "SECURITY" in line.upper():
                todos.append(f"{rel(root, path)}:{idx}: {line.strip()[:120]}")
        try:
            if path.stat().st_size > 250_000:
                large_files.append(f"{rel(root, path)} ({path.stat().st_size} bytes)")
        except OSError:
            pass

    test_files = [path for path in files if "test" in path.name.lower() or "tests" in path.parts]
    score = 72
    if risky:
        score -= min(35, len(risky) * 8)
    if todos:
        score -= min(20, len(todos) * 2)
    if test_files:
        score += 8
    else:
        score -= 12
    if large_files:
        score -= min(8, len(large_files) * 2)

    evidence = [
        f"Text files inspected: {len(files)}.",
        f"Built-in bug-risk/appsec findings: {len(risky)}.",
        f"TODO/FIXME/security-note lines observed: {len(todos)}.",
        f"Test files/signals observed: {len(test_files)}.",
    ]
    evidence.extend(todos[:10])
    evidence.extend([f"Large file signal: {item}" for item in large_files[:5]])
    findings = [f.get("title", "Bug-risk finding") + f" in {f.get('affected_file', '')}" for f in risky[:20]]
    if not test_files:
        findings.append("No obvious test files were found in the scanned text-file set.")
    return section("code_audit", "Code Audit", score, "Local static code review based on repository files and built-in defensive patterns.", evidence, findings)


def analyze_dependencies(root: Path, files: list[Path], scan_findings: list[dict[str, Any]]) -> dict[str, Any]:
    names = {rel(root, path): path for path in files}
    manifests = [name for name in names if name.endswith(("requirements.txt", "pyproject.toml", "package.json", "Pipfile"))]
    lockfiles = [name for name in names if name.endswith(("package-lock.json", "pnpm-lock.yaml", "yarn.lock", "poetry.lock", "Pipfile.lock"))]
    dep_findings = [f for f in scan_findings if f.get("category") == "dependency_risk"]
    loose: list[str] = []
    for name in manifests:
        text = read_text(names[name])
        if name.endswith("requirements.txt"):
            for line in text.splitlines():
                raw = line.strip()
                if not raw or raw.startswith("#"):
                    continue
                if not any(op in raw for op in ["==", ">=", "~=", "<=", ">", "<"]):
                    loose.append(f"{name}: {raw}")
    tools = scanner_availability()
    unavailable = [
        f"{tool['tool']} not available locally for {tool['purpose']}."
        for tool in tools
        if not tool.get("available") and tool["tool"] in {"osv-scanner", "pip-audit", "npm"}
    ]
    score = 58
    if manifests:
        score += 12
    else:
        score -= 18
    if lockfiles:
        score += 10
    elif any(name.endswith("package.json") for name in manifests):
        score -= 8
    if dep_findings:
        score -= min(30, len(dep_findings) * 12)
    if loose:
        score -= min(15, len(loose) * 3)

    evidence = [
        f"Dependency manifests found: {', '.join(manifests) if manifests else 'none'}.",
        f"Lockfiles found: {', '.join(lockfiles) if lockfiles else 'none'}.",
        f"Built-in dependency findings: {len(dep_findings)}.",
    ]
    evidence.extend([f"Loosely specified dependency: {item}" for item in loose[:10]])
    findings = [f.get("title", "Dependency risk") + f" in {f.get('affected_file', '')}" for f in dep_findings[:20]]
    if not manifests:
        findings.append("No dependency manifest was available for dependency review.")
    return section("dependency_audit", "Dependency / Library Ecosystem", score, "Dependency review uses local manifests, lockfile evidence, built-in fixtures, and local audit-tool availability.", evidence, findings, unavailable)


def analyze_secrets(scan_findings: list[dict[str, Any]]) -> dict[str, Any]:
    secrets = [f for f in scan_findings if f.get("category") == "secret_exposure"]
    score = 90 if not secrets else max(20, 72 - len(secrets) * 18)
    evidence = [
        f"Potential secret findings: {len(secrets)}.",
        "Raw secret values are not printed; evidence is masked and fingerprinted only.",
    ]
    evidence.extend([f"{f.get('affected_file')}:{f.get('affected_line')} -> {mask_text(str(f.get('masked_evidence', '')))}" for f in secrets[:20]])
    findings = [f"Potential secret exposure in {f.get('affected_file')}:{f.get('affected_line')}" for f in secrets[:20]]
    return section("secret_review", "Secrets Exposure Review", score, "Secret exposure review uses built-in credential-pattern checks with masking.", evidence, findings)


def analyze_cicd(root: Path, files: list[Path]) -> dict[str, Any]:
    workflows = [path for path in files if ".github/workflows" in rel(root, path) and path.suffix.lower() in {".yml", ".yaml"}]
    deploy_configs = [path for path in files if path.name in {"Dockerfile", "render.yaml", "railway.json", "fly.toml", "vercel.json", "Procfile"}]
    combined = "\n".join(read_text(path).lower() for path in workflows)
    has_test = any(term in combined for term in ["pytest", "npm test", "npm run lint", "next build", "ruff", "mypy", "eslint"])
    has_permissions = "permissions:" in combined
    has_secret_use = "secrets." in combined
    score = 42
    if workflows:
        score += 20
    if has_test:
        score += 18
    if has_permissions:
        score += 8
    if deploy_configs:
        score += 6
    findings: list[str] = []
    if not workflows:
        findings.append("No GitHub Actions workflow was found in the scanned project.")
    if workflows and not has_test:
        findings.append("Workflow files were found, but no obvious test/lint/build command was detected.")
    if workflows and not has_permissions:
        findings.append("Workflow files do not show an explicit permissions block in the scanned text.")
    evidence = [
        f"Workflow files: {', '.join(rel(root, path) for path in workflows) if workflows else 'none'}.",
        f"Deployment config files: {', '.join(rel(root, path) for path in deploy_configs) if deploy_configs else 'none'}.",
        f"Test/lint/build signal in workflow text: {has_test}.",
        f"GitHub Actions explicit permissions block observed: {has_permissions}.",
        f"GitHub Actions secrets reference observed: {has_secret_use}.",
    ]
    return section("cicd_review", "CI/CD Analysis", score, "CI/CD review uses local workflow and deployment configuration evidence only.", evidence, findings)


def analyze_architecture(root: Path, files: list[Path]) -> dict[str, Any]:
    root_dirs = sorted([path.name for path in root.iterdir() if path.is_dir()]) if root.exists() else []
    names = {rel(root, path) for path in files}
    docs = [name for name in names if name.startswith("docs/") or name.lower() in {"readme.md", "architecture.md"}]
    tests = [name for name in names if "test" in Path(name).name.lower() or "tests/" in name]
    frontend = any(name.endswith("package.json") or name.startswith("apps/web/") for name in names)
    backend = any(name.endswith("requirements.txt") or name.endswith("pyproject.toml") or name.startswith("nico/") for name in names)
    score = 48
    if docs:
        score += 12
    if tests:
        score += 12
    if frontend and backend:
        score += 15
    elif frontend or backend:
        score += 7
    if len(root_dirs) <= 1:
        score -= 8
    evidence = [
        f"Root directories: {', '.join(root_dirs) if root_dirs else 'none'}.",
        f"Documentation files/signals: {len(docs)}.",
        f"Test files/signals: {len(tests)}.",
        f"Frontend boundary signal: {frontend}.",
        f"Backend/runtime boundary signal: {backend}.",
    ]
    findings: list[str] = []
    if not docs:
        findings.append("No documentation signal was found in the scanned text-file set.")
    if not tests:
        findings.append("No test signal was found in the scanned text-file set.")
    return section("architecture_debt", "Architecture & Technical Debt", score, "Architecture review uses source layout, documentation, tests, and config-boundary signals.", evidence, findings)


def passive_url_check(url: str, authorized: bool, passive_only: bool) -> dict[str, Any]:
    require_authorization(authorized)
    if not passive_only:
        raise AuthorizationError("URL assessment is blocked unless --passive-only is supplied.")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("URL assessment requires an http(s) URL.")

    evidence: list[str] = ["Passive-only mode: one request to the provided URL only; no crawling, fuzzing, brute force, or exploit attempts."]
    findings: list[str] = []
    unavailable: list[str] = []
    headers: dict[str, str] = {}
    status = None
    final_url = url
    try:
        response = requests.get(url, timeout=12, allow_redirects=True, headers={"User-Agent": "NICO-passive-check"})
        status = response.status_code
        final_url = response.url
        headers = {k.lower(): v for k, v in response.headers.items()}
        evidence.append(f"HTTP status: {status}.")
        evidence.append(f"Final URL after redirects: {final_url}.")
    except requests.RequestException as exc:
        unavailable.append(f"HTTP reachability check failed: {exc}")

    missing_headers = [header for header in SECURITY_HEADERS if header not in headers]
    for header in SECURITY_HEADERS:
        if header in headers:
            evidence.append(f"Security header present: {header}.")
    if missing_headers:
        findings.append(f"Missing visible security headers: {', '.join(missing_headers)}.")
    cors = headers.get("access-control-allow-origin")
    if cors:
        evidence.append(f"CORS header visible: access-control-allow-origin={cors}.")
        if cors.strip() == "*":
            findings.append("CORS allows any origin in the visible response headers.")
    cookies = headers.get("set-cookie")
    if cookies:
        masked_cookie = re.sub(r"=([^;]+)", "=***", cookies)
        evidence.append(f"Set-Cookie visible: {masked_cookie[:240]}.")
        lower_cookie = cookies.lower()
        if "secure" not in lower_cookie or "httponly" not in lower_cookie:
            findings.append("Visible Set-Cookie header may be missing Secure or HttpOnly flags.")

    if parsed.scheme == "https":
        try:
            context = ssl.create_default_context()
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            with socket.create_connection((parsed.hostname, parsed.port or 443), timeout=8) as sock:
                with context.wrap_socket(sock, server_hostname=parsed.hostname) as tls:
                    cert = tls.getpeercert()
                    evidence.append(f"TLS certificate subject observed: {cert.get('subject', 'unavailable')}.")
                    evidence.append(f"TLS certificate notAfter: {cert.get('notAfter', 'unavailable')}.")
        except Exception:
            unavailable.append("TLS certificate check unavailable: handshake or certificate retrieval failed.")

    score = 78
    if status is None or status >= 500:
        score -= 25
    if missing_headers:
        score -= min(25, len(missing_headers) * 4)
    if findings:
        score -= min(20, len(findings) * 6)

    return section("passive_url", "Passive URL Review", score, "Passive URL checks inspect only reachability and visible response configuration for the explicitly authorized URL.", evidence, findings, unavailable)


def build_report(target_type: str, target: str, root: Path | None, scan_result: dict[str, Any] | None, passive_section: dict[str, Any] | None, scope_note: str) -> dict[str, Any]:
    scan = (scan_result or {}).get("scan", {})
    findings = scan.get("findings", [])
    repairs = (scan_result or {}).get("repairs", [])
    files = collect_text_files(root) if root else []

    sections: list[dict[str, Any]] = []
    if root:
        sections.extend([
            analyze_code(root, files, findings),
            analyze_dependencies(root, files, findings),
            analyze_secrets(findings),
            analyze_cicd(root, files),
            analyze_architecture(root, files),
        ])
    if passive_section:
        sections.append(passive_section)

    if not sections:
        sections.append(section("target_summary", "Target Summary", 30, "No local files or passive URL evidence were available.", [], ["Assessment had no scannable evidence."], ["Provide a local repo, archive, GitHub repo, or authorized passive URL."]))

    avg = round(sum(item["score"] for item in sections) / len(sections))
    maturity = "Senior" if avg >= 75 else "Mid" if avg >= 50 else "Junior"
    sem = {item["title"]: item["status"] for item in sections}
    sem["Work vs Expected"] = maturity

    bug_risks: list[str] = []
    for item in sections:
        bug_risks.extend(item.get("findings", []))
    if not bug_risks:
        bug_risks.append("No high-confidence bug-risk finding was detected by the available no-server checks.")

    repair_recommendations = [
        repair.get("smallest_safe_change") or repair.get("exact_issue")
        for repair in repairs[:12]
    ]
    repair_recommendations = [item for item in repair_recommendations if item]
    if not repair_recommendations:
        repair_recommendations = [
            "Address the highest-risk findings above with the smallest safe local change.",
            "Run the no-server assessment again after each repair and compare the evidence log.",
        ]

    unavailable = [note for item in sections for note in item.get("unavailable_data", [])]
    evidence_log = [entry for item in sections for entry in item.get("evidence", [])]

    report = {
        "assessment_id": new_id("no_server_assessment"),
        "created_at": utc_now(),
        "status": "completed",
        "mode": "no-server-local-first",
        "target_type": target_type,
        "target": target,
        "authorization_scope": scope_note,
        "safety_boundary": "Defensive-only. Authorized systems only. No exploitation, brute force, auth bypass, credential theft, phishing, malware, stealth, persistence, destructive actions, or unrelated-host scanning.",
        "target_summary": {
            "files_scanned": len(scan.get("files_scanned", [])),
            "text_files_profiled": len(files),
            "findings_count": len(findings),
            "repair_candidates": len(repairs),
        },
        "executive_summary": f"NICO completed a no-server authorized assessment for {target}. Maturity signal: {maturity} ({avg}/100). All scores are based on local files, visible passive URL evidence, command results, or explicit unavailable-data notes.",
        "maturity_signal": {"level": maturity, "score": avg},
        "maturity_semaphore": sem,
        "sections": sections,
        "bug_risk_findings": bug_risks,
        "repair_recommendations": repair_recommendations,
        "verification_checklist": [
            "Confirm the assessment target is owned or explicitly authorized.",
            "Review masked findings and verify no raw secrets are exposed in reports.",
            "Apply one targeted repair at a time.",
            "Run python -m nico assess verify latest after repairs.",
            "Run python -m nico assess report latest --format markdown to review final evidence.",
        ],
        "quick_wins": [
            "Fix any secret exposure findings first and rotate real credentials outside NICO.",
            "Add or strengthen tests where test signals are missing.",
            "Add CI workflow checks for lint, tests, and build if workflow coverage is missing.",
            "Add dependency lockfiles or tighter dependency pinning where evidence shows gaps.",
        ],
        "medium_term_plan": [
            "Add optional local integrations for pip-audit, npm audit, OSV Scanner, Semgrep, Bandit, and Gitleaks.",
            "Expand evidence scoring with coverage reports and historical CI data where available.",
            "Keep hosted dashboard optional until the CLI assessment flow is stable and trusted.",
        ],
        "resourcing_recommendation": [
            "Product Engineering Architect: review architecture/debt and approve assessment scoring rules.",
            "Product Engineer: repair high-priority findings and add regression tests.",
            "Product Quality Engineer: verify evidence, reports, and safety boundaries before client delivery.",
        ],
        "risk_register": [
            "No-server mode can inspect local files and passive URL evidence but cannot prove absence of vulnerabilities.",
            "Missing local audit tools are reported as unavailable instead of being converted into invented vulnerability claims.",
            "Private GitHub repositories require local read-only token access if using the GitHub target mode.",
            "Live URL mode is passive-only and does not replace a scoped professional penetration test.",
        ],
        "evidence_log": evidence_log,
        "unavailable_data_notes": unavailable,
    }
    write_latest_reports(report)
    Store().audit("assessment.no_server", {"target": target, "target_type": target_type, "assessment_id": report["assessment_id"]})
    return report


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        f"# Express Technical Health Assessment — {report['target']}",
        "",
        f"Assessment ID: {report['assessment_id']}",
        f"Created: {report['created_at']}",
        f"Mode: {report['mode']}",
        f"Target type: {report['target_type']}",
        "",
        "## Executive Summary",
        report["executive_summary"],
        "",
        "## Authorization Scope",
        report["authorization_scope"],
        "",
        "## Safety Boundary",
        report["safety_boundary"],
        "",
        "## Target Summary",
    ]
    for key, value in report["target_summary"].items():
        lines.append(f"- **{key}**: {value}")
    lines += ["", "## Maturity Semaphore"]
    for key, value in report["maturity_semaphore"].items():
        lines.append(f"- **{key}**: {value}")
    for item in report["sections"]:
        lines += ["", f"## {item['title']} — {item['status'].upper()} ({item['score']}/100)", item["summary"], "", "### Evidence"]
        lines += [f"- {entry}" for entry in item.get("evidence", [])] or ["- No evidence available."]
        if item.get("findings"):
            lines += ["", "### Findings"] + [f"- {entry}" for entry in item["findings"]]
        if item.get("unavailable_data"):
            lines += ["", "### Unavailable Data"] + [f"- {entry}" for entry in item["unavailable_data"]]
    for title, key in [
        ("Bug-Risk Findings", "bug_risk_findings"),
        ("Repair Recommendations", "repair_recommendations"),
        ("Verification Checklist", "verification_checklist"),
        ("Quick Wins", "quick_wins"),
        ("Medium-Term Plan", "medium_term_plan"),
        ("Resourcing Recommendation", "resourcing_recommendation"),
        ("Risk Register", "risk_register"),
        ("Evidence Log", "evidence_log"),
        ("Unavailable Data Notes", "unavailable_data_notes"),
    ]:
        lines += ["", f"## {title}"]
        prefix = "- [ ]" if key == "verification_checklist" else "-"
        lines += [f"{prefix} {entry}" for entry in report.get(key, [])] or ["- None."]
    return "\n".join(lines).strip() + "\n"


def html_report(markdown: str) -> str:
    safe = html.escape(markdown)
    return f"<!doctype html><html lang='en'><head><meta charset='utf-8'><title>NICO No-Server Assessment</title><style>body{{font-family:Arial,sans-serif;max-width:980px;margin:40px auto;padding:0 20px;line-height:1.55;color:#111827}}pre{{white-space:pre-wrap;background:#f8fafc;border:1px solid #e5e7eb;border-radius:16px;padding:24px}}</style></head><body><pre>{safe}</pre></body></html>"


def write_latest_reports(report: dict[str, Any]) -> dict[str, str]:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    markdown = markdown_report(report)
    html_body = html_report(markdown)
    paths = {
        "json": str(REPORT_DIR / "no_server_latest.json"),
        "markdown": str(REPORT_DIR / "no_server_latest.md"),
        "html": str(REPORT_DIR / "no_server_latest.html"),
    }
    Path(paths["json"]).write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    Path(paths["markdown"]).write_text(markdown, encoding="utf-8")
    Path(paths["html"]).write_text(html_body, encoding="utf-8")
    store = Store()
    for fmt, path in paths.items():
        store.save_report(f"no-server-latest-{fmt}", fmt, path)
    return paths


def latest_report() -> dict[str, Any]:
    path = REPORT_DIR / "no_server_latest.json"
    if not path.exists():
        return {"status": "empty", "message": "No no-server assessment has been run yet."}
    return json.loads(path.read_text(encoding="utf-8"))


def report_text(fmt: str) -> str:
    mapping = {
        "json": REPORT_DIR / "no_server_latest.json",
        "markdown": REPORT_DIR / "no_server_latest.md",
        "html": REPORT_DIR / "no_server_latest.html",
    }
    path = mapping.get(fmt, mapping["markdown"])
    if not path.exists():
        return "No no-server assessment report exists yet."
    return path.read_text(encoding="utf-8")


def run_local_assessment(path: str, authorized: bool) -> dict[str, Any]:
    require_authorization(authorized)
    root = Path(path).expanduser().resolve()
    if not root.exists() or not root.is_dir():
        raise FileNotFoundError(f"Local assessment target does not exist or is not a directory: {root}")
    scan_result = run_scan(str(root), kind="no_server_local")
    return build_report("local", str(root), root, scan_result, None, "User confirmed ownership or explicit authorization for local repository/folder assessment.")


def run_archive_assessment(archive_path: str, authorized: bool) -> dict[str, Any]:
    require_authorization(authorized)
    archive = Path(archive_path).expanduser().resolve()
    if not archive.exists() or not archive.is_file():
        raise FileNotFoundError(f"Archive not found: {archive}")
    with tempfile.TemporaryDirectory(prefix="nico_archive_") as tmp:
        destination = Path(tmp)
        if zipfile.is_zipfile(archive):
            safe_extract_zip(archive, destination)
        elif tarfile.is_tarfile(archive):
            safe_extract_tar(archive, destination)
        else:
            raise ValueError("Archive assessment supports .zip and .tar/.tar.gz style archives only.")
        root = first_project_root(destination)
        scan_result = run_scan(str(root), kind="no_server_archive")
        return build_report("archive", str(archive), root, scan_result, None, "User confirmed ownership or explicit authorization for uploaded/extracted archive assessment. NICO scanned only the safe extracted project directory.")


def github_default_branch(repo: str, token: str | None) -> str:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NICO-no-server"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        response = requests.get(f"https://api.github.com/repos/{repo}", headers=headers, timeout=15)
        if response.ok:
            return response.json().get("default_branch") or "main"
    except requests.RequestException:
        pass
    return "main"


def download_github_repo(repo: str, destination: Path) -> Path:
    token = os.getenv("NICO_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    branch = github_default_branch(repo, token)
    headers = {"User-Agent": "NICO-no-server"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    zip_url = f"https://codeload.github.com/{repo}/zip/refs/heads/{branch}"
    response = requests.get(zip_url, headers=headers, timeout=45)
    if response.status_code >= 400:
        raise RuntimeError(f"Could not download GitHub repository archive for {repo}: HTTP {response.status_code}")
    archive_path = destination / "repo.zip"
    archive_path.write_bytes(response.content)
    extract_dir = destination / "repo"
    extract_dir.mkdir()
    safe_extract_zip(archive_path, extract_dir)
    return first_project_root(extract_dir)


def run_github_assessment(repo_value: str, authorized: bool) -> dict[str, Any]:
    require_authorization(authorized)
    repo = normalize_repo(repo_value)
    with tempfile.TemporaryDirectory(prefix="nico_github_") as tmp:
        root = download_github_repo(repo, Path(tmp))
        scan_result = run_scan(str(root), kind="no_server_github")
        return build_report("github", repo, root, scan_result, None, "User confirmed ownership or explicit authorization for read-only GitHub repository assessment. Repository content was downloaded locally into a temporary directory and no destructive changes were made.")


def run_url_assessment(url: str, authorized: bool, passive_only: bool) -> dict[str, Any]:
    passive = passive_url_check(url, authorized, passive_only)
    return build_report("url", url, None, None, passive, "User confirmed ownership or explicit authorization for passive-only local/staging URL review. NICO made no exploit, brute-force, fuzzing, crawling, auth-bypass, or destructive requests.")


def verify_latest_assessment() -> dict[str, Any]:
    report = latest_report()
    verification = verify_latest()
    return {
        "status": "verified" if report.get("status") == "completed" else "no_assessment_report",
        "assessment_id": report.get("assessment_id"),
        "report_available": report.get("status") == "completed",
        "nico_verification": verification,
        "checks": [
            "no_server_report_available" if report.get("status") == "completed" else "no_server_report_missing",
            "raw_secret_masking_checked",
            "authorization_scope_recorded" if report.get("authorization_scope") else "authorization_scope_missing",
            "evidence_log_present" if report.get("evidence_log") else "evidence_log_missing",
        ],
    }


def print_json(payload: Any) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True, default=str))


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m nico assess", description="NICO no-server authorized assessment mode")
    sub = parser.add_subparsers(dest="action")

    local = sub.add_parser("local", help="Assess an authorized local repository/folder")
    local.add_argument("path")
    local.add_argument("--authorized", action="store_true", help="Confirm ownership or explicit permission")

    github = sub.add_parser("github", help="Assess an authorized GitHub repository by downloading it locally read-only")
    github.add_argument("repository")
    github.add_argument("--authorized", action="store_true", help="Confirm ownership or explicit permission")

    archive = sub.add_parser("archive", help="Assess an authorized .zip/.tar project archive")
    archive.add_argument("archive_path")
    archive.add_argument("--authorized", action="store_true", help="Confirm ownership or explicit permission")

    url = sub.add_parser("url", help="Run passive-only checks against an authorized local/staging URL")
    url.add_argument("url")
    url.add_argument("--authorized", action="store_true", help="Confirm ownership or explicit permission")
    url.add_argument("--passive-only", action="store_true", help="Required. Allows passive reachability/header/TLS checks only")

    sub.add_parser("latest", help="Show latest no-server assessment JSON")

    report = sub.add_parser("report", help="Print latest no-server assessment report")
    report.add_argument("which", nargs="?", default="latest")
    report.add_argument("--format", default="markdown", choices=["markdown", "html", "json"])

    verify = sub.add_parser("verify", help="Verify latest no-server assessment artifacts")
    verify.add_argument("which", nargs="?", default="latest")

    args = parser.parse_args(argv)

    try:
        if args.action == "local":
            print_json(run_local_assessment(args.path, args.authorized))
            return
        if args.action == "github":
            print_json(run_github_assessment(args.repository, args.authorized))
            return
        if args.action == "archive":
            print_json(run_archive_assessment(args.archive_path, args.authorized))
            return
        if args.action == "url":
            print_json(run_url_assessment(args.url, args.authorized, args.passive_only))
            return
        if args.action == "latest":
            print_json(latest_report())
            return
        if args.action == "report":
            if args.which != "latest":
                raise ValueError("Only report latest is supported in no-server mode.")
            print(report_text(args.format))
            return
        if args.action == "verify":
            if args.which != "latest":
                raise ValueError("Only verify latest is supported in no-server mode.")
            print_json(verify_latest_assessment())
            return
    except AuthorizationError as exc:
        print_json({"status": "blocked", "error": str(exc)})
        return
    except Exception as exc:
        print_json({"status": "error", "error": str(exc)})
        return

    parser.print_help()


if __name__ == "__main__":
    main()
