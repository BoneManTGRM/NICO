from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.v2.canonical-surface-sync.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def synchronize_canonical_finding_surfaces(value: Mapping[str, Any]) -> dict[str, Any]:
    canonical = deepcopy(dict(value))
    findings = [deepcopy(dict(item)) for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    by_id: dict[str, dict[str, Any]] = {}
    for item in findings:
        identities = [
            item.get("finding_id"),
            item.get("id"),
            *(item.get("finding_aliases") or []),
        ]
        for raw in identities:
            identity = _text(raw)
            if identity:
                by_id[identity] = item

    def sync(node: Any) -> Any:
        if isinstance(node, list):
            return [sync(item) for item in node]
        if not isinstance(node, Mapping):
            return node
        original = dict(node)
        repaired = {key: sync(item) for key, item in original.items()}
        identity = _text(original.get("finding_id") or original.get("id"))
        source = by_id.get(identity)
        if source is not None:
            for key, item in source.items():
                repaired[key] = deepcopy(item)
        return repaired

    for surface in (
        "executive_findings",
        "finding_cards",
        "backlog",
        "roadmap",
        "work_packages",
        "remediation_plan",
        "recommendations",
        "assessment",
        "stage_summaries",
    ):
        if surface in canonical:
            canonical[surface] = sync(canonical[surface])
    contract = canonical.get("v2_canonical_premium_truth") if isinstance(canonical.get("v2_canonical_premium_truth"), Mapping) else {}
    contract = deepcopy(dict(contract))
    contract["all_finding_linked_surfaces_synchronized"] = True
    canonical["v2_canonical_premium_truth"] = contract
    return canonical


__all__ = ["VERSION", "synchronize_canonical_finding_surfaces"]
