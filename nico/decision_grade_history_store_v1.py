from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable

from nico.decision_grade_contract_v1 import AssessmentType, DecisionGradeContract
from nico.storage import STORE, StorageAdapter

VERSION = "nico.decision_grade_history_store.v1"


def _text(value: Any, limit: int = 1000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _walk_dicts(value: Any, *, max_depth: int = 7) -> Iterable[dict[str, Any]]:
    queue: list[tuple[Any, int]] = [(value, 0)]
    seen: set[int] = set()
    while queue:
        current, depth = queue.pop(0)
        if depth > max_depth:
            continue
        if isinstance(current, dict):
            identity = id(current)
            if identity in seen:
                continue
            seen.add(identity)
            yield current
            for key, item in current.items():
                if key in {"pdf_base64", "content", "raw_bytes"}:
                    continue
                if isinstance(item, (dict, list, tuple)):
                    queue.append((item, depth + 1))
        elif isinstance(current, (list, tuple)):
            queue.extend((item, depth + 1) for item in current if isinstance(item, (dict, list, tuple)))


def _extract_contract(record: dict[str, Any]) -> tuple[DecisionGradeContract | None, dict[str, Any] | None]:
    response = record.get("response") if isinstance(record.get("response"), dict) else record
    contract: DecisionGradeContract | None = None
    assessment: dict[str, Any] | None = None
    for node in _walk_dicts(response):
        if contract is None:
            raw = node.get("decision_grade_contract")
            if isinstance(raw, dict) and raw.get("status") != "invalid":
                try:
                    contract = DecisionGradeContract.model_validate(raw)
                except Exception:
                    pass
        if assessment is None:
            raw_assessment = node.get("assessment")
            if isinstance(raw_assessment, dict) and (
                "technical_score" in raw_assessment
                or "canonical_evidence_adjusted_score" in raw_assessment
                or "maturity_signal" in raw_assessment
            ):
                assessment = deepcopy(raw_assessment)
        if contract is not None and assessment is not None:
            break
    return contract, assessment


def _chronology(record: dict[str, Any], contract: DecisionGradeContract) -> tuple[str, str, str]:
    return (
        _text(contract.identity.assessment_completed_at or contract.generated_at, 100),
        _text(record.get("updated_at"), 100),
        _text(record.get("created_at"), 100),
    )


def find_previous_compatible_assessment(
    *,
    repository: str,
    assessment_type: AssessmentType | str,
    current_assessment_id: str,
    customer_id: str | None = None,
    project_id: str | None = None,
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    active = store or STORE
    normalized_repository = _text(repository, 500).casefold()
    normalized_type = AssessmentType(assessment_type)
    current_id = _text(current_assessment_id, 240)
    status = active.status()
    records = active.list("assessment_runs", customer_id=customer_id, project_id=project_id)
    candidates: list[tuple[tuple[str, str, str], dict[str, Any], DecisionGradeContract, dict[str, Any] | None]] = []
    rejected = {
        "current_assessment": 0,
        "non_full_workflow": 0,
        "missing_or_invalid_contract": 0,
        "repository_mismatch": 0,
        "assessment_type_mismatch": 0,
    }

    for record in records:
        if not isinstance(record, dict):
            continue
        record_id = _text(record.get("run_id") or record.get("id"), 240)
        if record_id == current_id:
            rejected["current_assessment"] += 1
            continue
        workflow = _text(record.get("workflow"), 100).casefold()
        if workflow and workflow != "full_assessment":
            rejected["non_full_workflow"] += 1
            continue
        contract, assessment = _extract_contract(record)
        if contract is None:
            rejected["missing_or_invalid_contract"] += 1
            continue
        if contract.identity.repository_identifier.casefold() != normalized_repository:
            rejected["repository_mismatch"] += 1
            continue
        if contract.identity.assessment_type != normalized_type:
            rejected["assessment_type_mismatch"] += 1
            continue
        candidates.append((_chronology(record, contract), record, contract, assessment))

    candidates.sort(key=lambda item: item[0], reverse=True)
    adapter = _text(status.get("adapter") or status.get("mode") or "unknown", 80)
    persistence_available = bool(status.get("persistence_available"))
    durability_verified = bool(
        status.get("durability_verified")
        or status.get("survives_container_replacement_verified")
        or (adapter == "postgres" and persistence_available)
    )
    base = {
        "schema_version": VERSION,
        "repository": repository,
        "assessment_type": normalized_type.value,
        "current_assessment_id": current_id,
        "records_examined": len(records),
        "compatible_candidate_count": len(candidates),
        "rejected_counts": rejected,
        "storage_adapter": adapter,
        "persistence_available": persistence_available,
        "durability_verified": durability_verified,
        "synthetic_history_generated": False,
    }
    if not candidates:
        return {
            **base,
            "status": "no_comparable_previous_assessment",
            "selected": False,
            "reason": "No retained compatible decision-grade contract was found in the authorized storage scope.",
        }

    _, record, contract, assessment = candidates[0]
    return {
        **base,
        "status": "selected",
        "selected": True,
        "previous_assessment_id": contract.identity.assessment_id,
        "previous_commit_sha": contract.identity.assessed_commit_sha,
        "previous_completed_at": contract.identity.assessment_completed_at or contract.generated_at,
        "record_id": _text(record.get("run_id") or record.get("id"), 240),
        "previous_decision_grade_contract": contract.model_dump(mode="json"),
        "previous_assessment": assessment,
        "selection_rule": "newest compatible retained contract by assessment completion and storage timestamps",
    }


def enrich_report_identity_with_history(
    identity: dict[str, Any],
    *,
    assessment_type: AssessmentType | str = AssessmentType.COMPREHENSIVE,
    store: StorageAdapter | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    output = deepcopy(identity)
    selection = find_previous_compatible_assessment(
        repository=_text(identity.get("repository"), 500),
        assessment_type=assessment_type,
        current_assessment_id=_text(identity.get("run_id") or identity.get("assessment_id"), 240),
        customer_id=_text(identity.get("customer_id"), 240) or None,
        project_id=_text(identity.get("project_id"), 240) or None,
        store=store,
    )
    output["historical_comparison_selection"] = {
        key: deepcopy(value)
        for key, value in selection.items()
        if key not in {"previous_decision_grade_contract", "previous_assessment"}
    }
    if selection.get("selected") is True:
        output["previous_comparable_assessment_id"] = selection["previous_assessment_id"]
        output["previous_decision_grade_contract"] = deepcopy(selection["previous_decision_grade_contract"])
        if isinstance(selection.get("previous_assessment"), dict):
            output["previous_assessment"] = deepcopy(selection["previous_assessment"])
    return output, selection


__all__ = [
    "VERSION",
    "find_previous_compatible_assessment",
    "enrich_report_identity_with_history",
]
