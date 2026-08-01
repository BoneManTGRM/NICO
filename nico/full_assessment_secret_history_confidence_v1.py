from __future__ import annotations

from functools import wraps
from typing import Any, Callable

import nico.full_assessment_scorecard as scorecard

VERSION = "nico.full_assessment_secret_history_confidence.v1"
_PATCH_MARKER = "_nico_full_assessment_secret_history_confidence_v1"
_SECRET_TOOLS = {"gitleaks", "trufflehog", "detect-secrets"}
_COMPLETE_STATES = {
    "complete",
    "completed",
    "completed_clean",
    "completed_with_findings",
    "passed",
    "success",
    "succeeded",
}


def _name(record: dict[str, Any]) -> str:
    return str(
        record.get("scanner")
        or record.get("scanner_name")
        or record.get("tool")
        or ""
    ).strip().casefold()


def _full_history_scanners(scanner: dict[str, Any]) -> set[str]:
    run = scorecard._tool_names(scanner, "tools_run") & _SECRET_TOOLS
    blocked = (
        scorecard._tool_names(scanner, "unavailable_tools")
        | scorecard._tool_names(scanner, "failed_tools")
        | scorecard._tool_names(scanner, "timed_out_tools")
    )
    verified: set[str] = set()
    records = scanner.get("scanner_results")
    if not isinstance(records, list):
        return verified

    for raw in records:
        if not isinstance(raw, dict):
            continue
        name = _name(raw)
        if name not in run or name in blocked:
            continue
        status = str(
            raw.get("execution_status") or raw.get("status") or ""
        ).strip().casefold()
        completed = raw.get("execution_completed") is True or status in _COMPLETE_STATES
        history_verified = any(
            raw.get(key) is True
            for key in (
                "full_history_covered",
                "full_history_verified",
                "history_depth_verified",
            )
        )
        history_count = scorecard._count(raw.get("history_commit_count"))
        if completed and history_verified and history_count > 0:
            verified.add(name)
    return verified


def install_full_assessment_secret_history_confidence_v1() -> dict[str, Any]:
    current: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] = (
        scorecard._secrets_section
    )
    if bool(getattr(current, _PATCH_MARKER, False)):
        return {
            "status": "already_installed",
            "version": VERSION,
            "history_confidence_requires_completed_history_evidence": True,
        }

    @wraps(current)
    def secrets_with_history_confidence(
        repo: dict[str, Any],
        scanner: dict[str, Any],
    ) -> dict[str, Any]:
        section = current(repo, scanner)
        history_scanners = _full_history_scanners(scanner)
        if not history_scanners:
            return section

        section["confidence"] = "history-scanner-and-repository-bound"
        evidence = section.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
            section["evidence"] = evidence
        note = (
            "Verified full-history secret scanners: "
            + ", ".join(sorted(history_scanners))
            + "."
        )
        if note not in evidence:
            evidence.append(note)
        section["verified_claims"] = list(evidence)
        return section

    setattr(secrets_with_history_confidence, _PATCH_MARKER, True)
    setattr(secrets_with_history_confidence, "_nico_previous", current)
    scorecard._secrets_section = secrets_with_history_confidence
    return {
        "status": "installed",
        "version": VERSION,
        "history_confidence_requires_completed_history_evidence": True,
        "zero_sampled_hits_are_not_clean_history_proof": True,
        "failed_or_unavailable_history_scanners_are_excluded": True,
    }


__all__ = [
    "VERSION",
    "install_full_assessment_secret_history_confidence_v1",
]
