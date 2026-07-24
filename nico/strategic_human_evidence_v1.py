from __future__ import annotations

import csv
import io
import json
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable

VERSION = "nico.strategic_human_evidence.v1"

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
        "description": "Human accessibility and workflow-friction observations that automated source review cannot prove alone.",
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


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 1600) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: max(0, limit - 3)].rstrip() + "..."


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    return [deepcopy(item) for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _stage(stage_results: dict[str, Any], names: tuple[str, ...]) -> dict[str, Any]:
    for name in names:
        candidate = _record(stage_results.get(name))
        if candidate:
            return candidate
    return {}


def _candidate_payload(stage: dict[str, Any], module_id: str) -> dict[str, Any]:
    sources = (
        stage.get(module_id),
        _record(stage.get("human_evidence")).get(module_id),
        _record(stage.get("evidence")).get(module_id),
        _record(stage.get("strategic_evidence")).get(module_id),
        _record(stage.get("intake")).get(module_id),
    )
    for source in sources:
        candidate = _record(source)
        if candidate:
            return candidate
    # A stage dedicated to this module may return its fields at the top level.
    reserved = {
        "status", "message", "progress_percent", "current_stage", "stage_id",
        "human_review_required", "client_delivery_allowed", "unavailable_data_notes",
    }
    candidate = {key: deepcopy(value) for key, value in stage.items() if key not in reserved and value not in (None, "", [], {})}
    return candidate


def _explicit_exclusion(stage: dict[str, Any], payload: dict[str, Any]) -> tuple[bool, str]:
    excluded = payload.get("excluded") is True or str(payload.get("status") or "").casefold() in {"excluded", "out_of_scope"}
    rationale = _text(payload.get("exclusion_rationale") or payload.get("reason") or stage.get("exclusion_rationale"), 900)
    return bool(excluded and rationale), rationale


def _field_present(payload: dict[str, Any], field: str) -> bool:
    value = payload.get(field)
    return value not in (None, "", [], {})


def build_strategic_human_evidence_ledger(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, Any],
) -> dict[str, Any]:
    modules: list[dict[str, Any]] = []
    for definition in MODULE_DEFINITIONS:
        module_id = str(definition["module_id"])
        source_stages = tuple(str(item) for item in definition["source_stages"])
        stage = _stage(stage_results, source_stages)
        payload = _candidate_payload(stage, module_id) if stage else {}
        excluded, exclusion_rationale = _explicit_exclusion(stage, payload)
        required_fields = tuple(str(item) for item in definition["required_fields"])
        present_fields = [field for field in required_fields if _field_present(payload, field)]
        missing_fields = [field for field in required_fields if field not in present_fields]
        source_status = str(stage.get("status") or "").casefold()

        if excluded:
            status = "excluded"
            assurance = "EXCLUDED WITH RATIONALE"
        elif payload and not missing_fields and source_status in {"complete", "completed", "attached", "available", ""}:
            status = "complete"
            assurance = "REVIEW REQUIRED"
        elif payload:
            status = "partial"
            assurance = "REVIEW LIMITED"
        else:
            status = "not_assessed"
            assurance = "NOT ASSESSED"

        modules.append(
            {
                "module_id": module_id,
                "label": definition["label"],
                "description": definition["description"],
                "status": status,
                "assurance": assurance,
                "source_stage": next((name for name in source_stages if _record(stage_results.get(name))), ""),
                "source_stage_status": source_status or "not_returned",
                "required_fields": list(required_fields),
                "present_fields": present_fields,
                "missing_fields": missing_fields,
                "evidence": payload,
                "exclusion_rationale": exclusion_rationale,
                "human_observation_required": True,
                "repository_inference_allowed": False,
                "named_reviewer_required": status in {"complete", "partial"},
            }
        )

    incomplete = [item["module_id"] for item in modules if item["status"] in {"not_assessed", "partial"}]
    excluded = [item["module_id"] for item in modules if item["status"] == "excluded"]
    complete = [item["module_id"] for item in modules if item["status"] == "complete"]
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
        "complete_modules": complete,
        "excluded_modules": excluded,
        "incomplete_modules": incomplete,
        "modules": modules,
        "guardrail": "Human, QA, parity, accessibility, incident, product, compliance, budget, and risk-acceptance claims are retained only when explicitly supplied or observed. Repository code is never used to fabricate these facts.",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def strategic_intake_template() -> dict[str, Any]:
    return {
        "artifact_schema": VERSION,
        "instructions": "Provide only authorized, factual observations. Use explicit exclusions with rationale when a module is outside scope.",
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
    return _csv(
        rows,
        ("test_id", "scenario", "environment", "expected", "actual", "status", "severity", "evidence_reference", "reviewer"),
    )


def parity_matrix_csv(ledger: dict[str, Any]) -> str:
    module = next((item for item in _records(ledger.get("modules")) if item.get("module_id") == "platform_parity"), {})
    evidence = _record(module.get("evidence"))
    rows = _records(evidence.get("matrix"))
    return _csv(
        rows,
        ("surface", "platform", "operating_system", "browser_or_client", "version", "result", "difference", "severity", "evidence_reference", "reviewer"),
    )


def stakeholder_decision_log_csv(ledger: dict[str, Any]) -> str:
    rows: list[dict[str, Any]] = []
    for module in _records(ledger.get("modules")):
        evidence = _record(module.get("evidence"))
        decisions = _records(evidence.get("decisions"))
        for decision in decisions:
            rows.append({"module_id": module.get("module_id"), **decision})
    return _csv(
        rows,
        ("module_id", "decision_id", "decision", "owner", "rationale", "evidence_reference", "deadline", "review_date", "status"),
    )


def ledger_json(ledger: dict[str, Any]) -> str:
    return json.dumps(ledger, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


__all__ = [
    "MODULE_DEFINITIONS",
    "VERSION",
    "build_strategic_human_evidence_ledger",
    "ledger_json",
    "parity_matrix_csv",
    "qa_register_csv",
    "stakeholder_decision_log_csv",
    "strategic_intake_template",
]
