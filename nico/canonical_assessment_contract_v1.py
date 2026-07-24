from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

VERSION = "nico.canonical_assessment_contract.v1"

TECHNICAL_MODULES: tuple[str, ...] = (
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
    "test_strategy",
    "runtime_operations",
    "security_architecture",
    "privacy_data",
    "performance_scalability",
    "documentation_dx",
)

HUMAN_EVIDENCE_MODULES: tuple[str, ...] = (
    "functional_qa",
    "platform_parity",
    "accessibility_ux",
    "stakeholder_context",
    "incident_and_support_history",
    "product_objectives",
    "release_constraints",
    "regulatory_contractual_requirements",
    "budget_staffing_constraints",
    "accepted_risks_and_decisions",
)


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(value) if isinstance(value, dict) else {}


def _records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [deepcopy(item) for item in value if isinstance(item, dict)]


def _text(value: Any, limit: int = 500) -> str:
    normalized = " ".join(str(value or "").split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: max(0, limit - 3)].rstrip() + "..."


def _first(*values: Any, limit: int = 500) -> str:
    for value in values:
        candidate = _text(value, limit)
        if candidate:
            return candidate
    return ""


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _sha256(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def normalize_depth(value: Any) -> str:
    normalized = _text(value, 40).casefold().replace("-", "_")
    if normalized in {"strategic", "comprehensive", "mid", "full", "deep"}:
        return "strategic"
    return "core"


def _assessment(payload: dict[str, Any]) -> dict[str, Any]:
    direct = _record(payload.get("assessment"))
    if direct:
        return direct
    if isinstance(payload.get("sections"), list):
        return {"sections": _records(payload.get("sections"))}
    return {}


def _scanner(payload: dict[str, Any]) -> dict[str, Any]:
    for key in ("scanner", "scanner_run", "scanner_evidence", "scanner_worker"):
        candidate = _record(payload.get(key))
        if candidate:
            return candidate
    return {}


def _snapshot(payload: dict[str, Any]) -> dict[str, Any]:
    return _record(payload.get("repository_snapshot") or payload.get("snapshot"))


def _reports(payload: dict[str, Any]) -> dict[str, Any]:
    return _record(payload.get("reports") or payload.get("report_package"))


def build_identity(payload: dict[str, Any], *, depth: Any = None, language: Any = None) -> dict[str, str]:
    snapshot = _snapshot(payload)
    scanner = _scanner(payload)
    reports = _reports(payload)
    evidence_bundle = _record(payload.get("evidence_artifact_bundle") or payload.get("evidence_bundle"))

    return {
        "repository": _first(
            payload.get("repository"),
            snapshot.get("repository"),
            snapshot.get("repository_full_name"),
            limit=240,
        ),
        "commit_sha": _first(
            payload.get("commit_sha"),
            snapshot.get("commit_sha"),
            snapshot.get("snapshot_commit_sha"),
            limit=80,
        ),
        "tree_sha": _first(payload.get("tree_sha"), snapshot.get("tree_sha"), limit=80),
        "run_id": _first(payload.get("run_id"), payload.get("assessment_run_id"), limit=180),
        "customer_id": _first(payload.get("customer_id"), limit=180),
        "project_id": _first(payload.get("project_id"), limit=180),
        "scanner_run_id": _first(
            scanner.get("scan_id"),
            scanner.get("scanner_run_id"),
            scanner.get("run_id"),
            limit=180,
        ),
        "evidence_bundle_sha256": _first(
            evidence_bundle.get("bundle_hash"),
            evidence_bundle.get("sha256"),
            payload.get("evidence_bundle_hash"),
            limit=128,
        ),
        "report_sha256": _first(
            reports.get("pdf_sha256"),
            reports.get("canonical_truth_sha256"),
            reports.get("report_artifact_digest"),
            payload.get("canonical_truth_sha256"),
            limit=128,
        ),
        "assessment_depth": normalize_depth(
            depth
            or payload.get("assessment_depth")
            or payload.get("assessment_type")
            or payload.get("service_tier")
        ),
        "report_language": _first(
            language,
            payload.get("report_language"),
            payload.get("language"),
            "en",
            limit=24,
        ),
    }


def build_score_assurance_ledger(payload: dict[str, Any]) -> list[dict[str, Any]]:
    assessment = _assessment(payload)
    ledger: list[dict[str, Any]] = []

    for index, section in enumerate(_records(assessment.get("sections")), start=1):
        control_id = _first(section.get("id"), section.get("control_id"), f"control_{index}", limit=120)
        score = section.get("presented_score")
        if not isinstance(score, (int, float)):
            score = section.get("score")
        technical_score = int(score) if isinstance(score, (int, float)) else None

        ledger.append(
            {
                "control_id": control_id,
                "label": _first(section.get("label"), section.get("title"), control_id, limit=220),
                "technical_score": technical_score,
                "technical_band": _first(
                    section.get("score_band_label"),
                    section.get("score_band"),
                    "NOT SCORED" if technical_score is None else "UNCLASSIFIED",
                    limit=80,
                ).upper(),
                "evidence_assurance": _first(
                    section.get("assurance_label"),
                    section.get("evidence_assurance"),
                    section.get("assurance_status"),
                    "UNAVAILABLE",
                    limit=80,
                ).upper(),
                "risk_disposition": _first(
                    section.get("risk_disposition"),
                    section.get("risk_status"),
                    section.get("status"),
                    "REVIEW REQUIRED",
                    limit=80,
                ).upper(),
                "included_in_maturity": bool(
                    section.get("exclude_from_maturity") is not True
                    and technical_score is not None
                ),
            }
        )

    return ledger


def build_module_status(payload: dict[str, Any], *, depth: Any = None) -> list[dict[str, Any]]:
    assessment = _assessment(payload)
    normalized_depth = normalize_depth(
        depth
        or payload.get("assessment_depth")
        or payload.get("assessment_type")
        or payload.get("service_tier")
    )
    section_ids = {
        _first(item.get("id"), item.get("control_id"), limit=120)
        for item in _records(assessment.get("sections"))
    }

    status: list[dict[str, Any]] = []
    for module_id in TECHNICAL_MODULES:
        status.append(
            {
                "module_id": module_id,
                "module_family": "technical",
                "status": "complete" if module_id in section_ids else "not_assessed",
                "human_evidence_required": False,
            }
        )

    for module_id in HUMAN_EVIDENCE_MODULES:
        source = payload.get(module_id)
        retained = bool(source)
        status.append(
            {
                "module_id": module_id,
                "module_family": "human_evidence",
                "status": (
                    "complete"
                    if retained
                    else "not_assessed"
                    if normalized_depth == "strategic"
                    else "not_in_core_scope"
                ),
                "human_evidence_required": True,
                "repository_inference_prohibited": True,
            }
        )

    return status


def build_canonical_assessment_contract(
    payload: dict[str, Any],
    *,
    depth: Any = None,
    language: Any = None,
) -> dict[str, Any]:
    identity = build_identity(payload, depth=depth, language=language)
    required_identity = ("repository", "commit_sha", "run_id")
    missing_identity = [key for key in required_identity if not identity.get(key)]

    contract: dict[str, Any] = {
        "schema_version": VERSION,
        "status": "complete" if not missing_identity else "review_limited",
        "identity": identity,
        "missing_required_identity": missing_identity,
        "canonical_score_and_assurance_ledger": build_score_assurance_ledger(payload),
        "module_status": build_module_status(payload, depth=identity["assessment_depth"]),
        "one_canonical_run_required": True,
        "independent_core_and_strategic_scorecards_allowed": False,
        "technical_score_assurance_and_risk_are_separate": True,
        "human_evidence_may_be_inferred_from_repository": False,
        "automatic_approval": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    contract["contract_sha256"] = _sha256(contract)
    return contract


def attach_canonical_assessment_contract(
    payload: dict[str, Any],
    *,
    depth: Any = None,
    language: Any = None,
) -> dict[str, Any]:
    output = deepcopy(payload)
    output["canonical_assessment_contract"] = build_canonical_assessment_contract(
        output,
        depth=depth,
        language=language,
    )
    return output


__all__ = [
    "HUMAN_EVIDENCE_MODULES",
    "TECHNICAL_MODULES",
    "VERSION",
    "attach_canonical_assessment_contract",
    "build_canonical_assessment_contract",
    "build_identity",
    "build_module_status",
    "build_score_assurance_ledger",
    "normalize_depth",
]
