from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from nico.candidate_lineage_migration_v1 import VERSION as LINEAGE_VERSION
from nico.candidate_lineage_migration_v1 import apply_candidate_lineage

VERSION = "nico.candidate-lineage-runtime-patch.v1"
_PROVIDER_MARKER = "_nico_candidate_lineage_provider_v1"
_INSTALL_MARKER = "_nico_candidate_lineage_install_v1"
_STAGE_MARKER = "_nico_candidate_lineage_stage_v1"
_HEAVY = {"pdf_base64", "html", "markdown", "scanner_results", "raw_output", "stdout", "stderr"}


def _find_lineage(node: Any, depth: int = 0) -> Mapping[str, Any]:
    if depth > 8:
        return {}
    if isinstance(node, Mapping):
        direct = node.get("candidate_lineage")
        if isinstance(direct, Mapping):
            return direct
        for key, value in node.items():
            if str(key).casefold() in _HEAVY:
                continue
            found = _find_lineage(value, depth + 1)
            if found:
                return found
    elif isinstance(node, list) and len(node) <= 250:
        for value in node:
            found = _find_lineage(value, depth + 1)
            if found:
                return found
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
        output = deepcopy(stage)
        evidence = [str(item) for item in output.get("evidence") or []]
        evidence.extend(
            [
                f"Prior candidate register imported from exact commit {lineage.get('prior_target_commit_sha')}",
                f"Prior candidates: {lineage.get('prior_candidate_count', 0)}; current candidates: {lineage.get('current_candidate_count', 0)}.",
                f"Carried forward with exact identity: {lineage.get('carried_forward_exact', 0)}.",
                f"Carried forward after location change: {lineage.get('carried_forward_location_changed', 0)}.",
                f"Carried forward after evidence-text change: {lineage.get('carried_forward_evidence_changed', 0)}.",
                f"Newly observed: {lineage.get('newly_observed', 0)}; no longer observed: {lineage.get('no_longer_observed', 0)}.",
                "Prior proposed dispositions were preserved with provenance; human approval was not carried forward.",
            ]
        )
        output["evidence"] = evidence
        output["summary"] = (
            "Scanner candidates remain separate from confirmed material findings. "
            "The prior canonical register was imported, cross-SHA lineage was reconciled, "
            "and new or changed observations remain human-review work."
        )
        output["unavailable_data_notes"] = [
            item
            for item in output.get("unavailable_data_notes") or []
            if "prior structured risk register was unavailable" not in str(item).casefold()
        ]
        output["candidate_lineage"] = deepcopy(dict(lineage))
        return output

    setattr(candidate_stage, _STAGE_MARKER, True)
    setattr(candidate_stage, "_nico_previous", current)
    content._candidate_stage = candidate_stage
    return True


def install_candidate_lineage_runtime_patch() -> dict[str, Any]:
    from nico import comprehensive_native_providers_v5 as providers

    current_builder = providers.build_canonical_scanner_finding_register
    if not getattr(current_builder, _PROVIDER_MARKER, False):
        @wraps(current_builder)
        def build_with_lineage(scan: Mapping[str, Any], commit_sha: str):
            return apply_candidate_lineage(current_builder(scan, commit_sha))

        setattr(build_with_lineage, _PROVIDER_MARKER, True)
        setattr(build_with_lineage, "_nico_previous", current_builder)
        providers.build_canonical_scanner_finding_register = build_with_lineage

    current_install = providers.install_native_comprehensive_providers
    if not getattr(current_install, _INSTALL_MARKER, False):
        @wraps(current_install)
        def install_with_lineage(app):
            result = current_install(app)
            status = dict(getattr(app.state, "nico_native_comprehensive_provider_status", {}) or {})
            status.update(
                {
                    "candidate_lineage_migration_bound": True,
                    "candidate_lineage_schema": LINEAGE_VERSION,
                    "prior_proposed_dispositions_may_carry_forward": True,
                    "human_approval_may_carry_forward": False,
                    "client_delivery_allowed": False,
                }
            )
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
        "human_approval_carried_forward": False,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_candidate_lineage_runtime_patch"]
