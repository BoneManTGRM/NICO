from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.express_score_assurance_ledger_v45 import apply_express_score_assurance_ledger_v45
from nico.scanner_claim_reconciliation_v45 import reconcile_scanner_claims_v45

VERSION = "nico.comprehensive_score_assurance_ledger.v45"
_PATCH_MARKER = "_nico_comprehensive_score_assurance_ledger_v45"


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
