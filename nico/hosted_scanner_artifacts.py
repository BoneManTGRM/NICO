from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.bandit_triage import bandit_triage_report_lines, build_bandit_triage
from nico.hosted_scanner_worker import hosted_scanner_autorun_enabled, run_hosted_scanner_worker
from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact, scanner_worker_evidence_notes

SCANNER_ARTIFACT_KEYS = (
    "scanner_worker_artifact",
    "scanner_artifact",
    "worker_artifact",
    "scanner_worker",
)
AUTO_RUN_SENTINEL = {"auto_run_scanner_worker": True}


def _status_color(score: int, unavailable: bool = False) -> str:
    if unavailable:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def extract_explicit_scanner_worker_artifact(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in SCANNER_ARTIFACT_KEYS:
        value = payload.get(key)
        if isinstance(value, dict) and value:
            return value
    return None


def extract_scanner_worker_artifact(payload: dict[str, Any]) -> dict[str, Any] | None:
    explicit = extract_explicit_scanner_worker_artifact(payload)
    if explicit:
        return explicit
    if hosted_scanner_autorun_enabled(payload):
        return dict(AUTO_RUN_SENTINEL)
    return None


def _resolve_scanner_worker_artifact(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, bool]:
    explicit = extract_explicit_scanner_worker_artifact(payload)
    if explicit:
        return explicit, False
    if hosted_scanner_autorun_enabled(payload):
        return run_hosted_scanner_worker(payload), True
    return None, False


def _remove_unavailable(section: dict[str, Any], fragments: tuple[str, ...]) -> None:
    unavailable = section.get("unavailable") or []
    section["unavailable"] = [
        item for item in unavailable
        if not any(fragment.lower() in str(item).lower() for fragment in fragments)
    ]


def _refresh_section_status(section: dict[str, Any]) -> None:
    score = max(0, min(100, int(section.get("score") or 0)))
    section["score"] = score
    section["status"] = _status_color(score, bool(section.get("unavailable")) and score == 0)


def _complexity_profile(artifact: dict[str, Any]) -> dict[str, Any]:
    value = artifact.get("complexity_engine")
    return value if isinstance(value, dict) else {}


def _complexity_evidence(profile: dict[str, Any]) -> list[str]:
    evidence = [str(item) for item in profile.get("evidence", []) if item]
    risk = profile.get("risk_level")
    score = profile.get("complexity_score")
    if risk and score is not None:
        evidence.append(f"Complexity engine risk level: {risk}; complexity score={score}/100.")
    hotspots = profile.get("hotspots") if isinstance(profile.get("hotspots"), list) else []
    if hotspots:
        top = hotspots[0]
        if isinstance(top, dict):
            evidence.append(
                "Top complexity hotspot: "
                f"{top.get('path')} hotspot_score={top.get('hotspot_score')}, "
                f"cyclomatic={top.get('cyclomatic_complexity')}, churn={top.get('churn')}."
            )
    return evidence


def _complexity_findings(profile: dict[str, Any]) -> list[str]:
    findings = [str(item) for item in profile.get("findings", []) if item]
    hotspots = profile.get("hotspots") if isinstance(profile.get("hotspots"), list) else []
    for item in hotspots[:5]:
        if not isinstance(item, dict):
            continue
        findings.append(
            "Complexity hotspot: "
            f"{item.get('path')} score={item.get('hotspot_score')}, "
            f"loc={item.get('loc')}, cyclomatic={item.get('cyclomatic_complexity')}, churn={item.get('churn')}."
        )
    return findings


def _secret_history_scan_verified(artifact: dict[str, Any]) -> bool:
    checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
    history = artifact.get("secret_history_scan") if isinstance(artifact.get("secret_history_scan"), dict) else {}
    completed = history.get("completed_tools") if isinstance(history.get("completed_tools"), list) else []
    return bool(checkout.get("full_history_secret_scan_requested") and checkout.get("history_depth") == "full" and completed)


def _apply_dependency_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], notes: dict[str, list[str]]) -> None:
    section.setdefault("evidence", []).extend([item for item in notes.get("evidence", []) if "dependency" in item.lower()])
    section.setdefault("findings", []).extend([item for item in notes.get("findings", []) if "dependency" in item.lower()])
    section.setdefault("unavailable", []).extend([item for item in notes.get("unavailable", []) if "dependency" in item.lower()])

    if normalized.get("dependency_evidence_complete"):
        _remove_unavailable(section, ("pip-audit", "npm audit", "npm-audit", "osv scanner", "osv-scanner", "sandboxed worker"))
        count = int(normalized.get("dependency_finding_count") or 0)
        if count == 0:
            section["score"] = max(int(section.get("score") or 0), 95)
            section["summary"] = "Dependency review includes worker-backed pip-audit, npm audit, and OSV Scanner evidence."
        else:
            section["score"] = max(45, min(int(section.get("score") or 0), 86 - min(35, count * 4)))
            section["summary"] = "Dependency review includes worker-backed dependency scanner evidence with findings requiring triage."
    _refresh_section_status(section)


def _apply_bandit_triage(section: dict[str, Any], artifact: dict[str, Any]) -> dict[str, Any]:
    triage = build_bandit_triage(artifact)
    if triage.get("finding_count"):
        lines = bandit_triage_report_lines(triage)
        section.setdefault("evidence", []).extend(lines.get("evidence", []))
        section.setdefault("findings", []).extend(lines.get("findings", []))
        section["summary"] = "Static analysis includes worker-backed scanner evidence and Bandit finding triage."
        if triage.get("blocking_count"):
            section["score"] = max(45, min(int(section.get("score") or 0), 74))
        elif triage.get("review_required_count"):
            section["score"] = max(55, min(int(section.get("score") or 0), 82))
    return triage


def _apply_static_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], notes: dict[str, list[str]], artifact: dict[str, Any]) -> dict[str, Any]:
    section.setdefault("evidence", []).extend([item for item in notes.get("evidence", []) if "static" in item.lower()])
    section.setdefault("findings", []).extend([item for item in notes.get("findings", []) if "static" in item.lower()])
    section.setdefault("unavailable", []).extend([item for item in notes.get("unavailable", []) if "static" in item.lower()])

    triage = build_bandit_triage(artifact)
    if normalized.get("static_evidence_complete"):
        _remove_unavailable(section, ("semgrep", "bandit", "eslint", "typescript", "sandboxed worker"))
        count = int(normalized.get("static_finding_count") or 0)
        if count == 0:
            section["score"] = max(int(section.get("score") or 0), 92)
            section["summary"] = "Static analysis includes worker-backed Bandit, Semgrep, ESLint, and TypeScript evidence."
        else:
            section["score"] = max(45, min(int(section.get("score") or 0), 82 - min(35, count)))
            section["summary"] = "Static analysis includes worker-backed scanner evidence with findings requiring triage."
    if triage.get("finding_count"):
        triage = _apply_bandit_triage(section, artifact)
    _refresh_section_status(section)
    return triage


def _apply_secret_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], notes: dict[str, list[str]], artifact: dict[str, Any]) -> None:
    section.setdefault("evidence", []).extend([item for item in notes.get("evidence", []) if "secret" in item.lower()])
    section.setdefault("findings", []).extend([item for item in notes.get("findings", []) if "secret" in item.lower()])
    section.setdefault("unavailable", []).extend([item for item in notes.get("unavailable", []) if "secret" in item.lower()])

    history_verified = _secret_history_scan_verified(artifact)
    if history_verified:
        history = artifact.get("secret_history_scan") if isinstance(artifact.get("secret_history_scan"), dict) else {}
        completed = ", ".join(str(item) for item in history.get("completed_tools", []))
        commit_count = artifact.get("checkout", {}).get("commit_count") if isinstance(artifact.get("checkout"), dict) else None
        section.setdefault("evidence", []).append(
            f"Full git-history secret scan executed with {completed}; commit_count={commit_count if commit_count is not None else 'unknown'}."
        )

    if normalized.get("secret_evidence_complete"):
        if history_verified:
            _remove_unavailable(section, ("gitleaks", "trufflehog", "git-history", "git history", "sandboxed worker"))
        else:
            _remove_unavailable(section, ("gitleaks", "trufflehog", "sandboxed worker"))
            section.setdefault("unavailable", []).append("Full git-history secret scan did not provide verified history coverage.")
        count = int(normalized.get("secret_finding_count") or 0)
        if count == 0:
            section["score"] = max(int(section.get("score") or 0), 95 if history_verified else 92)
            section["summary"] = "Secrets review includes worker-backed Gitleaks and TruffleHog history evidence." if history_verified else "Secrets review includes worker-backed secret scanner evidence, but full git-history coverage is not verified."
        else:
            section["score"] = max(25, min(int(section.get("score") or 0), 70 - min(45, count * 10)))
            section["summary"] = "Secrets review includes worker-backed secret scanner findings requiring immediate human review."
    _refresh_section_status(section)


def _apply_architecture_complexity(section: dict[str, Any], artifact: dict[str, Any]) -> None:
    profile = _complexity_profile(artifact)
    if not profile:
        return
    section.setdefault("evidence", []).extend(_complexity_evidence(profile))
    section.setdefault("findings", []).extend(_complexity_findings(profile))
    _remove_unavailable(section, ("call-graph", "call graph", "cyclomatic", "complexity scoring"))
    target_score = int(profile.get("architecture_score") or profile.get("complexity_score") or section.get("score") or 0)
    if profile.get("risk_level") == "high":
        section["score"] = min(int(section.get("score") or 0), target_score)
    else:
        section["score"] = max(int(section.get("score") or 0), target_score)
    section["summary"] = "Architecture review includes worker-backed call-graph, cyclomatic complexity, hotspot, churn, ownership, dependency-risk, and source-footprint evidence."
    _refresh_section_status(section)


def _apply_velocity_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], artifact: dict[str, Any]) -> None:
    if normalized.get("static_evidence_complete"):
        section.setdefault("evidence", []).append(
            "Scanner-worker static evidence is available, reducing hosted uncertainty around large source footprint and deeper analyzer coverage."
        )
        _remove_unavailable(section, ("deeper complexity", "sandboxed worker"))
        section["score"] = max(int(section.get("score") or 0), 82)
    if normalized.get("coverage_tools_completed"):
        section.setdefault("evidence", []).append("Scanner-worker coverage evidence is available for work-vs-expected review.")

    profile = _complexity_profile(artifact)
    if profile:
        section.setdefault("evidence", []).extend(_complexity_evidence(profile))
        section.setdefault("findings", []).extend(_complexity_findings(profile))
        _remove_unavailable(section, ("deeper complexity", "source-footprint", "source footprint"))
        target_score = int(profile.get("velocity_score") or profile.get("complexity_score") or section.get("score") or 0)
        if profile.get("risk_level") == "high":
            section["score"] = min(int(section.get("score") or 0), target_score)
        else:
            section["score"] = max(int(section.get("score") or 0), target_score)
        section["summary"] = "Velocity and complexity review includes worker-backed churn, ownership concentration, hotspot, call-graph, dependency-risk, and source-footprint evidence."
    _refresh_section_status(section)


def attach_scanner_worker_artifacts(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Attach explicit or auto-run scanner-worker evidence to a hosted Express result.

    Missing or failed tool evidence remains unavailable. Auto-run only happens for
    explicit authorized requests and can be disabled globally or per request.
    """
    output = deepcopy(result)
    artifact, auto_ran = _resolve_scanner_worker_artifact(payload)
    if not artifact:
        output["scanner_worker_evidence_attached"] = False
        output.setdefault("unavailable_data_notes", []).append(
            "No scanner-worker artifact was supplied or auto-run; hosted Express result keeps scanner execution evidence unavailable."
        )
        return output

    normalized = normalize_scanner_worker_artifact(artifact)
    notes = scanner_worker_evidence_notes(artifact)
    bandit_triage: dict[str, Any] | None = None
    sections = output.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if section_id == "dependency_health":
            _apply_dependency_worker_evidence(section, normalized, notes)
        elif section_id == "static_analysis":
            bandit_triage = _apply_static_worker_evidence(section, normalized, notes, artifact)
        elif section_id == "secrets_review":
            _apply_secret_worker_evidence(section, normalized, notes, artifact)
        elif section_id == "architecture_debt":
            _apply_architecture_complexity(section, artifact)
        elif section_id == "velocity_complexity":
            _apply_velocity_worker_evidence(section, normalized, artifact)

    output["scanner_worker_evidence_attached"] = True
    output["scanner_worker_auto_ran"] = auto_ran
    output["scanner_worker_artifact"] = normalized
    if artifact.get("secret_history_scan"):
        output["secret_history_scan"] = artifact["secret_history_scan"]
    if artifact.get("complexity_engine"):
        output["complexity_engine"] = artifact["complexity_engine"]
    if bandit_triage and bandit_triage.get("finding_count"):
        output["bandit_triage"] = bandit_triage
    if artifact.get("worker_execution_state"):
        output["scanner_worker_execution"] = {
            "state": artifact.get("worker_execution_state"),
            "generated_at": artifact.get("generated_at"),
            "duration_seconds": artifact.get("duration_seconds"),
            "retention_note": artifact.get("retention_note"),
        }
    output.setdefault("unavailable_data_notes", []).extend(artifact.get("unavailable_data_notes") or [])
    output["findings"] = [
        finding
        for item in sections
        if isinstance(item, dict)
        for finding in item.get("findings", [])
    ] or ["No high-confidence finding was returned by available hosted checks."]
    return output


def run_github_assessment_with_scanner_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    """Run hosted Express assessment, then attach scanner-worker artifacts.

    Existing callers can keep using run_github_assessment. Worker-aware hosted flows
    can call this wrapper with a trusted artifact or let NICO auto-run the worker for
    explicitly authorized owner/repo assessments.
    """
    from nico.hosted_assessment import run_github_assessment

    result = run_github_assessment(payload)
    if result.get("status") != "complete":
        return result
    return attach_scanner_worker_artifacts(result, payload)
