from __future__ import annotations

import io
import json
import os
import re
import zipfile
from copy import deepcopy
from typing import Any

import requests

GITHUB_API = "https://api.github.com"
MAX_ARTIFACT_BYTES = 1_200_000
MAX_RUNS = 30
SCANNER_SECTION_IDS = ["dependency_health", "secrets_review", "static_analysis", "ci_cd"]


def _token() -> str:
    return os.getenv("NICO_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or ""


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NICO-scanner-artifact-scoring"}
    token = _token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _repo(value: Any) -> str:
    repo = str(value or "").strip()
    repo = repo.replace("https://github.com/", "").replace("http://github.com/", "").replace("git@github.com:", "").replace(".git", "").strip("/")
    parts = repo.split("/")
    if len(parts) >= 2:
        repo = "/".join(parts[:2])
    return repo if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo) else ""


def _get_json(url: str, params: dict[str, Any] | None = None) -> Any | None:
    try:
        response = requests.get(url, headers=_headers(), params=params, timeout=25)
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    try:
        return response.json()
    except ValueError:
        return None


def _artifact_files(repo: str, artifact_id: int) -> dict[str, Any]:
    try:
        response = requests.get(f"{GITHUB_API}/repos/{repo}/actions/artifacts/{artifact_id}/zip", headers=_headers(), timeout=30)
    except requests.RequestException:
        return {}
    if response.status_code >= 400 or len(response.content) > MAX_ARTIFACT_BYTES:
        return {}
    files: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                lower = name.lower()
                if not lower.endswith(".json"):
                    continue
                raw = archive.read(name)
                if len(raw) > MAX_ARTIFACT_BYTES:
                    continue
                text = raw.decode("utf-8", errors="replace")
                try:
                    files[lower.rsplit("/", 1)[-1]] = json.loads(text)
                except ValueError:
                    files[lower.rsplit("/", 1)[-1]] = {"raw_text": text[:4000]}
    except Exception:
        return {}
    return files


def scanner_artifact_access_status(repository: Any = "") -> dict[str, Any]:
    repo = _repo(repository or os.getenv("NICO_DEFAULT_REPOSITORY") or "")
    token_configured = bool(_token())
    if not repo:
        return {
            "status": "repo_unavailable",
            "token_configured": token_configured,
            "repository": "unavailable",
            "message": "Scanner artifact scoring needs an owner/name repository before it can inspect GitHub Actions artifacts.",
        }
    if not token_configured:
        return {
            "status": "token_missing",
            "token_configured": False,
            "repository": repo,
            "message": "Set NICO_GITHUB_TOKEN or GITHUB_TOKEN in the deployed backend to let NICO read GitHub Actions artifacts for scoring.",
        }
    data = _get_json(f"{GITHUB_API}/repos/{repo}/actions/runs", {"per_page": 1})
    if not isinstance(data, dict):
        return {
            "status": "api_unavailable",
            "token_configured": True,
            "repository": repo,
            "message": "GitHub Actions artifact metadata could not be read with the configured token.",
        }
    return {
        "status": "ok",
        "token_configured": True,
        "repository": repo,
        "message": "GitHub Actions artifact metadata is accessible to the deployed backend.",
    }


def _fetch_recent_artifacts(repo: str) -> dict[str, Any]:
    if not _token() or not repo:
        return {}
    data = _get_json(f"{GITHUB_API}/repos/{repo}/actions/runs", {"per_page": MAX_RUNS})
    runs = data.get("workflow_runs", []) if isinstance(data, dict) else []
    wanted_names = {"security-audit-evidence", "audit-evidence-results", "frontend-audit-results", "audit-results"}
    out: dict[str, Any] = {}
    for run in runs:
        if run.get("conclusion") not in {"success", "failure"}:
            continue
        run_id = run.get("id")
        if not run_id:
            continue
        artifacts_data = _get_json(f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/artifacts")
        artifacts = artifacts_data.get("artifacts", []) if isinstance(artifacts_data, dict) else []
        for artifact in artifacts:
            name = str(artifact.get("name") or "").lower()
            if name not in wanted_names or name in out:
                continue
            files = _artifact_files(repo, int(artifact.get("id") or 0))
            if files:
                out[name] = {"workflow": run.get("name"), "conclusion": run.get("conclusion"), "created_at": artifact.get("created_at"), "files": files}
        if all(name in out for name in wanted_names):
            break
    return out


def _section(sections: list[dict[str, Any]], section_id: str) -> dict[str, Any] | None:
    return next((item for item in sections if item.get("id") == section_id), None)


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _pip_count(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("dependencies"), list):
        return sum(len(item.get("vulns") or []) for item in data["dependencies"] if isinstance(item, dict))
    if isinstance(data.get("vulnerabilities"), list):
        return len(data["vulnerabilities"])
    return None


def _npm_count(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None
    metadata = data.get("metadata")
    if isinstance(metadata, dict):
        vulns = metadata.get("vulnerabilities")
        if isinstance(vulns, dict) and "total" in vulns:
            return int(vulns.get("total") or 0)
    vulnerabilities = data.get("vulnerabilities")
    if isinstance(vulnerabilities, dict):
        return len(vulnerabilities)
    if isinstance(vulnerabilities, list):
        return len(vulnerabilities)
    return None


def _result_count(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None
    for key in ("results", "findings", "errors"):
        value = data.get(key)
        if isinstance(value, list):
            return len(value)
    return None


def _credential_count(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None
    value = data.get("findings")
    if isinstance(value, list):
        return len(value)
    return None


def _lift_section(section: dict[str, Any], source: str, note: str, score: int = 88) -> None:
    section.setdefault("evidence", [])
    section.setdefault("findings", [])
    section.setdefault("unavailable", [])
    _append_unique(section["evidence"], note)
    sources = set(section.get("evidence_sources") or [])
    sources.add(source)
    section["evidence_sources"] = sorted(sources)
    if not section.get("findings"):
        section["score"] = max(int(section.get("score") or 0), score)
        section["status"] = "green"


def _flag_section(section: dict[str, Any], source: str, note: str, score_cap: int = 68) -> None:
    section.setdefault("findings", [])
    _append_unique(section["findings"], note)
    sources = set(section.get("evidence_sources") or [])
    sources.add(source)
    section["evidence_sources"] = sorted(sources)
    section["score"] = min(int(section.get("score") or 0), score_cap)
    section["status"] = "yellow"


def _mark_artifact_access_unavailable(sections: list[dict[str, Any]], status: dict[str, Any]) -> None:
    message = str(status.get("message") or "GitHub Actions artifact access is unavailable; scanner artifacts cannot affect scoring.")
    note = f"GitHub Actions artifact access unavailable: {message}"
    for section_id in SCANNER_SECTION_IDS:
        section = _section(sections, section_id)
        if section is not None:
            section.setdefault("unavailable", [])
            _append_unique(section["unavailable"], note)


def apply_scanner_artifact_scoring(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    repo = _repo(output.get("repository") or output.get("source_scope"))
    sections = [item for item in output.get("sections", []) or [] if isinstance(item, dict)]
    access = scanner_artifact_access_status(repo)
    artifacts = _fetch_recent_artifacts(repo) if access.get("status") == "ok" else {}
    if not artifacts:
        output["sections"] = sections
        output["scanner_artifact_summary"] = {
            "status": "artifact_access_unavailable" if access.get("status") != "ok" else "no_recent_artifacts",
            "artifact_sets": [],
            "files": [],
            "access": access,
            "rule": "Scanner artifacts can affect scores only when current parseable GitHub Actions artifacts are available.",
        }
        _mark_artifact_access_unavailable(sections, access)
        return output

    deps = _section(sections, "dependency_health")
    secrets = _section(sections, "secrets_review")
    static = _section(sections, "static_analysis")
    ci = _section(sections, "ci_cd")

    files: dict[str, Any] = {}
    for artifact in artifacts.values():
        files.update(artifact.get("files") or {})

    if deps is not None:
        pip = files.get("pip-audit.json") or files.get("pip-audit-results.json")
        npm = files.get("npm-audit.json") or files.get("npm-audit-results.json")
        pip_count = _pip_count(pip) if pip is not None else None
        npm_count = _npm_count(npm) if npm is not None else None
        if pip_count == 0 and npm_count == 0:
            _lift_section(deps, "dependency_intelligence", "Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities.", 90)
        elif pip_count and pip_count > 0:
            _flag_section(deps, "dependency_intelligence", f"Parsed pip-audit artifact reported {pip_count} vulnerability finding(s).", 68)
        elif npm_count and npm_count > 0:
            _flag_section(deps, "dependency_intelligence", f"Parsed npm-audit artifact reported {npm_count} vulnerability finding(s).", 64)

    if secrets is not None:
        credential = files.get("credential-scan.json")
        count = _credential_count(credential)
        if count == 0:
            _lift_section(secrets, "secret_scanning", "Parsed credential-scan artifact reported zero high-confidence credential findings.", 90)
        elif count and count > 0:
            _flag_section(secrets, "secret_scanning", f"Parsed credential-scan artifact reported {count} high-confidence credential finding(s).", 60)

    if static is not None:
        bandit = files.get("bandit.json")
        semgrep = files.get("semgrep.json")
        bandit_count = _result_count(bandit) if bandit is not None else None
        semgrep_count = _result_count(semgrep) if semgrep is not None else None
        if bandit_count == 0 and semgrep_count == 0:
            _lift_section(static, "static_analysis", "Parsed Bandit and Semgrep artifacts reported zero scanner findings.", 90)
        elif bandit_count and bandit_count > 0:
            _flag_section(static, "static_analysis", f"Parsed Bandit artifact reported {bandit_count} finding(s).", 70)
        elif semgrep_count and semgrep_count > 0:
            _flag_section(static, "static_analysis", f"Parsed Semgrep artifact reported {semgrep_count} finding(s).", 70)

    if ci is not None:
        _lift_section(ci, "workflow_runs", f"Parsed {len(artifacts)} current GitHub Actions evidence artifact set(s) from authorized repository workflow runs.", 90)

    output["sections"] = sections
    output["scanner_artifact_summary"] = {"status": "parsed", "access": access, "artifact_sets": sorted(artifacts.keys()), "files": sorted(files.keys())}
    return output
