from __future__ import annotations

from functools import wraps
from copy import deepcopy
from collections.abc import Mapping
from typing import Any, Callable

from nico.express_score_assurance_ledger_v45 import apply_express_score_assurance_ledger_v45
from nico.scanner_claim_reconciliation_v45 import reconcile_scanner_claims_v45

VERSION = "nico.comprehensive_score_assurance_ledger.v45"
_PATCH_MARKER = "_nico_comprehensive_score_assurance_ledger_v45"


def bind_source_security_assurance(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Qualify technical signals with retained source/execution evidence, without scoring it."""
    from nico.repository_profile_coverage_v1 import source_coverage_metrics
    output = deepcopy(dict(payload))
    profiles = [stage["profile_coverage"] for stage in output.get("stage_summaries") or []
        if isinstance(stage, Mapping) and isinstance(stage.get("profile_coverage"), Mapping)]
    metrics = source_coverage_metrics(profiles[0]) if profiles else {}
    consistent = bool(profiles) and all(source_coverage_metrics(p) == metrics for p in profiles)
    profile = profiles[0] if consistent else {}
    counts = [profile.get(k) for k in ("analyzed_source_files", "eligible_source_files", "observed_source_files")]
    valid_counts = all(type(v) is int for v in counts) and 0 <= counts[0] <= counts[1] <= counts[2]
    source_known = consistent and valid_counts and profile.get("inventory_complete") is True and counts[1] > 0
    source_limited = source_known and counts[0] < counts[1]
    assessment = output.get("assessment") or {}
    records = output.get("requested_scanner_records") or assessment.get("requested_scanner_records") or []
    required = [r for r in records if isinstance(r, Mapping) and r.get("applicable") is not False]
    unresolved = [r for r in required if r.get("applicability_state") not in {"applicable", "applicable_to_subset"}]
    incomplete = [r for r in required if r.get("verified_complete") is not True]
    limit = (output.get("live_scanner_evidence") or {}).get("execution_limit")
    if not limit:
        limit = next((s.get("execution_limit") for s in output.get("stage_summaries") or []
            if isinstance(s, Mapping) and s.get("execution_limit")), None)
    reasons = []
    if not source_known: reasons.append("source_coverage_unverified")
    if source_limited: reasons.append("eligible_source_analysis_incomplete")
    if limit: reasons.append("repository_execution_limit")
    if not records: reasons.append("scanner_evidence_unavailable")
    if unresolved: reasons.append("scanner_applicability_unproven")
    if incomplete: reasons.append("scanner_execution_incomplete")
    status = "limited" if source_limited or limit or incomplete else "unverified" if reasons else "supported_scope"
    output["source_security_assurance"] = {
        "version": "nico.source_security_assurance.v1", "status": status, "reasons": reasons,
        "coverage_metrics": metrics if consistent else {},
        "unsampled_eligible_source_files": profile.get("unsampled_eligible_source_files"),
        "execution_limit": deepcopy(limit), "configured_scanner_count": len(records),
        "incomplete_required_scanner_count": len(incomplete), "unproven_applicability_count": len(unresolved),
        "repository_wide_security_rating": False, "technical_score_modified": False,
        "missing_evidence_is_pass": False, "missing_evidence_is_fail": False,
    }
    output.setdefault("assessment", {})["source_security_assurance"] = deepcopy(output["source_security_assurance"])
    return output


def assurance_headline(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    assurance = canonical.get("source_security_assurance") or {}
    state = assurance.get("status", "unverified")
    labels = ({"limited": "limitada", "unverified": "no verificada", "supported_scope": "disponible para el alcance compatible"}
        if spanish else {"limited": "limited", "unverified": "unverified", "supported_scope": "available for the supported scope"})
    text = (f"Garantía de evidencia de código y seguridad: {labels.get(state, labels['unverified'])}. "
        "La madurez técnica no es una calificación de seguridad del repositorio en su conjunto. " if spanish else
        f"Source/security evidence assurance: {labels.get(state, labels['unverified'])}. "
        "Technical maturity is not a repository-wide security rating. ")
    metrics = assurance.get("coverage_metrics") or {}
    eligible, observed = metrics.get("eligible_source_analysis") or {}, metrics.get("observed_supported_source_analysis") or {}
    if eligible.get("numerator") is not None and eligible.get("denominator") is not None:
        def percentage(metric: Mapping[str, Any]) -> str:
            return f"{metric['percentage']}%" if metric.get("percentage") is not None else "no verificado" if spanish else "unverified"
        text += (f"Código elegible analizado: {eligible['numerator']} / {eligible['denominator']} ({percentage(eligible)}); "
            if spanish else f"Eligible source analyzed: {eligible['numerator']} / {eligible['denominator']} ({percentage(eligible)}); ")
        text += (f"código compatible observado: {observed.get('numerator')} / {observed.get('denominator')} ({percentage(observed)}). "
            if spanish else f"observed supported source: {observed.get('numerator')} / {observed.get('denominator')} ({percentage(observed)}). ")
        unsampled = assurance.get("unsampled_eligible_source_files")
        if unsampled is not None:
            text += f"Elegibles sin muestrear: {unsampled}. " if spanish else f"Unsampled eligible files: {unsampled}. "
    if assurance.get("incomplete_required_scanner_count"):
        text += ("La ejecución de analizadores está incompleta." if spanish else "Scanner execution is incomplete.")
    return text.strip()


def apply_comprehensive_score_assurance_ledger_v45(payload: dict[str, Any]) -> dict[str, Any]:
    output = reconcile_scanner_claims_v45(apply_express_score_assurance_ledger_v45(payload))
    truth = output.get("canonical_report_truth")
    if not isinstance(truth, dict):
        truth = {}
        output["canonical_report_truth"] = truth
    truth.update(
        {
            "report_finality": "final",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "review_posture": "Required",
            "human_review_required": True,
            "client_delivery_allowed": False,
            "score_assurance_risk_contract_version": VERSION,
        }
    )
    output["report_finality"] = "final"
    output["approval_status"] = "pending_human_approval"
    output["delivery_status"] = "blocked_pending_human_approval"
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    return output


def install_comprehensive_score_assurance_ledger_v45() -> dict[str, Any]:
    from nico import comprehensive_canonical_truth as target

    current: Callable[[dict[str, Any]], dict[str, Any]] = target.canonicalize_comprehensive_payload
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def canonicalize(payload: dict[str, Any]) -> dict[str, Any]:
        return apply_comprehensive_score_assurance_ledger_v45(current(payload))

    setattr(canonicalize, _PATCH_MARKER, True)
    setattr(canonicalize, "_nico_previous", current)
    target.canonicalize_comprehensive_payload = canonicalize
    return {
        "status": "installed",
        "version": VERSION,
        "express_comprehensive_parity": True,
        "technical_score_controls_color": True,
        "scanner_ledger_not_scored": True,
        "scanner_claims_reconciled": True,
        "acceptance_outside_technical_maturity": True,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "apply_comprehensive_score_assurance_ledger_v45",
    "install_comprehensive_score_assurance_ledger_v45",
]
