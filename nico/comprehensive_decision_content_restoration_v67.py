from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

from nico.comprehensive_decision_content_restoration_v66 import (
    restore_decision_content as _restore_decision_content_v66,
)

VERSION = "nico.comprehensive-decision-content-restoration.v67"

_RELEVANT_STAGE_IDS = (
    "repository_and_delivery_evidence",
    "ci_cd_architecture_complexity_velocity",
    "architecture_and_data_flow",
    "deep_scanner_triage",
    "dependency_security_static_analysis",
    "evidence_reconciliation_and_scoring",
    "risk_reduction_and_executive_briefing",
    "decision_report_generation",
    "historical_trends_and_change_failure",
    "developer_delivery_process",
    "deployment_and_infrastructure",
)


def _bounded_stage_view(raw_stages: Mapping[str, Any]) -> dict[str, Any]:
    return {
        stage_id: raw_stages[stage_id]
        for stage_id in _RELEVANT_STAGE_IDS
        if stage_id in raw_stages and isinstance(raw_stages[stage_id], Mapping)
    }


def restore_decision_content(
    canonical: Mapping[str, Any],
    *,
    raw_stages: Mapping[str, Any],
    assessment: Mapping[str, Any],
    commit_sha: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Restore decision content from a bounded set of authoritative stages.

    The final report path previously timed out when it repeatedly traversed the entire
    retained evidence tree. The restoration logic needs only the stages that own
    findings, complexity, scanner triage, and CI operational context. Unrelated large
    evidence payloads are not copied or scanned.
    """

    selected = _bounded_stage_view(raw_stages)
    output, updated_assessment, manifest = _restore_decision_content_v66(
        canonical,
        raw_stages=selected,
        assessment=assessment,
        commit_sha=commit_sha,
    )
    bounded_manifest = {
        **deepcopy(manifest),
        "version": VERSION,
        "source_stage_population": len(raw_stages),
        "selected_stage_population": len(selected),
        "selected_stage_ids": sorted(selected),
        "unrelated_stage_payloads_not_copied_or_scanned": True,
        "bounded_authoritative_stage_projection": True,
    }
    output["decision_content_restoration"] = deepcopy(bounded_manifest)
    updated_assessment["decision_content_restoration"] = deepcopy(bounded_manifest)
    output["assessment"] = updated_assessment
    return output, updated_assessment, bounded_manifest


__all__ = [
    "VERSION",
    "restore_decision_content",
]
