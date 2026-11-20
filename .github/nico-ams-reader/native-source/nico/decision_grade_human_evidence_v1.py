from __future__ import annotations

import csv
import hashlib
import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

from nico.decision_grade_contract_v1 import (
    DecisionGradeContract,
    ReadinessStatus,
    ValidationIssue,
)

VERSION = "nico.decision_grade_human_evidence.v1"

MODULE_DEFINITIONS: tuple[dict[str, Any], ...] = (
    {
        "module_id": "functional_qa",
        "label": "Functional QA",
        "required_fields": ("test_cases", "observed_results"),
        "source_stages": ("functional_qa",),
        "description": "Human-observed functional scenarios, expected behavior, actual behavior, environment, evidence, and disposition.",
    },
    {
        "module_id": "platform_parity",
        "label": "Browser, device, and platform parity",
        "required_fields": ("matrix",),
        "source_stages": ("platform_parity",),
        "description": "Observed parity results by supported browser, device, operating system, application surface, and release.",
    },
    {
        "module_id": "accessibility_ux",
        "label": "Accessibility and UX review",
        "required_fields": ("observations",),
        "source_stages": ("functional_qa", "platform_parity"),
        "description": "Human accessibility and workflow-friction observations that repository analysis cannot prove alone.",
    },
    {
        "module_id": "stakeholder_context",
        "label": "Stakeholder objectives and constraints",
        "required_fields": ("objectives", "constraints"),
        "source_stages": ("stakeholder_and_business_alignment",),
        "description": "Named stakeholder goals, pain points, constraints, desired state, and decision priorities.",
    },
    {
        "module_id": "incident_history",
        "label": "Incident and support history",
        "required_fields": ("incidents",),
        "source_stages": ("stakeholder_and_business_alignment", "historical_trends_and_change_failure"),
        "description": "Human-confirmed incidents, customer-impacting defects, support themes, and operational consequences.",
    },
    {
        "module_id": "product_objectives",
        "label": "Product objectives and release outcomes",
        "required_fields": ("objectives", "success_measures"),
        "source_stages": ("stakeholder_and_business_alignment", "requirements_traceability"),
        "description": "Target outcomes and success measures used to connect technical findings to product decisions.",
    },
    {
        "module_id": "release_constraints",
        "label": "Release deadlines and delivery constraints",
        "required_fields": ("constraints",),
        "source_stages": ("stakeholder_and_business_alignment", "requirements_traceability"),
        "description": "Deadlines, contractual commitments, rollout constraints, rollback limits, and dependency dates.",
    },
    {
        "module_id": "compliance_requirements",
        "label": "Regulatory and contractual requirements",
        "required_fields": ("requirements",),
        "source_stages": ("stakeholder_and_business_alignment", "requirements_traceability"),
        "description": "Explicit obligations supplied by authorized stakeholders; this is readiness evidence, not certification.",
    },
    {
        "module_id": "budget_staffing",
        "label": "Budget, staffing, and capacity constraints",
        "required_fields": ("constraints",),
        "source_stages": ("stakeholder_and_business_alignment", "staffing_sequencing_and_cost"),
        "description": "Available roles, capacity, budget ranges, hiring constraints, and delivery ownership assumptions.",
    },
    {
        "module_id": "accepted_risks",
        "label": "Known decisions and accepted risks",
        "required_fields": ("decisions",),
        "source_stages": ("stakeholder_and_business_alignment", "human_review_request"),
        "description": "Named, time-bounded risk acceptances and architecture decisions with owner, rationale, and review date.",
    },
)


_COMPLETION_METADATA = ("reviewer", "observed_at", "source_reference")
_COMPLETE_SOURCE_STATES = {"", "complete", "completed", "attached", "available", "verified"}


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 2000) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 3)].rstrip() + "..."


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _stage(stage_results: dict[str, Any], names: tuple[str, ...]) -> tuple[str, dict[str, Any]]:
    for name in names:
        candidate = _record(stage_results.get(name))
        if candidate:
            return name, candidate
    return "", {}


def _intake_modules(value: Any) -> dict[str, dict[str, Any]]:
    source = _record(value)
    modules = source.get("modules")
    if isinstance(modules, dict):
        return {str(key): _record(item) for key, item in modules.items() if _record(item)}
    if isinstance(modules, list):
        return {
            _text(item.get("module_id"), 100): _record(item.get("evidence") or item)
            for item in modules
            if isinstance(item, dict) and _text(item.get("module_id"), 100)
        }
    return {
        str(key): _record(item)
        for key, item in source.items()
        if key not in {"artifact_schema", "instructions", "status"} and _record(item)
    }


def _candidate_payload(stage: dict[str, Any], module_id: str) -> dict[str, Any]:
    sources = (
        stage.get(module_id),
        _record(stage.get("human_evidence")).get(module_id),
        _record(stage.get("evidence")).get(module_id),
        _record(stage.get("decision_context")).get(module_id),
        _record(stage.get("intake")).get(module_id),
    )
    for source in sources:
        candidate = _record(source)
        if candidate:
            return candidate
    reserved = {
        "status",
        "message",
        "progress_percent",
        "current_stage",
        "stage_id",
        "human_review_required",
        "client_delivery_allowed",
        "unavailable_data_notes",
    }
    return {
        key: deepcopy(value)
        for key, value in stage.items()
        if key not in reserved and value not in (None, "", [], {})
    }


def _explicit_exclusion(stage: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, bool, str]:
    requested = payload.get("excluded") is True or str(payload.get("status") or "").casefold() in {
        "excluded",
        "out_of_scope",
    }
    rationale = _text(
        payload.get("exclusion_rationale")
        or payload.get("reason")
        or stage.get("exclusion_rationale"),
        1200,
    )
    return bool(requested and rationale), bool(requested), rationale


def _field_present(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    return value not in (None, "", [], {})


def _module_record(
    definition: dict[str, Any],
    *,
    stage_results: dict[str, Any],
    explicit_modules: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    module_id = str(definition["module_id"])
    source_stages = tuple(str(item) for item in definition["source_stages"])
    source_stage, stage = _stage(stage_results, source_stages)
    payload = _record(explicit_modules.get(module_id)) or (_candidate_payload(stage, module_id) if stage else {})
    excluded, exclusion_requested, exclusion_rationale = _explicit_exclusion(stage, payload)
    required_fields = tuple(str(item) for item in definition["required_fields"])
    present_fields = [field for field in required_fields if _field_present(payload, field)]
    missing_fields = [field for field in required_fields if field not in present_fields]
    present_metadata = [field for field in _COMPLETION_METADATA if _field_present(payload, field)]
    missing_metadata = [field for field in _COMPLETION_METADATA if field not in present_metadata]
    source_status = str(stage.get("status") or payload.get("source_status") or "").casefold()

    if excluded:
        status = "excluded"
        assurance = "EXCLUDED WITH RATIONALE"
    elif payload and not missing_fields and not missing_metadata and source_status in _COMPLETE_SOURCE_STATES:
        status = "complete"
        assurance = "HUMAN EVIDENCE RETAINED · REVIEW REQUIRED"
    elif payload:
        status = "partial"
        assurance = "REVIEW LIMITED"
        if exclusion_requested and not exclusion_rationale:
            missing_metadata.append("exclusion_rationale")
    else:
        status = "not_assessed"
        assurance = "NOT ASSESSED"

    return {
        "module_id": module_id,
        "label": definition["label"],
        "description": definition["description"],
        "status": status,
        "assurance": assurance,
        "source_stage": source_stage,
        "source_stage_status": source_status or "not_returned",
        "required_fields": list(required_fields),
        "present_fields": present_fields,
        "missing_fields": missing_fields,
        "required_metadata": list(_COMPLETION_METADATA),
        "present_metadata": present_metadata,
        "missing_metadata": sorted(set(missing_metadata)),
        "reviewer": _text(payload.get("reviewer"), 240),
        "observed_at": _text(payload.get("observed_at"), 100),
        "source_reference": _text(payload.get("source_reference"), 600),
        "evidence": payload,
        "exclusion_requested": exclusion_requested,
        "exclusion_rationale": exclusion_rationale,
        "human_observation_required": True,
        "repository_inference_allowed": False,
        "named_reviewer_required": status in {"complete", "partial"},
    }


def build_human_evidence_ledger(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, Any],
    intake: dict[str, Any] | None = None,
) -> dict[str, Any]:
    explicit = (
        intake
        or _record(identity.get("human_evidence_inputs"))
        or _record(stage_results.get("human_evidence_intake"))
    )
    explicit_modules = _intake_modules(explicit)
    modules = [
        _module_record(
            definition,
            stage_results=stage_results,
            explicit_modules=explicit_modules,
        )
        for definition in MODULE_DEFINITIONS
    ]
    incomplete = [item["module_id"] for item in modules if item["status"] in {"not_assessed", "partial"}]
    excluded = [item["module_id"] for item in modules if item["status"] == "excluded"]
    complete = [item["module_id"] for item in modules if item["status"] == "complete"]
    counts = {
        status: sum(item["status"] == status for item in modules)
        for status in ("complete", "partial", "not_assessed", "excluded")
    }
    return {
        "artifact_schema": VERSION,
        "status": "complete" if not incomplete else "review_limited",
        "repository": _text(identity.get("repository"), 260),
        "commit_sha": _text(identity.get("commit_sha"), 80),
        "run_id": _text(identity.get("run_id"), 180),
        "customer_id": _text(identity.get("customer_id"), 180),
        "project_id": _text(identity.get("project_id"), 180),
        "generated_at": _now(),
        "module_count": len(modules),
        "status_counts": counts,
        "complete_modules": complete,
        "excluded_modules": excluded,
        "incomplete_modules": incomplete,
        "modules": modules,
        "guardrail": (
            "Human, QA, parity, accessibility, incident, product, compliance, budget, and risk-acceptance claims "
            "are retained only when explicitly supplied or observed. Repository code is never used to fabricate these facts."
        ),
        "repository_inference_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def human_evidence_intake_template() -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "instructions": (
            "Provide only authorized factual observations. Every completed module requires a named reviewer, observation time, "
            "and source reference. Use explicit exclusions with rationale when a module is outside scope."
        ),
        "modules": [
            {
                "module_id": definition["module_id"],
                "label": definition["label"],
                "description": definition["description"],
                "required_fields": list(definition["required_fields"]),
                "status": "not_assessed",
                "excluded": False,
                "exclusion_rationale": "",
                "evidence": {field: [] for field in definition["required_fields"]},
                "reviewer": "",
                "observed_at": "",
                "source_reference": "",
            }
            for definition in MODULE_DEFINITIONS
        ],
    }


def _csv(rows: Iterable[dict[str, Any]], fields: tuple[str, ...]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=list(fields), extrasaction="ignore", lineterminator="\n")
    writer.writeheader()
    for row in rows:
        writer.writerow({field: _text(row.get(field), 5000) for field in fields})
    return buffer.getvalue()


def qa_register_csv(ledger: dict[str, Any]) -> str:
    module = next((item for item in _records(ledger.get("modules")) if item.get("module_id") == "functional_qa"), {})
    evidence = _record(module.get("evidence"))
    rows = _records(evidence.get("test_cases") or evidence.get("observed_results"))
    reviewer = module.get("reviewer")
    return _csv(
        [{**row, "reviewer": row.get("reviewer") or reviewer} for row in rows],
        (
            "test_id",
            "scenario",
            "environment",
            "expected",
            "actual",
            "status",
            "severity",
            "evidence_reference",
            "reviewer",
        ),
    )


def parity_matrix_csv(ledger: dict[str, Any]) -> str:
    module = next((item for item in _records(ledger.get("modules")) if item.get("module_id") == "platform_parity"), {})
    evidence = _record(module.get("evidence"))
    reviewer = module.get("reviewer")
    return _csv(
        [{**row, "reviewer": row.get("reviewer") or reviewer} for row in _records(evidence.get("matrix"))],
        (
            "surface",
            "platform",
            "operating_system",
            "browser_or_client",
            "version",
            "result",
            "difference",
            "severity",
            "evidence_reference",
            "reviewer",
        ),
    )


def stakeholder_decision_log_csv(ledger: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = []
    for module in _records(ledger.get("modules")):
        evidence = _record(module.get("evidence"))
        for decision in _records(evidence.get("decisions")):
            rows.append(
                {
                    "module_id": module.get("module_id"),
                    "reviewer": decision.get("reviewer") or module.get("reviewer"),
                    **decision,
                }
            )
    return _csv(
        rows,
        (
            "module_id",
            "decision_id",
            "decision",
            "owner",
            "rationale",
            "evidence_reference",
            "deadline",
            "review_date",
            "status",
            "reviewer",
        ),
    )


def ledger_json(ledger: dict[str, Any]) -> str:
    return json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def human_evidence_exports(ledger: dict[str, Any]) -> dict[str, Any]:
    ledger_text = ledger_json(ledger)
    intake_text = json.dumps(
        human_evidence_intake_template(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    qa_csv = qa_register_csv(ledger)
    parity_csv = parity_matrix_csv(ledger)
    decision_csv = stakeholder_decision_log_csv(ledger)
    hashes = {
        "ledger_json_sha256": _hash(ledger_text),
        "intake_template_json_sha256": _hash(intake_text),
        "qa_register_csv_sha256": _hash(qa_csv),
        "parity_matrix_csv_sha256": _hash(parity_csv),
        "stakeholder_decision_log_csv_sha256": _hash(decision_csv),
    }
    return {
        "schema_version": VERSION,
        "status": ledger.get("status"),
        "ledger": ledger,
        "ledger_json": ledger_text,
        "intake_template": human_evidence_intake_template(),
        "intake_template_json": intake_text,
        "qa_register_csv": qa_csv,
        "parity_matrix_csv": parity_csv,
        "stakeholder_decision_log_csv": decision_csv,
        "hashes": hashes,
        "repository_inference_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _issue_key(issue: ValidationIssue) -> tuple[str, tuple[str, ...]]:
    return issue.code, tuple(sorted(issue.related_ids))


def _append_issue(contract: DecisionGradeContract, issue: ValidationIssue) -> None:
    existing = {_issue_key(item) for item in contract.validation_issues}
    if _issue_key(issue) not in existing:
        contract.validation_issues.append(issue)


def apply_human_evidence_to_contract(
    contract: DecisionGradeContract,
    ledger: dict[str, Any],
) -> DecisionGradeContract:
    output = contract.model_copy(deep=True)
    modules = _records(ledger.get("modules"))
    incomplete = [str(item.get("module_id")) for item in modules if item.get("status") in {"partial", "not_assessed"}]
    invalid_exclusions = [
        str(item.get("module_id"))
        for item in modules
        if item.get("exclusion_requested") and not item.get("exclusion_rationale")
    ]
    inferred = [
        str(item.get("module_id"))
        for item in modules
        if item.get("repository_inference_allowed") is not False
    ]
    if incomplete:
        _append_issue(
            output,
            ValidationIssue(
                code="human_evidence_incomplete",
                severity="error",
                message=(
                    "Required human-evidence modules are partial or not assessed. The report must disclose the gaps and remain review-limited."
                ),
                related_ids=incomplete,
            ),
        )
        if output.readiness_status not in {ReadinessStatus.DELIVERY_BLOCKED, ReadinessStatus.EVIDENCE_INCOMPLETE}:
            output.readiness_status = ReadinessStatus.EVIDENCE_INCOMPLETE
    if invalid_exclusions:
        _append_issue(
            output,
            ValidationIssue(
                code="human_evidence_exclusion_rationale_missing",
                severity="critical",
                message="A human-evidence module requested exclusion without a retained rationale.",
                related_ids=invalid_exclusions,
            ),
        )
        output.readiness_status = ReadinessStatus.DELIVERY_BLOCKED
    if inferred:
        _append_issue(
            output,
            ValidationIssue(
                code="human_evidence_repository_inference_prohibited",
                severity="critical",
                message="Human evidence cannot be inferred from repository source or automated scanner output.",
                related_ids=inferred,
            ),
        )
        output.readiness_status = ReadinessStatus.DELIVERY_BLOCKED
    return output


__all__ = [
    "MODULE_DEFINITIONS",
    "VERSION",
    "apply_human_evidence_to_contract",
    "build_human_evidence_ledger",
    "human_evidence_exports",
    "human_evidence_intake_template",
    "ledger_json",
    "parity_matrix_csv",
    "qa_register_csv",
    "stakeholder_decision_log_csv",
]
