from __future__ import annotations

from copy import deepcopy
from typing import Any

import nico.mid_approval_api as approval_api
import nico.mid_assessment_approval as approval_service
import nico.mid_review_enforcement as enforcement
from nico.storage import STORE, StorageAdapter

_COMPAT_INSTALLED = False
_BASE_ENFORCED_VALIDATE = enforcement._enforced_validate_mid_approval


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _active_store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _compat_validate_mid_approval(value: Any, store: StorageAdapter | None = None) -> dict[str, Any]:
    approval = value if isinstance(value, dict) else {}
    result = deepcopy(_BASE_ENFORCED_VALIDATE(approval, store=store))
    if str(approval.get("approval_version") or "") == enforcement.MID_APPROVAL_ENFORCED_VERSION:
        for check in _list(result.get("checks")):
            if isinstance(check, dict) and check.get("id") == "approval_version":
                check["passed"] = True
                check["message"] = "The production Mid approval uses the enforced version-three contract."
        result = enforcement._recompute_validation(result)
    return result


def _production_request_mid_approval(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _active_store(store)
    result = enforcement._ORIGINALS["request_mid_approval"](
        run_id,
        customer_id,
        project_id,
        admin_token=admin_token,
        store=active,
    )
    approval = _dict(_dict(result).get("approval"))
    approval_id = str(approval.get("approval_id") or "")
    stored = active.get("approvals", approval_id) if approval_id else None
    if not isinstance(stored, dict):
        return result

    is_new = result.get("idempotent_reuse") is False
    is_enforced = str(stored.get("approval_version") or "") == enforcement.MID_APPROVAL_ENFORCED_VERSION
    if not is_new and not is_enforced:
        return result

    updated = deepcopy(stored)
    if is_new:
        updated["approval_version"] = enforcement.MID_APPROVAL_ENFORCED_VERSION
    updated["review_disposition_required"] = True
    updated["review_disposition_policy_version"] = enforcement.MID_REVIEW_ENFORCEMENT_VERSION
    updated.setdefault("review_item_dispositions", {})
    updated.setdefault("review_item_disposition_sha256", "")
    updated.setdefault("review_disposition_set_sha256", "")
    updated.setdefault("review_disposition_count", 0)
    updated["approval_identity"] = enforcement._request_identity(updated)
    updated["approval_identity_sha256"] = enforcement._canonical_hash(updated["approval_identity"])
    active.put("approvals", approval_id, updated)
    return {
        **result,
        "approval": enforcement._enforced_public_approval(updated, store=active),
    }


def _production_transition_mid_approval(
    approval_id: str,
    state: str,
    actor: str,
    note: str = "",
    reviewed_item_ids: list[str] | None = None,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = _active_store(store)
    approval = active.get("approvals", approval_id)
    requested = str(state or "").strip().lower()
    if isinstance(approval, dict) and enforcement._is_enforced(approval) and requested == "approved":
        summary = enforcement._strict_review_disposition_summary(approval, store=active)
        if summary.get("approval_ready"):
            disposition_hash = str(summary.get("disposition_set_sha256") or "")
            staged = deepcopy(approval)
            staged_decision = _dict(staged.get("review_decision"))
            staged_decision["review_disposition_set_sha256"] = disposition_hash
            staged_decision["review_disposition_count"] = int(summary.get("expected_item_count") or 0)
            staged["review_decision"] = staged_decision
            staged_report = _dict(staged.get("approved_report"))
            staged_report["review_disposition_set_sha256"] = disposition_hash
            staged_report["review_disposition_count"] = int(summary.get("expected_item_count") or 0)
            staged["approved_report"] = staged_report
            active.put("approvals", approval_id, staged)
    return enforcement._enforced_transition_mid_approval(
        approval_id,
        state,
        actor,
        note=note,
        reviewed_item_ids=reviewed_item_ids,
        admin_token=admin_token,
        store=active,
    )


def install_mid_review_enforcement_compat() -> dict[str, Any]:
    global _COMPAT_INSTALLED
    base = enforcement.install_mid_review_enforcement()
    if _COMPAT_INSTALLED:
        return {**base, "compatibility_installed": True, "compatibility_idempotent_reuse": True}

    approval_service.MID_APPROVAL_VERSION = "mid-report-approval-v2"
    approval_service.request_mid_approval = enforcement._ORIGINALS["request_mid_approval"]
    approval_service.transition_mid_approval = enforcement._ORIGINALS["transition_mid_approval"]
    enforcement._enforced_validate_mid_approval = _compat_validate_mid_approval
    approval_service.validate_mid_approval = _compat_validate_mid_approval
    approval_api.request_mid_approval = _production_request_mid_approval
    approval_api.transition_mid_approval = _production_transition_mid_approval

    _COMPAT_INSTALLED = True
    return {
        **base,
        "compatibility_installed": True,
        "compatibility_idempotent_reuse": False,
        "service_api_legacy_default": "mid-report-approval-v2",
        "production_api_enforced_default": enforcement.MID_APPROVAL_ENFORCED_VERSION,
    }


__all__ = ["install_mid_review_enforcement_compat"]
