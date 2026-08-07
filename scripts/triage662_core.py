from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

EXPECTED = {"static": 586, "dependency": 59, "secret": 17}  # nosec B105 - candidate counts, not credentials


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return value


def repo_path(value: Any) -> str:
    path = str(value or "").replace("\\", "/")
    while path.startswith("./"):
        path = path[2:]
    lower = path.casefold()
    marker = "/repo/"
    if marker in lower:
        path = path[lower.rfind(marker) + len(marker):]
        lower = path.casefold()
    roots = (".github/", "apps/", "config/", "docs/", "nico/", "scripts/", "tests/")
    indexes = [lower.rfind(root) for root in roots if lower.rfind(root) >= 0]
    return path[max(indexes):] if indexes else path


def stable_id(prefix: str, *parts: Any) -> str:
    text = "\x1f".join(" ".join(str(part or "").split()) for part in parts)
    return f"{prefix}-{hashlib.sha256(text.encode()).hexdigest()[:20].upper()}"


def scope(path: str) -> str:
    lower = path.casefold()
    if lower == ".env.example" or lower.endswith(".example"):
        return "example_template"
    if lower.startswith("tests/") or "/tests/" in f"/{lower}":
        return "test"
    if lower.startswith(("nico/", "apps/", "scripts/")):
        return "source"
    return "other"


def validate_run(run: dict[str, Any], expected_sha: str | None = None) -> str:
    sha = str(run.get("target_commit_sha") or "").lower()
    if len(sha) != 40 or (expected_sha and sha != expected_sha):
        raise ValueError(f"Invalid scanner target SHA: {sha}")
    if run.get("scanner_evidence_ready") is not True or run.get("required_scanner_completion") is not True:
        raise ValueError("Scanner run is not evidence-ready.")
    if run.get("raw_artifact_capture_complete") is not True or run.get("raw_artifact_retention_complete") is not True:
        raise ValueError("Raw scanner evidence is incomplete.")
    incomplete = {key: value for key, value in (run.get("required_scanner_statuses") or {}).items() if value != "completed"}
    if incomplete:
        raise ValueError(f"Required scanners are incomplete: {incomplete}")
    return sha


def findings(run: dict[str, Any], tool: str) -> list[dict[str, Any]]:
    values = (((run.get("tools") or {}).get(tool) or {}).get("findings") or [])
    return [dict(item) for item in values if isinstance(item, dict)]


def fingerprint(run: dict[str, Any], tool: str) -> str:
    return str((run.get("deterministic_fingerprints") or {}).get(tool) or "")


def common_record(*, candidate_id: str, cluster_id: str, category: str, scanner: str,
                  rule: str, title: str, path: str, line: int | None, severity: str,
                  confidence: str, proposed: str, rationale: str, sha: str,
                  evidence_fingerprint: str) -> dict[str, Any]:
    return {
        "candidate_id": candidate_id, "cluster_id": cluster_id, "category": category,
        "scanner": scanner, "rule_id": rule, "title": " ".join(title.split())[:400],
        "path": path, "line": line, "severity": severity, "confidence": confidence,
        "evidence_scope": scope(path), "proposed_disposition": proposed,
        "rationale": rationale, "confirmed_material": False,
        "human_review_required": True, "human_approved": False,
        "source_evidence_fingerprint": evidence_fingerprint, "target_commit_sha": sha,
    }


def static_candidates(run: dict[str, Any], sha: str) -> list[dict[str, Any]]:
    output = []
    for item in findings(run, "bandit"):
        path = repo_path(item.get("filename"))
        line = int(item.get("line_number") or 0) or None
        rule = str(item.get("test_id") or item.get("test_name") or "bandit")
        output.append(common_record(
            candidate_id=stable_id("NICO-STATIC", sha, rule, path, line, item.get("col_offset")),
            cluster_id=stable_id("NICO-CLUSTER-STATIC", rule, item.get("test_name")),
            category="static", scanner="bandit", rule=rule,
            title=str(item.get("issue_text") or item.get("test_name") or "Bandit candidate"),
            path=path, line=line, severity=str(item.get("issue_severity") or "unknown").casefold(),
            confidence=str(item.get("issue_confidence") or "unknown").casefold(),
            proposed="source_review_required",
            rationale=("Bandit reported a source-level candidate at the exact assessed SHA. "
                       "The automated signal does not establish exploitability, so human source review remains required."),
            sha=sha, evidence_fingerprint=fingerprint(run, "bandit"),
        ))
    return output


def osv_severity(package: dict[str, Any], vuln_id: str) -> str:
    scores = []
    for group in package.get("groups") or []:
        ids = {str(value) for value in (group.get("ids") or []) + (group.get("aliases") or [])}
        if vuln_id in ids:
            try:
                scores.append(float(group.get("max_severity")))
            except (TypeError, ValueError):
                pass
    score = max(scores) if scores else -1
    return "critical" if score >= 9 else "high" if score >= 7 else "medium" if score >= 4 else "low" if score >= 0 else "unknown"


def dependency_candidates(run: dict[str, Any], sha: str) -> list[dict[str, Any]]:
    output = []
    for result in findings(run, "osv-scanner"):
        packages = result.get("packages")
        if isinstance(packages, list):
            source_path = repo_path((result.get("source") or {}).get("path") or "requirements.txt")
            for package in packages:
                metadata = package.get("package") or {}
                name = str(metadata.get("name") or "unknown")
                version = str(metadata.get("version") or "unknown")
                ecosystem = str(metadata.get("ecosystem") or "unknown")
                for vuln in package.get("vulnerabilities") or []:
                    output.append(_dependency_record(run, sha, source_path, name, version, ecosystem,
                                                     str(vuln.get("id") or "unknown"),
                                                     str(vuln.get("summary") or vuln.get("id") or "OSV candidate"),
                                                     osv_severity(package, str(vuln.get("id") or "unknown")), False))
            continue
        affected = [value for value in result.get("affected") or [] if isinstance(value, dict)]
        package_meta = (affected[0].get("package") or {}) if affected else {}
        name = str(result.get("package") or result.get("dependency") or package_meta.get("name") or "unknown")
        ecosystem = str(result.get("ecosystem") or package_meta.get("ecosystem") or "unknown")
        version = str(result.get("installed_version") or result.get("version") or "not_retained_in_normalized_row")
        vuln_id = str(result.get("id") or result.get("vulnerability_id") or result.get("advisory_id") or "unknown")
        database = result.get("database_specific") if isinstance(result.get("database_specific"), dict) else {}
        severity = str(result.get("severity") if isinstance(result.get("severity"), str) else database.get("severity") or "unknown").casefold()
        output.append(_dependency_record(run, sha, repo_path(result.get("path") or "requirements.txt"),
                                         name, version, ecosystem, vuln_id,
                                         str(result.get("summary") or vuln_id), severity, True))
    return output


def _dependency_record(run: dict[str, Any], sha: str, path: str, name: str, version: str,
                       ecosystem: str, vuln_id: str, title: str, severity: str,
                       normalized: bool) -> dict[str, Any]:
    rationale = ("OSV reported an advisory while scanning the exact assessed checkout. "
                 "Installed-version applicability, runtime reachability, production use, and remediation require human confirmation.")
    if normalized:
        rationale = ("OSV reported an advisory while scanning the exact assessed checkout. The normalized evidence row does not "
                     "retain the installed version, so applicability, reachability, and remediation require human confirmation.")
    row = common_record(
        candidate_id=stable_id("NICO-DEPENDENCY", sha, ecosystem, name, version, vuln_id),
        cluster_id=stable_id("NICO-CLUSTER-DEPENDENCY", ecosystem, name),
        category="dependency", scanner="osv-scanner", rule=vuln_id, title=title,
        path=path, line=None, severity=severity, confidence="high",
        proposed="dependency_reachability_and_upgrade_review", rationale=rationale,
        sha=sha, evidence_fingerprint=fingerprint(run, "osv-scanner"),
    )
    row.update({"package": name, "installed_version": version, "ecosystem": ecosystem})
    return row
