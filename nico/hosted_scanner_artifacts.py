from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact, scanner_worker_evidence_notes

SCANNER_ARTIFACT_KEYS = (
    "scanner_worker_artifact",
    "scanner_artifact",
    "worker_artifact",
    "scanner_worker",
)


def _status_color(score: int, unavailable: bool = False) -> str:
    if unavailable:
        return "gray"
    if score >= 75:
        return "green"
    if score >= 45:
        return "yellow"
    return "red"


def extract_scanner_worker_artifact(payload: dict[str, Any]) -> dict[str, Any] | None:
    for key in SCANNER_ARTIFACT_KEYS:
        value = payload.get(key)
        if isinstance(value, dict):
            return value
    return None


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


def _apply_static_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], notes: dict[str, list[str]]) -> None:
    section.setdefault("evidence", []).extend(notes.get("evidence", []))
    section.setdefault("findings", []).extend([item for item in notes.get("findings", []) if "static" in item.lower()])
    section.setdefault("unavailable", []).extend([item for item in notes.get("unavailable", []) if "static" in item.lower()])

    if normalized.get("static_evidence_complete"):
        _remove_unavailable(section, ("semgrep", "bandit", "eslint", "typescript", "sandboxed worker"))
        count = int(normalized.get("static_finding_count") or 0)
        if count == 0:
            section["score"] = max(int(section.get("score") or 0), 92)
            section["summary"] = "Static analysis includes worker-backed Bandit, Semgrep, ESLint, and TypeScript evidence."
        else:
            section["score"] = max(45, min(int(section.get("score") or 0), 82 - min(35, count)))
            section["summary"] = "Static analysis includes worker-backed scanner evidence with findings requiring triage."
    _refresh_section_status(section)


def _apply_secret_worker_evidence(section: dict[str, Any], normalized: dict[str, Any], notes: dict[str, list[str]]) -> None:
    section.setdefault("evidence", []).extend(notes.get("evidence", []))
    section.setdefault("findings", []).extend([item for item in notes.get("findings", []) if "secret" in item.lower()])
    section.setdefault("unavailable", []).extend([item for item in notes.get("unavailable", []) if "secret" in item.lower()])

    if normalized.get("secret_evidence_complete"):
        _remove_unavailable(section, ("gitleaks", "trufflehog", "git-history", "sandboxed worker"))
        count = int(normalized.get("secret_finding_count") or 0)
        if count == 0:
            section["score"] = max(int(section.get("score") or 0), 95)
            section["summary"] = "Secrets review includes worker-backed Gitleaks and TruffleHog evidence."
        else:
            section["score"] = max(25, min(int(section.get("score") or 0), 70 - min(45, count * 10)))
            section["summary"] = "Secrets review includes worker-backed secret scanner findings requiring immediate human review."
    _refresh_section_status(section)


def _apply_velocity_worker_evidence(section: dict[str, Any], normalized: dict[str, Any]) -> None:
    if normalized.get("static_evidence_complete"):
        section.setdefault("evidence", []).append(
            "Scanner-worker static evidence is available, reducing hosted uncertainty around large source footprint and deeper analyzer coverage."
        )
        _remove_unavailable(section, ("deeper complexity", "sandboxed worker"))
        section["score"] = max(int(section.get("score") or 0), 82)
    _refresh_section_status(section)


def attach_scanner_worker_artifacts(result: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """Attach explicit scanner-worker evidence to a hosted Express result.

    This function is intentionally conservative. It only upgrades sections when a
    scanner-worker artifact is explicitly supplied. Missing tool evidence remains
    unavailable instead of being treated as clean.
    """
    output = deepcopy(result)
    artifact = extract_scanner_worker_artifact(payload)
    if not artifact:
        output["scanner_worker_evidence_attached"] = False
        output.setdefault("unavailable_data_notes", []).append(
            "No scanner-worker artifact was supplied; hosted Express result keeps scanner execution evidence unavailable."
        )
        return output

    normalized = normalize_scanner_worker_artifact(artifact)
    notes = scanner_worker_evidence_notes(artifact)
    sections = output.get("sections") or []
    for section in sections:
        if not isinstance(section, dict):
            continue
        section_id = section.get("id")
        if section_id == "static_analysis":
            _apply_static_worker_evidence(section, normalized, notes)
        elif section_id == "secrets_review":
            _apply_secret_worker_evidence(section, normalized, notes)
        elif section_id == "velocity_complexity":
            _apply_velocity_worker_evidence(section, normalized)

    output["scanner_worker_evidence_attached"] = True
    output["scanner_worker_artifact"] = normalized
    output["findings"] = [
        finding
        for item in sections
        if isinstance(item, dict)
        for finding in item.get("findings", [])
    ] or ["No high-confidence finding was returned by available hosted checks."]
    return output


def run_github_assessment_with_scanner_artifacts(payload: dict[str, Any]) -> dict[str, Any]:
    """Run hosted Express assessment, then attach explicit scanner-worker artifacts.

    Existing callers can keep using run_github_assessment. Worker-aware hosted flows
    can call this wrapper when they have a trusted scanner-worker artifact to attach.
    """
    from nico.hosted_assessment import run_github_assessment

    result = run_github_assessment(payload)
    if result.get("status") != "complete":
        return result
    return attach_scanner_worker_artifacts(result, payload)
