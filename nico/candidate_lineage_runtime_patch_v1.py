from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from nico.candidate_evidence_context_v1 import VERSION as EVIDENCE_CONTEXT_VERSION
from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence
from nico.candidate_lineage_migration_v1 import VERSION as LINEAGE_VERSION
from nico.candidate_lineage_migration_v1 import apply_candidate_lineage, subject_identity
from nico.candidate_technical_triage_v1 import VERSION as TECHNICAL_TRIAGE_VERSION
from nico.candidate_technical_triage_v1 import apply_candidate_technical_triage
from nico.osv_scanner_context_patch_v1 import install_osv_scanner_context_patch

VERSION = "nico.candidate-lineage-runtime-patch.v3"
_PROVIDER_MARKER = "_nico_candidate_lineage_provider_v3"
_INSTALL_MARKER = "_nico_candidate_lineage_install_v3"
_STAGE_MARKER = "_nico_candidate_lineage_stage_v3"
_HEAVY = {"pdf_base64", "html", "markdown", "scanner_results", "raw_output", "stdout", "stderr"}


def _find_named_mapping(node: Any, name: str, depth: int = 0) -> Mapping[str, Any]:
    if depth > 8:
        return {}
    if isinstance(node, Mapping):
        direct = node.get(name)
        if isinstance(direct, Mapping):
            return direct
        for key, value in node.items():
            if str(key).casefold() in _HEAVY:
                continue
            found = _find_named_mapping(value, name, depth + 1)
            if found:
                return found
    elif isinstance(node, list) and len(node) <= 250:
        for value in node:
            found = _find_named_mapping(value, name, depth + 1)
            if found:
                return found
    return {}


def _find_lineage(node: Any, depth: int = 0) -> Mapping[str, Any]:
    return _find_named_mapping(node, "candidate_lineage", depth)


def _scan_subject(scan: Mapping[str, Any]) -> dict[str, str]:
    direct = subject_identity(scan)
    if direct:
        return direct
    for key in ("assessment", "target", "repository", "project", "metadata", "context"):
        value = scan.get(key)
        if isinstance(value, Mapping):
            candidate = subject_identity(value)
            if candidate:
                return candidate
    return {}


def _patch_candidate_stage() -> bool:
    from nico import comprehensive_report_content_render_v66 as content
    current = content._candidate_stage
    if getattr(current, _STAGE_MARKER, False):
        return True

    @wraps(current)
    def candidate_stage(canonical: Mapping[str, Any], renderer: Any):
        stage = current(canonical, renderer)
        if not isinstance(stage, dict):
            return stage
        lineage = _find_lineage(canonical)
        if not lineage or lineage.get("status") != "complete":
            return stage
        technical = _find_named_mapping(canonical, "technical_triage")
        output = deepcopy(stage)
        evidence = [str(item) for item in output.get("evidence") or []]
        evidence.extend([
            f"Prior candidate register imported from exact commit {lineage.get('prior_target_commit_sha')}; assessment-subject match={lineage.get('assessment_subject_match')}.",
            f"Prior candidates: {lineage.get('prior_candidate_count', 0)}; current candidates: {lineage.get('current_candidate_count', 0)}.",
            f"Exact carry-forward: {lineage.get('carried_forward_exact', 0)}; location-changed: {lineage.get('carried_forward_location_changed', 0)}; evidence-changed: {lineage.get('carried_forward_evidence_changed', 0)}.",
            f"Newly observed: {lineage.get('newly_observed', 0)}; no longer observed: {lineage.get('no_longer_observed', 0)}.",
            "Prior proposed dispositions may be retained only within the same assessment subject; human approval is never carried forward.",
        ])
        if technical.get("status") == "complete":
            metrics = technical.get("workload_metrics") if isinstance(technical.get("workload_metrics"), Mapping) else {}
            verdicts = (
                technical.get("verdict_counts")
                if isinstance(technical.get("verdict_counts"), Mapping)
                else {}
            )
            evidence.extend([
                (
                    "Technical triage proposals imported for "
                    f"{technical.get('imported_candidate_count', 0)} current candidate(s): "
                    f"not_actionable={verdicts.get('not_actionable', 0)}, "
                    f"needs_review={verdicts.get('needs_review', 0)}, "
                    f"confirmed={verdicts.get('confirmed', 0)}."
                ),
                (
                    "Current-evidence candidates requiring new technical triage: "
                    f"{technical.get('fresh_technical_triage_required', 0)}; "
                    f"fresh automated triage completed={technical.get('fresh_technical_triage_completed', 0)}."
                ),
                f"Technical triage coverage: {metrics.get('technical_triage_completed', 0)}/{metrics.get('total_candidates', 0)} ({metrics.get('technical_triage_coverage_pct', 0)}%).",
                f"Individual human attention: {metrics.get('candidates_requiring_individual_human_attention', 0)}; grouped-review eligible: {metrics.get('candidates_eligible_for_grouped_review', 0)}; quality-control pool: {metrics.get('quality_control_sample_pool', 0)}.",
                "Technical triage remains proposal-only. Authorized human approval remains pending and client delivery remains blocked.",
            ])
            output["technical_triage"] = deepcopy(dict(technical))
            output["summary"] = (
                "Scanner candidates remain separate from confirmed material findings. NICO performed deterministic fresh triage for new or evidence-changed candidates, retained valid same-subject prior analysis for stable lineage, and routed review by exception without creating human disposition or approval."
            )
        output["evidence"] = evidence
        for key in ("unavailable", "unavailable_data_notes"):
            output[key] = [
                item
                for item in output.get(key) or []
                if "prior structured risk register was unavailable"
                not in str(item).casefold()
            ]
        output["candidate_lineage"] = deepcopy(dict(lineage))
        return output

    setattr(candidate_stage, _STAGE_MARKER, True)
    setattr(candidate_stage, "_nico_previous", current)
    content._candidate_stage = candidate_stage
    return True


def install_candidate_lineage_runtime_patch() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers
    osv_context = install_osv_scanner_context_patch()
    current_builder = providers.build_canonical_scanner_finding_register
    if not getattr(current_builder, _PROVIDER_MARKER, False):
        @wraps(current_builder)
        def build_with_lineage(scan: Mapping[str, Any], commit_sha: str):
            register = current_builder(scan, commit_sha)
            subject = _scan_subject(scan)
            if subject:
                register["assessment_subject"] = subject
            register = enrich_canonical_candidate_evidence(register, scan)
            register = apply_candidate_lineage(register)
            return apply_candidate_technical_triage(register)
        setattr(build_with_lineage, _PROVIDER_MARKER, True)
        setattr(build_with_lineage, "_nico_previous", current_builder)
        providers.build_canonical_scanner_finding_register = build_with_lineage

    current_install = providers.install_native_comprehensive_providers
    if not getattr(current_install, _INSTALL_MARKER, False):
        @wraps(current_install)
        def install_with_lineage(app):
            result = current_install(app)
            status = dict(getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {})
            status.update({
                "candidate_lineage_migration_bound": True,
                "candidate_lineage_schema": LINEAGE_VERSION,
                "candidate_evidence_context_bound": True,
                "candidate_evidence_context_schema": EVIDENCE_CONTEXT_VERSION,
                "candidate_technical_triage_bound": True,
                "candidate_technical_triage_schema": TECHNICAL_TRIAGE_VERSION,
                "fresh_technical_triage_new_or_changed": True,
                "review_by_exception_routing_bound": True,
                "osv_scanner_context_bound": osv_context.get("parser_bound") is True and osv_context.get("fallback_bound") is True,
                "technical_triage_evidence_changed_may_carry_forward": False,
                "human_approval_may_carry_forward": False,
                "client_delivery_allowed": False,
            })
            app.state.nico_native_comprehensive_provider_status = status
            return result
        setattr(install_with_lineage, _INSTALL_MARKER, True)
        setattr(install_with_lineage, "_nico_previous", current_install)
        providers.install_native_comprehensive_providers = install_with_lineage

    stage_bound = _patch_candidate_stage()
    return {
        "status": "installed",
        "version": VERSION,
        "provider_bound": getattr(providers.build_canonical_scanner_finding_register, _PROVIDER_MARKER, False),
        "provider_install_bound": getattr(providers.install_native_comprehensive_providers, _INSTALL_MARKER, False),
        "report_stage_bound": stage_bound,
        "lineage_schema": LINEAGE_VERSION,
        "evidence_context_schema": EVIDENCE_CONTEXT_VERSION,
        "technical_triage_schema": TECHNICAL_TRIAGE_VERSION,
        "technical_triage_bound": True,
        "osv_scanner_context": osv_context,
        "human_approval_carried_forward": False,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_candidate_lineage_runtime_patch"]
