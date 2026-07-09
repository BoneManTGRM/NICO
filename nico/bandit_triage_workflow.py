from __future__ import annotations

from typing import Any

from nico.bandit_triage import (
    approval_template_for_triage,
    bandit_triage_report_lines,
    build_bandit_triage,
)


def _scanner_artifact(result: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("scanner_worker_artifact", "scanner_artifacts", "scanner_worker"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    return None


def _approval_artifact(result: dict[str, Any]) -> dict[str, Any] | None:
    for key in ("bandit_triage_approval", "bandit_triage_approvals", "bandit_triage_approval_artifact"):
        value = result.get(key)
        if isinstance(value, dict):
            return value
    scanner = _scanner_artifact(result)
    if isinstance(scanner, dict):
        for key in ("bandit_triage_approval", "bandit_triage_approvals", "bandit_triage_approval_artifact"):
            value = scanner.get(key)
            if isinstance(value, dict):
                return value
    return None


def _static_section(result: dict[str, Any]) -> dict[str, Any] | None:
    for section in result.get("sections", []) or []:
        if isinstance(section, dict) and section.get("id") == "static_analysis":
            return section
    return None


def _append_unique(items: list[Any], value: str) -> None:
    if value not in items:
        items.append(value)


def _clear_prior_bandit_triage_lines(section: dict[str, Any]) -> None:
    for key in ("evidence", "findings", "unavailable"):
        values = section.get(key) or []
        if not isinstance(values, list):
            values = [values]
        section[key] = [item for item in values if not str(item).startswith("Bandit triage") and "finding_key=bandit_" not in str(item)]


def _attach_lines(result: dict[str, Any], triage: dict[str, Any]) -> None:
    section = _static_section(result)
    if not section:
        return
    _clear_prior_bandit_triage_lines(section)
    lines = bandit_triage_report_lines(triage)
    for key in ("evidence", "findings"):
        section.setdefault(key, [])
        if not isinstance(section[key], list):
            section[key] = [section[key]]
        for line in lines.get(key, []):
            _append_unique(section[key], line)


def attach_bandit_triage_to_report(result: dict[str, Any]) -> dict[str, Any]:
    """Attach Bandit triage evidence after scanner artifact binding.

    This does not approve findings automatically. It creates a stable finding-key
    triage artifact and, when a signed approval artifact is present, applies those
    approvals so repeated reports stop re-blocking the same reviewed finding.
    """
    if result.get("status") != "complete":
        return result
    artifact = _scanner_artifact(result)
    guards = result.setdefault("report_quality_guards", {})
    if not artifact:
        guards["bandit_triage"] = {
            "status": "missing_scanner_artifact",
            "guardrail": "Bandit triage requires a scanner-worker artifact with Bandit output.",
        }
        return result

    approval = _approval_artifact(result)
    triage = build_bandit_triage(artifact, approval_artifact=approval)
    result["bandit_triage"] = triage
    if triage.get("human_review_required"):
        result["bandit_triage_approval_template"] = approval_template_for_triage(triage)
    else:
        result.pop("bandit_triage_approval_template", None)
    _attach_lines(result, triage)
    guards["bandit_triage"] = {
        "status": triage.get("status"),
        "artifact_hash": triage.get("artifact_hash"),
        "finding_count": triage.get("finding_count"),
        "blocking_count": triage.get("blocking_count"),
        "review_required_count": triage.get("review_required_count"),
        "approved_count": triage.get("approved_count"),
        "approval_artifact_attached": triage.get("approval_artifact_attached"),
        "guardrail": "Bandit findings clear static review only after clean scan or signed triage approvals with no blockers.",
    }
    return result
