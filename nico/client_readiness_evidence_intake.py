from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

VERSION = "nico.client-readiness-evidence-intake.v1"
SECTION_STATUSES = {"assessed", "limited", "not_applicable", "pending"}

SECTION_DEFINITIONS = {
    "functional_qa": {
        "title": "Functional QA",
        "required_inputs": ["critical journeys", "runtime environment", "browser/device matrix", "acceptance results"],
    },
    "platform_parity": {
        "title": "Platform Parity",
        "required_inputs": ["platform scope", "runnable builds", "feature matrix", "permission/localization evidence"],
    },
    "historical_trends_and_change_failure": {
        "title": "Historical Trends and Change Failure",
        "required_inputs": ["incident records", "deployment records", "rollback records", "recovery-time evidence"],
    },
    "requirements_traceability": {
        "title": "Requirements Traceability",
        "required_inputs": ["approved specifications", "ADRs", "contractual requirements", "acceptance criteria"],
    },
    "stakeholder_and_business_alignment": {
        "title": "Stakeholder and Business Alignment",
        "required_inputs": ["decision owner", "technical approver", "budget authority", "success measures"],
    },
    "risk_reduction_and_executive_briefing": {
        "title": "Risk Reduction and Executive Briefing",
        "required_inputs": ["finding dispositions", "risk owners", "remediation owners", "acceptance evidence"],
    },
    "six_month_roadmap": {
        "title": "Six-Month Roadmap",
        "required_inputs": ["approved sequencing", "dependencies", "owners", "acceptance criteria"],
    },
    "staffing_sequencing_and_cost": {
        "title": "Staffing, Sequencing, and Cost",
        "required_inputs": ["approved scope", "capacity", "delivery model", "rates and budget ceiling"],
    },
}


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _valid_digest(value: Any) -> bool:
    return bool(re.fullmatch(r"[0-9a-fA-F]{64}", _text(value)))


def client_evidence_intake_template(*, repository: str = "", commit_sha: str = "", run_id: str = "") -> dict[str, Any]:
    sections = []
    for section_id, definition in SECTION_DEFINITIONS.items():
        sections.append(
            {
                "section_id": section_id,
                "title": definition["title"],
                "status": "pending",
                "required_inputs": list(definition["required_inputs"]),
                "evidence": [],
                "conclusion": "",
                "limitations": [],
                "justification": "",
                "reviewer": {},
                "accepted_limitations": {},
                "not_applicable_authorization": {},
            }
        )
    return {
        "schema_version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "client_delivery_allowed": False,
        "automation_may_complete_client_evidence": False,
        "sections": sections,
        "rule": "Client and reviewer evidence must be supplied explicitly; automation cannot infer missing stakeholder input.",
    }


def _authority_errors(value: Any, prefix: str) -> list[str]:
    authority = value if isinstance(value, Mapping) else {}
    errors: list[str] = []
    for key in ("identity", "role", "authorization_basis", "recorded_at"):
        if not _text(authority.get(key)):
            errors.append(f"{prefix}.{key} is required")
    if authority.get("authorized") is not True:
        errors.append(f"{prefix}.authorized must be true")
    return errors


def _evidence_errors(evidence: Any) -> list[str]:
    if not isinstance(evidence, list) or not evidence:
        return ["at least one retained evidence record is required"]
    errors: list[str] = []
    ids: list[str] = []
    for index, item in enumerate(evidence):
        record = item if isinstance(item, Mapping) else {}
        evidence_id = _text(record.get("evidence_id"))
        ids.append(evidence_id)
        for key in ("evidence_id", "source_type", "submitted_by", "submitted_at", "scope"):
            if not _text(record.get(key)):
                errors.append(f"evidence[{index}].{key} is required")
        if not _valid_digest(record.get("artifact_sha256")):
            errors.append(f"evidence[{index}].artifact_sha256 must be a SHA-256 digest")
    duplicates = sorted(value for value, count in Counter(ids).items() if value and count > 1)
    if duplicates:
        errors.append(f"duplicate evidence_id values: {', '.join(duplicates)}")
    return errors


def _section_errors(section: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    section_id = _text(section.get("section_id"))
    definition = SECTION_DEFINITIONS.get(section_id)
    if not definition:
        return ["section_id is not canonical"]
    if _text(section.get("title")) != definition["title"]:
        errors.append("section title does not match the canonical title")
    status = _text(section.get("status")).lower()
    if status not in SECTION_STATUSES:
        errors.append(f"unsupported section status: {status or 'blank'}")
        return errors
    if status == "pending":
        return errors

    errors.extend(_authority_errors(section.get("reviewer"), "reviewer"))
    if not _text(section.get("conclusion")):
        errors.append("conclusion is required for a completed section")

    if status == "assessed":
        errors.extend(_evidence_errors(section.get("evidence")))
    elif status == "limited":
        errors.extend(_evidence_errors(section.get("evidence")))
        limitations = section.get("limitations")
        if not isinstance(limitations, list) or not any(_text(item) for item in limitations):
            errors.append("limited sections require explicit limitations")
        errors.extend(_authority_errors(section.get("accepted_limitations"), "accepted_limitations"))
        if not _text((section.get("accepted_limitations") or {}).get("scope")):
            errors.append("accepted_limitations.scope is required")
    elif status == "not_applicable":
        if not _text(section.get("justification")):
            errors.append("not_applicable sections require a justification")
        errors.extend(_authority_errors(section.get("not_applicable_authorization"), "not_applicable_authorization"))
        if not _text((section.get("not_applicable_authorization") or {}).get("scope")):
            errors.append("not_applicable_authorization.scope is required")
    return errors


def build_client_evidence_register(
    sections: Iterable[Mapping[str, Any]],
    *,
    repository: str,
    commit_sha: str,
    run_id: str,
) -> dict[str, Any]:
    section_records = [deepcopy(dict(item)) for item in sections if isinstance(item, Mapping)]
    section_ids = [_text(item.get("section_id")) for item in section_records]
    duplicates = sorted(value for value, count in Counter(section_ids).items() if value and count > 1)
    missing = sorted(set(SECTION_DEFINITIONS).difference(section_ids))
    unexpected = sorted(set(section_ids).difference(SECTION_DEFINITIONS))
    invalid_sections: list[dict[str, Any]] = []
    for record in section_records:
        errors = _section_errors(record)
        if errors:
            invalid_sections.append({"section_id": _text(record.get("section_id")), "errors": errors})

    pending = sorted(
        _text(record.get("section_id"))
        for record in section_records
        if _text(record.get("status")).lower() == "pending"
    )
    blockers: list[str] = []
    if duplicates:
        blockers.append(f"duplicate client evidence sections: {', '.join(duplicates)}")
    if missing:
        blockers.append(f"missing client evidence sections: {', '.join(missing)}")
    if unexpected:
        blockers.append(f"unexpected client evidence sections: {', '.join(unexpected)}")
    if pending:
        blockers.append(f"pending client evidence sections: {', '.join(pending)}")
    if invalid_sections:
        blockers.append("one or more client evidence sections are invalid")

    normalized_sections = []
    for record in sorted(section_records, key=lambda item: _text(item.get("section_id"))):
        normalized_sections.append({**record, "section_digest": _sha256(record)})
    complete = not blockers
    basis = {
        "version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "section_digests": [item["section_digest"] for item in normalized_sections],
    }
    return {
        "schema_version": VERSION,
        "repository": _text(repository),
        "commit_sha": _text(commit_sha),
        "run_id": _text(run_id),
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "status": "passed" if complete else "blocked",
        "evidence_complete": complete,
        "client_delivery_allowed": False,
        "automation_may_complete_client_evidence": False,
        "section_count": len(normalized_sections),
        "pending_section_ids": pending,
        "missing_section_ids": missing,
        "unexpected_section_ids": unexpected,
        "duplicate_section_ids": duplicates,
        "invalid_sections": invalid_sections,
        "blockers": blockers,
        "sections": normalized_sections,
        "register_digest": _sha256(basis),
        "rule": "Every human-review section must be explicitly assessed, limited with authorized acceptance, or authorized as not applicable; pending evidence blocks delivery.",
    }


def client_evidence_gate(register: Mapping[str, Any], *, expected_repository: str, expected_commit_sha: str, expected_run_id: str) -> dict[str, Any]:
    blockers: list[str] = []
    if str(register.get("schema_version") or "") != VERSION:
        blockers.append("client evidence schema version is missing or unsupported")
    if _text(register.get("repository")) != _text(expected_repository):
        blockers.append("client evidence repository identity does not match")
    if _text(register.get("commit_sha")).lower() != _text(expected_commit_sha).lower():
        blockers.append("client evidence commit identity does not match")
    if _text(register.get("run_id")) != _text(expected_run_id):
        blockers.append("client evidence run identity does not match")
    if register.get("evidence_complete") is not True:
        blockers.append("client evidence is incomplete")
    if register.get("blockers") or register.get("invalid_sections"):
        blockers.append("client evidence contains unresolved blockers")
    if int(register.get("section_count") or 0) != len(SECTION_DEFINITIONS):
        blockers.append("client evidence section population does not reconcile")
    if not _valid_digest(register.get("register_digest")):
        blockers.append("client evidence register digest is missing or invalid")
    return {
        "status": "passed" if not blockers else "blocked",
        "ready_for_next_gate": not blockers,
        "client_delivery_allowed": False,
        "blockers": blockers,
        "register_digest": register.get("register_digest") or "",
        "rule": "Passing client evidence is necessary but never sufficient for client delivery authorization.",
    }


__all__ = [
    "SECTION_DEFINITIONS",
    "SECTION_STATUSES",
    "VERSION",
    "build_client_evidence_register",
    "client_evidence_gate",
    "client_evidence_intake_template",
]
