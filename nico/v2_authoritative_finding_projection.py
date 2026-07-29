from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, MutableMapping

VERSION = "nico.v2.authoritative-finding-projection.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def project_finding_classification_in_place(canonical: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    """Propagate canonical scope/disposition fields to every copied finding surface.

    Roadmap, backlog, executive, and remediation surfaces often retain copies of
    canonical findings. Enriching those copies in the first pass keeps finalization
    deterministic and idempotent instead of changing them only on a second pass.
    """

    findings = [
        item for item in canonical.get("canonical_findings") or []
        if isinstance(item, Mapping)
    ]
    by_id = {
        _text(item.get("finding_id") or item.get("id")): item
        for item in findings
        if _text(item.get("finding_id") or item.get("id"))
    }

    def project(value: Any) -> Any:
        if isinstance(value, Mapping):
            item = deepcopy(dict(value))
            identifier = _text(item.get("finding_id") or item.get("id"))
            source = by_id.get(identifier)
            if source is not None:
                for field_name in ("production_scope", "technical_score_impact", "disposition"):
                    if field_name in source:
                        item[field_name] = deepcopy(source[field_name])
            return {key: project(child) for key, child in item.items()}
        if isinstance(value, list):
            return [project(child) for child in value]
        if isinstance(value, tuple):
            return tuple(project(child) for child in value)
        return value

    for surface in (
        "executive_findings",
        "executive_risk_register",
        "priority_findings",
        "roadmap",
        "backlog",
        "remediation_plan",
        "recommendations",
        "work_packages",
        "decision_backlog",
    ):
        if surface in canonical:
            canonical[surface] = project(canonical[surface])

    contract = canonical.get("authoritative_report_truth")
    if isinstance(contract, Mapping):
        contract = deepcopy(dict(contract))
        contract["classification_projected_to_all_finding_surfaces"] = True
        canonical["authoritative_report_truth"] = contract
    return canonical


__all__ = ["VERSION", "project_finding_classification_in_place"]
