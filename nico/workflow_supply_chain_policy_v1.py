from __future__ import annotations

import re
from typing import Any, Iterable

VERSION = "nico.workflow_supply_chain_policy.v1"
_SHA_RE = re.compile(r"^[0-9a-f]{40}$", re.IGNORECASE)


def classify_action_reference(reference: str) -> dict[str, Any]:
    value = str(reference or "").strip()
    if "@" not in value:
        return {"reference": value, "pinned": False, "reason": "reference_missing_version"}
    action, version = value.rsplit("@", 1)
    if action.startswith("./"):
        return {"reference": value, "pinned": True, "reason": "local_action"}
    if _SHA_RE.fullmatch(version):
        return {"reference": value, "pinned": True, "reason": "immutable_commit_sha"}
    return {"reference": value, "pinned": False, "reason": "mutable_tag_or_branch"}


def audit_action_references(references: Iterable[str]) -> dict[str, Any]:
    items = [classify_action_reference(reference) for reference in references]
    mutable = [item["reference"] for item in items if not item["pinned"]]
    return {
        "schema": VERSION,
        "references": items,
        "all_external_actions_pinned": not mutable,
        "mutable_references": mutable,
        "exceptions_require_documented_owner_and_expiry": True,
        "review_required": bool(mutable),
    }


def validate_dependabot_policy(config: dict[str, Any]) -> dict[str, Any]:
    updates = config.get("updates") if isinstance(config.get("updates"), list) else []
    blockers: list[str] = []
    ecosystems = set()
    for index, update in enumerate(updates):
        if not isinstance(update, dict):
            blockers.append(f"updates[{index}]:invalid")
            continue
        ecosystem = str(update.get("package-ecosystem") or "")
        ecosystems.add(ecosystem)
        cooldown = update.get("cooldown") if isinstance(update.get("cooldown"), dict) else {}
        default_days = cooldown.get("default-days")
        if not isinstance(default_days, int) or not 1 <= default_days <= 90:
            blockers.append(f"{ecosystem or index}:cooldown_missing_or_invalid")
        groups = update.get("groups") if isinstance(update.get("groups"), dict) else {}
        if not groups:
            blockers.append(f"{ecosystem or index}:grouping_missing")
    for required in ("pip", "npm", "github-actions"):
        if required not in ecosystems:
            blockers.append(f"{required}:ecosystem_missing")
    return {
        "schema": "nico.dependabot_policy.v1",
        "ready": not blockers,
        "blockers": blockers,
        "security_updates_not_delayed_by_version_cooldown": True,
    }


def install_workflow_supply_chain_policy_v1() -> dict[str, Any]:
    return {
        "status": "installed",
        "version": VERSION,
        "immutable_action_refs_required": True,
        "mutable_refs_require_exception": True,
        "dependabot_cooldown_required": True,
        "dependabot_grouping_required": True,
    }


__all__ = [
    "VERSION",
    "classify_action_reference",
    "audit_action_references",
    "validate_dependabot_policy",
    "install_workflow_supply_chain_policy_v1",
]
