from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.artifact_evidence import apply_evidence_artifact_scoring
from nico.report_accuracy import apply_report_accuracy as apply_base_report_accuracy


LEGACY_WORKFLOW_TRIGGERS = ("security-audit", "security audit")


def _artifact_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summary = payload.get("evidence_artifact_summary")
    return summary if isinstance(summary, dict) else {}


def _strip_legacy_workflow_lift_trigger(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    cleaned = value
    for trigger in LEGACY_WORKFLOW_TRIGGERS:
        cleaned = cleaned.replace(trigger, "audit evidence workflow")
    return cleaned


def _prevent_workflow_presence_only_score_lift(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    for section in output.get("sections", []) or []:
        if not isinstance(section, dict) or section.get("id") != "ci_cd":
            continue
        section["evidence"] = [_strip_legacy_workflow_lift_trigger(item) for item in section.get("evidence", []) or []]
        section["findings"] = [_strip_legacy_workflow_lift_trigger(item) for item in section.get("findings", []) or []]
    return output


def apply_report_accuracy(result: dict[str, Any]) -> dict[str, Any]:
    """Apply v19 evidence-artifact scoring before the base truthfulness pass.

    The legacy accuracy pass still understands sections, confidence, maturity,
    and reparodynamic output. This wrapper adds v19 artifact parsing and removes
    the old behavior where audit workflow configuration alone could lift scores.
    """
    artifact_scored = apply_evidence_artifact_scoring(deepcopy(result))
    guarded = _prevent_workflow_presence_only_score_lift(artifact_scored)
    polished = apply_base_report_accuracy(guarded)
    summary = _artifact_summary(artifact_scored)
    polished["evidence_artifacts"] = artifact_scored.get("evidence_artifacts", [])
    polished["evidence_artifact_summary"] = summary
    rules = list(polished.get("truthfulness_rules") or [])
    rule = "CI workflow presence alone cannot lift scores; parsed evidence artifact contents are required."
    if rule not in rules:
        rules.append(rule)
    polished["truthfulness_rules"] = rules
    return polished
