from __future__ import annotations
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.candidate-phase1-report-stage.v1"
_MARKER = "_nico_candidate_phase1_stage_v1"


def _find(node: Any, name: str, depth: int = 0) -> Mapping[str, Any]:
    if depth > 8: return {}
    if isinstance(node, Mapping):
        direct = node.get(name)
        if isinstance(direct, Mapping): return direct
        for key, value in node.items():
            if str(key).casefold() in {"pdf_base64", "html", "markdown", "scanner_results", "raw_output", "stdout", "stderr"}: continue
            found = _find(value, name, depth + 1)
            if found: return found
    elif isinstance(node, list) and len(node) <= 250:
        for value in node:
            found = _find(value, name, depth + 1)
            if found: return found
    return {}


def install_candidate_phase1_report_stage() -> bool:
    from nico import comprehensive_report_content_render_v66 as content
    current = content._candidate_stage
    if getattr(current, _MARKER, False): return True
    @wraps(current)
    def stage(canonical: Mapping[str, Any], renderer: Any):
        value = current(canonical, renderer)
        if not isinstance(value, dict): return value
        technical = _find(canonical, "technical_triage"); lineage = _find(canonical, "candidate_lineage")
        if technical.get("status") != "complete": return value
        metrics = technical.get("workload_metrics") if isinstance(technical.get("workload_metrics"), Mapping) else {}
        output = deepcopy(value); evidence = [str(item) for item in output.get("evidence") or []]
        evidence.extend([
            f"Prior candidates: {lineage.get('prior_candidate_count', 0)}; current candidates: {lineage.get('current_candidate_count', metrics.get('total_candidates', 0))}.",
            f"Technical triage coverage: {metrics.get('technical_triage_completed', 0)}/{metrics.get('total_candidates', 0)} ({metrics.get('technical_triage_coverage_pct', 0)}%).",
            f"Individual human attention: {metrics.get('candidates_requiring_individual_human_attention', 0)}; grouped-review eligible: {metrics.get('candidates_eligible_for_grouped_review', 0)}; quality-control pool: {metrics.get('quality_control_sample_pool', 0)}.",
            f"Assessment-subject lineage match: {lineage.get('assessment_subject_match')}; reason: {lineage.get('assessment_subject_match_reason', 'unavailable')}.",
            "Technical triage and routing are proposal-only; authorized human disposition, approval, risk acceptance, and client delivery remain pending/blocked.",
        ])
        output["evidence"] = evidence; output["technical_triage"] = deepcopy(dict(technical)); output["candidate_lineage"] = deepcopy(dict(lineage))
        output["summary"] = "NICO completed deterministic candidate triage and routed review by exception while preserving every candidate and keeping human disposition and final approval explicit."
        for key in ("unavailable", "unavailable_data_notes"):
            output[key] = [item for item in output.get(key) or [] if "prior structured risk register was unavailable" not in str(item).casefold()]
        return output
    setattr(stage, _MARKER, True); setattr(stage, "_nico_previous", current); content._candidate_stage = stage
    return True

__all__ = ["VERSION", "install_candidate_phase1_report_stage"]
