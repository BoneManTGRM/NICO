from __future__ import annotations

import io
import json
import os
import re
import zipfile
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any

import requests

GITHUB_API = "https://api.github.com"
STALE_AFTER_DAYS = 14
MAX_ARTIFACT_BYTES = 800_000
MAX_FETCHED_RUNS = 20

EXPECTED_ARTIFACTS = [
    {"source": "python_dependency_report", "artifact_name": "audit-results", "workflow_name": "NICO CI", "summary": "Python dependency audit output."},
    {"source": "frontend_npm_audit", "artifact_name": "frontend-audit-results", "workflow_name": "Audit Evidence", "summary": "Frontend npm audit output."},
    {"source": "audit_evidence_workflow", "artifact_name": "audit-evidence-results", "workflow_name": "Audit Evidence", "summary": "Dedicated Audit Evidence workflow output."},
]

DEPENDENCY_SOURCES = {"python_dependency_report", "frontend_npm_audit"}


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc)
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def _now_from_payload(payload: dict[str, Any]) -> datetime:
    parsed = _parse_dt(payload.get("generated_at") or payload.get("created_at"))
    return parsed or datetime.now(timezone.utc)


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, sort_keys=True)
    except TypeError:
        return str(value)


def _json_or_none(text: str) -> Any | None:
    try:
        return json.loads(text)
    except Exception:
        return None


def _github_token() -> str:
    return os.getenv("NICO_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN") or ""


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "NICO-artifact-evidence"}
    token = _github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _normalize_repo(value: Any) -> str:
    repo = str(value or "").strip()
    repo = repo.replace("https://github.com/", "").replace("http://github.com/", "").replace("git@github.com:", "").replace(".git", "").strip("/")
    parts = repo.split("/")
    if len(parts) >= 2:
        repo = "/".join(parts[:2])
    return repo if re.match(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$", repo) else ""


def _artifact_fetch_enabled(payload: dict[str, Any]) -> bool:
    if payload.get("disable_github_artifact_fetch"):
        return False
    return bool(_github_token() and _normalize_repo(payload.get("repository") or payload.get("source_scope")))


def _download_artifact_files(repo: str, artifact_id: int) -> dict[str, str]:
    response = requests.get(f"{GITHUB_API}/repos/{repo}/actions/artifacts/{artifact_id}/zip", headers=_headers(), timeout=25)
    if response.status_code >= 400 or len(response.content) > MAX_ARTIFACT_BYTES:
        return {}
    files: dict[str, str] = {}
    try:
        with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
            for name in archive.namelist():
                if not name.lower().endswith((".json", ".txt", ".xml", ".log")):
                    continue
                data = archive.read(name)
                if len(data) > MAX_ARTIFACT_BYTES:
                    continue
                files[name] = data.decode("utf-8", errors="replace")
    except Exception:
        return {}
    return files


def _raw_artifact(source: str, artifact_name: str, workflow_name: str, timestamp: Any, status: Any, content: Any) -> dict[str, Any]:
    return {"source": source, "artifact_name": artifact_name, "workflow_name": workflow_name, "timestamp": timestamp, "status": status or "", "content": content}


def _entries_from_artifact_zip(name: str, workflow_name: str, timestamp: Any, status: Any, files: dict[str, str]) -> list[dict[str, Any]]:
    name_l = name.lower()
    entries: list[dict[str, Any]] = []
    combined = "\n".join(files.values()) if files else ""
    if name_l == "audit-evidence-results":
        entries.append(_raw_artifact("audit_evidence_workflow", name, workflow_name, timestamp, status, "audit evidence workflow success" if str(status).lower() == "success" else combined))
    for filename, content in files.items():
        file_l = filename.lower()
        if "pip-audit" in file_l:
            entries.append(_raw_artifact("python_dependency_report", "audit-results", workflow_name, timestamp, status, content))
        elif "npm-audit" in file_l or "npm" in file_l:
            entries.append(_raw_artifact("frontend_npm_audit", "frontend-audit-results", workflow_name, timestamp, status, content))
    if not entries:
        source = _detect_source(name, workflow_name, combined)
        entries.append(_raw_artifact(source, name, workflow_name, timestamp, status, combined))
    return entries


def _fetch_github_action_artifacts(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not _artifact_fetch_enabled(payload):
        return []
    repo = _normalize_repo(payload.get("repository") or payload.get("source_scope"))
    try:
        runs_response = requests.get(f"{GITHUB_API}/repos/{repo}/actions/runs", headers=_headers(), params={"per_page": MAX_FETCHED_RUNS}, timeout=25)
        if runs_response.status_code >= 400:
            return []
        runs = runs_response.json().get("workflow_runs", [])
    except Exception:
        return []
    raw: list[dict[str, Any]] = []
    wanted_workflows = {item["workflow_name"].lower() for item in EXPECTED_ARTIFACTS} | {"security audit evidence"}
    wanted_names = {item["artifact_name"].lower() for item in EXPECTED_ARTIFACTS}
    for run in runs:
        workflow_name = str(run.get("name") or "")
        if workflow_name.lower() not in wanted_workflows:
            continue
        run_id = run.get("id")
        if not run_id:
            continue
        try:
            artifacts_response = requests.get(f"{GITHUB_API}/repos/{repo}/actions/runs/{run_id}/artifacts", headers=_headers(), timeout=25)
            if artifacts_response.status_code >= 400:
                continue
            artifacts = artifacts_response.json().get("artifacts", [])
        except Exception:
            continue
        for artifact in artifacts:
            name = str(artifact.get("name") or "")
            if not name or name.lower() not in wanted_names:
                continue
            files = _download_artifact_files(repo, int(artifact.get("id") or 0))
            raw.extend(_entries_from_artifact_zip(name, workflow_name, artifact.get("updated_at") or artifact.get("created_at") or run.get("updated_at"), run.get("conclusion") or run.get("status") or "", files))
    return raw


def _expand_supplied_artifact(raw: Any) -> list[Any]:
    if not isinstance(raw, dict):
        return [raw]
    name = str(raw.get("artifact_name") or raw.get("name") or raw.get("filename") or "")
    workflow = str(raw.get("workflow_name") or raw.get("workflow") or raw.get("source_workflow") or "unknown")
    content = raw.get("content") or raw.get("text") or raw.get("output") or raw.get("json") or raw.get("body")
    text = _as_text(content)
    if name.lower() != "audit-evidence-results":
        return [raw]
    expanded = [dict(raw, source="audit_evidence_workflow")]
    if "pip-audit" in text.lower() or '"dependencies"' in text:
        expanded.append(dict(raw, source="python_dependency_report", artifact_name="audit-results"))
    if "npm-audit" in text.lower() or '"metadata"' in text:
        expanded.append(dict(raw, source="frontend_npm_audit", artifact_name="frontend-audit-results"))
    return expanded


def _collect_raw_artifacts(payload: dict[str, Any]) -> list[Any]:
    candidates: list[Any] = []
    for key in ("evidence_artifacts", "ci_evidence_artifacts", "artifact_outputs", "audit_artifacts"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(value)
        elif value:
            candidates.append(value)
    readiness = payload.get("evidence_readiness")
    if isinstance(readiness, dict):
        for key in ("evidence_artifacts", "ci_evidence_artifacts", "artifact_outputs", "audit_artifacts"):
            value = readiness.get(key)
            if isinstance(value, list):
                candidates.extend(value)
            elif value:
                candidates.append(value)
    if not candidates:
        candidates.extend(_fetch_github_action_artifacts(payload))
    expanded: list[Any] = []
    for candidate in candidates:
        expanded.extend(_expand_supplied_artifact(candidate))
    return expanded


def _detect_source(name: str, workflow_name: str, text: str) -> str:
    name_l = name.lower()
    workflow_l = workflow_name.lower()
    haystack = f"{name_l} {workflow_l} {text[:400].lower()}"
    if name_l == "audit-results" and workflow_l in {"nico ci", "audit evidence", "security audit evidence"}:
        return "python_dependency_report"
    if name_l == "frontend-audit-results" or "npm audit" in haystack or "npm-audit" in haystack or "package-lock" in haystack:
        return "frontend_npm_audit"
    if name_l == "audit-evidence-results" or "audit evidence" in haystack or "audit-evidence" in haystack:
        return "audit_evidence_workflow"
    if "pip-audit" in haystack or "python" in haystack or "requirements" in haystack:
        return "python_dependency_report"
    return "unknown_artifact"


def _count_pip_audit_vulns(data: Any) -> int | None:
    if not isinstance(data, dict):
        return None
    if isinstance(data.get("dependencies"), list):
        return sum(len(dep.get("vulns") or []) for dep in data["dependencies"] if isinstance(dep, dict))
    if isinstance(data.get("vulnerabilities"), list):
        return len(data["vulnerabilities"])
    return None


def _count_npm_audit_vulns(data: Any) -> int | None:
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


def _status_from_content(source: str, text: str, declared_status: str) -> tuple[str, list[str], str]:
    lower = text.lower()
    data = _json_or_none(text)
    if declared_status in {"missing", "unavailable", "skipped"}:
        return "unavailable", ["Artifact was marked unavailable by the producer."], "Artifact status is unavailable; no clean claim can be made."
    if declared_status in {"failure", "failed", "error", "timeout", "cancelled"}:
        return "failed", ["Artifact producer reported a failed audit run."], "Artifact status indicates the audit did not pass."
    if not text.strip():
        return "unavailable", ["Artifact metadata exists but no parseable content was supplied."], "Workflow or artifact metadata alone is not proof that an audit passed."
    if source == "audit_evidence_workflow" and declared_status == "success":
        return "passed", [], "Audit Evidence workflow completed successfully and uploaded a parseable evidence artifact."
    if isinstance(data, dict) and str(data.get("status") or "").lower() in {"pip-audit unavailable", "npm audit unavailable", "unavailable"}:
        return "unavailable", [str(data.get("status"))], "Artifact content says the audit was unavailable."
    vuln_count: int | None = None
    if source == "python_dependency_report":
        vuln_count = _count_pip_audit_vulns(data)
    elif source == "frontend_npm_audit":
        vuln_count = _count_npm_audit_vulns(data)
    if vuln_count is not None:
        if vuln_count == 0:
            return "passed", [], "Artifact content parsed successfully and reported zero dependency vulnerabilities."
        return "failed", [f"Artifact content reported {vuln_count} dependency vulnerabilit{'y' if vuln_count == 1 else 'ies'}."], f"Artifact content reported {vuln_count} dependency vulnerabilit{'y' if vuln_count == 1 else 'ies'}."
    match = re.search(r"(\d+)\s+vulnerabilit", lower)
    if match:
        count = int(match.group(1))
        if count == 0:
            return "passed", [], "Artifact text reported zero vulnerabilities."
        return "failed", [f"Artifact text reported {count} vulnerabilities."], f"Artifact text reported {count} vulnerabilities."
    if any(term in lower for term in ("no vulnerabilities", "0 vulnerabilities", "zero vulnerabilities", "audit passed", "success")):
        return "passed", [], "Artifact text indicates the audit passed."
    if any(term in lower for term in ("vulnerability", "critical", "high severity", "moderate severity", "audit failed", "error")):
        return "failed", ["Artifact text contains failure or vulnerability language that requires review."], "Artifact text contains failure or vulnerability language."
    return "unavailable", ["Artifact content could not be classified as clean or failed."], "Artifact content was present but not enough to prove a clean audit."


def _normalize_one(raw: Any, now: datetime) -> dict[str, Any]:
    item = raw if isinstance(raw, dict) else {"content": raw}
    name = str(item.get("artifact_name") or item.get("name") or item.get("filename") or "artifact")
    workflow_name = str(item.get("workflow_name") or item.get("workflow") or item.get("source_workflow") or "unknown")
    content = item.get("content") or item.get("text") or item.get("output") or item.get("json") or item.get("body")
    text = _as_text(content)
    source = str(item.get("source") or _detect_source(name, workflow_name, text))
    timestamp = _parse_dt(item.get("timestamp") or item.get("created_at") or item.get("updated_at") or item.get("completed_at"))
    declared_status = str(item.get("status") or item.get("conclusion") or "").lower()
    status, findings, summary = _status_from_content(source, text, declared_status)
    stale = bool(timestamp and (now - timestamp).days > STALE_AFTER_DAYS)
    if stale and status == "passed":
        status = "stale"
        findings.append(f"Artifact is older than {STALE_AFTER_DAYS} days and cannot prove current clean status.")
    confidence = "high" if status in {"passed", "failed"} else "limited"
    return {"source": source, "artifact_name": name, "workflow_name": workflow_name, "timestamp": timestamp.isoformat().replace("+00:00", "Z") if timestamp else None, "status": status, "summary": summary, "findings": findings, "confidence": confidence, "missing": False, "stale": stale, "affects_score": status in {"passed", "failed"}}


def normalize_evidence_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    now = _now_from_payload(payload)
    artifacts = [_normalize_one(raw, now) for raw in _collect_raw_artifacts(payload)]
    seen = {item["source"] for item in artifacts}
    for expected in EXPECTED_ARTIFACTS:
        if expected["source"] not in seen:
            artifacts.append({"source": expected["source"], "artifact_name": expected["artifact_name"], "workflow_name": expected["workflow_name"], "timestamp": None, "status": "missing", "summary": f"Missing expected artifact: {expected['summary']}", "findings": ["Expected evidence artifact was not supplied or fetchable."], "confidence": "limited", "missing": True, "stale": False, "affects_score": False})
    counts: dict[str, int] = {}
    for artifact in artifacts:
        counts[artifact["status"]] = counts.get(artifact["status"], 0) + 1
    summary = {"total": len(artifacts), "passed": counts.get("passed", 0), "failed": counts.get("failed", 0), "missing": counts.get("missing", 0), "stale": counts.get("stale", 0), "unavailable": counts.get("unavailable", 0), "score_affecting": sum(1 for item in artifacts if item.get("affects_score")), "rule": "Workflow presence alone does not improve scores; only parsed artifact content can affect scoring."}
    return {"artifacts": artifacts, "summary": summary}


def _find_section(sections: list[dict[str, Any]], section_id: str) -> dict[str, Any] | None:
    return next((item for item in sections if item.get("id") == section_id), None)


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def apply_evidence_artifact_scoring(result: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    normalized = normalize_evidence_artifacts(output)
    output["evidence_artifacts"] = normalized["artifacts"]
    output["evidence_artifact_summary"] = normalized["summary"]
    sections = [item for item in output.get("sections", []) or [] if isinstance(item, dict)]
    dependency = _find_section(sections, "dependency_health")
    ci = _find_section(sections, "ci_cd")
    dependency_passes = 0
    dependency_failed = False
    for artifact in normalized["artifacts"]:
        source = artifact.get("source")
        status = artifact.get("status")
        name = artifact.get("artifact_name") or "artifact"
        workflow = artifact.get("workflow_name") or "workflow"
        note = f"Evidence artifact {name} from {workflow}: status={status}; {artifact.get('summary')}"
        findings = artifact.get("findings") or []
        if source in DEPENDENCY_SOURCES and dependency is not None:
            dependency.setdefault("evidence", [])
            dependency.setdefault("findings", [])
            dependency.setdefault("unavailable", [])
            sources = set(dependency.get("evidence_sources") or [])
            if status == "passed":
                _append_unique(dependency["evidence"], note)
                sources.add("dependency_intelligence")
                dependency_passes += 1
            elif status == "failed":
                dependency_failed = True
                _append_unique(dependency["findings"], note)
                for finding in findings:
                    _append_unique(dependency["findings"], str(finding))
            elif status in {"stale", "unavailable"}:
                _append_unique(dependency["unavailable"], note)
            dependency["evidence_sources"] = sorted(sources)
        if source == "audit_evidence_workflow" and ci is not None:
            ci.setdefault("evidence", [])
            ci.setdefault("findings", [])
            ci.setdefault("unavailable", [])
            sources = set(ci.get("evidence_sources") or [])
            if status == "passed":
                _append_unique(ci["evidence"], note)
                sources.add("workflow_runs")
                if int(ci.get("score") or 0) < 88 and not ci.get("findings"):
                    ci["score"] = 88
                    ci["status"] = "green"
            elif status == "failed":
                _append_unique(ci["findings"], note)
                for finding in findings:
                    _append_unique(ci["findings"], str(finding))
                ci["score"] = min(int(ci.get("score") or 0), 68)
                ci["status"] = "yellow"
            elif status in {"stale", "unavailable"}:
                _append_unique(ci["unavailable"], note)
            ci["evidence_sources"] = sorted(sources)
    if dependency is not None:
        current_score = int(dependency.get("score") or 0)
        if dependency_failed:
            dependency["score"] = min(current_score, 64)
            dependency["status"] = "yellow"
        elif dependency_passes >= 2 and not dependency.get("findings"):
            dependency["score"] = max(current_score, 88)
            dependency["status"] = "green"
        elif dependency_passes == 1 and not dependency.get("findings"):
            dependency["score"] = max(current_score, 82)
            dependency["status"] = "green"
    output["sections"] = sections
    return output
