from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "nico.client_report_truth_contract.v63"
ANALYZER_STATUSES = {
    "requested",
    "applicable",
    "completed",
    "completed_with_findings",
    "failed",
    "incomplete",
    "review_required",
    "not_applicable",
}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _dict(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, list) else []


def _truthy(value: Any) -> bool:
    return value is True or _text(value).casefold() in {"true", "yes", "verified", "approved", "1"}


def _unique_text(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value)
        if text and text.casefold() not in seen:
            seen.add(text.casefold())
            output.append(text)
    return output


def _limitations(node: Mapping[str, Any]) -> list[str]:
    values: list[Any] = []
    for key in (
        "limitations",
        "unavailable",
        "unavailable_or_limited_evidence",
        "missing_evidence_sources",
        "failed_evidence_tools",
        "unverified_claims",
        "evidence_limitations",
        "unresolved_limitations",
    ):
        value = node.get(key)
        if isinstance(value, list):
            values.extend(value)
        elif value:
            values.append(value)
    return _unique_text(values)


def _review_count(node: Mapping[str, Any]) -> int:
    for key in (
        "review_required",
        "review_required_count",
        "review_candidate_count",
        "review_candidates",
        "unverified_candidates",
    ):
        value = node.get(key)
        if isinstance(value, list):
            return len(value)
        if isinstance(value, int) and not isinstance(value, bool):
            return max(0, value)
    return 0


def _section_name(section: Mapping[str, Any]) -> str:
    return _text(section.get("id") or section.get("label") or section.get("title")).casefold()


def _score(section: Mapping[str, Any]) -> int | None:
    try:
        value = int(round(float(section.get("score"))))
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 100 else None


def _section_evidence_status(section: Mapping[str, Any]) -> str:
    review_count = _review_count(section)
    if review_count > 0:
        return "review_required"
    if _limitations(section):
        evidence = _list(section.get("evidence")) + _list(section.get("verified_claims"))
        return "partially_verified" if evidence else "insufficient_evidence"
    evidence = _list(section.get("evidence")) + _list(section.get("verified_claims"))
    if evidence:
        return "verified"
    human_status = _text(section.get("human_evidence_status")).casefold()
    if human_status in {"not_assessed", "missing", "unavailable"}:
        return "not_assessed"
    return "insufficient_evidence"


def _finding_evidence_status(finding: Mapping[str, Any]) -> str:
    quality = _text(finding.get("evidence_quality") or finding.get("evidence_status")).casefold()
    disposition = _text(finding.get("disposition")).casefold()
    exact = _truthy(finding.get("exact_commit_match")) or "exact commit match=true" in quality
    retained = bool(
        finding.get("observed_evidence")
        or finding.get("evidence")
        or finding.get("artifact_hash")
        or finding.get("source")
        or finding.get("location")
        or finding.get("exact_source")
    )
    if "not assessed" in quality:
        return "not_assessed"
    if "insufficient" in quality or (not retained and not exact):
        return "insufficient_evidence"
    if "review required" in quality or "review required" in disposition:
        return "review_required"
    if "inferred" in quality:
        return "inferred"
    if exact and retained:
        return "verified"
    if retained:
        return "partially_verified"
    return "insufficient_evidence"


def _confidence(evidence_status: str) -> str:
    return {
        "verified": "high_confidence",
        "partially_verified": "medium_confidence",
        "review_required": "medium_confidence",
        "inferred": "low_confidence",
        "insufficient_evidence": "no_confidence",
        "not_assessed": "no_confidence",
    }.get(evidence_status, "no_confidence")


def _normalize_finding(finding: Mapping[str, Any]) -> dict[str, Any]:
    output = _dict(finding)
    evidence_status = _finding_evidence_status(output)
    output["evidence_status"] = evidence_status
    output["confidence"] = _confidence(evidence_status)
    output["human_review_status"] = (
        "required" if evidence_status != "verified" or "proposed" in _text(output.get("disposition")).casefold() else "recommended"
    )
    return output


def _normalize_findings(node: Any, parent_key: str = "") -> Any:
    if isinstance(node, list):
        if "finding" in parent_key.casefold():
            return [_normalize_finding(item) if isinstance(item, Mapping) else item for item in node]
        return [_normalize_findings(item, parent_key) for item in node]
    if not isinstance(node, Mapping):
        return node
    output: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(value, list) and "finding" in str(key).casefold():
            output[str(key)] = [
                _normalize_finding(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            output[str(key)] = _normalize_findings(value, str(key))
    return output


def _normalize_section(section: Mapping[str, Any]) -> dict[str, Any]:
    output = _dict(section)
    name = _section_name(output)
    evidence_status = _section_evidence_status(output)
    review_count = _review_count(output)
    output["evidence_status"] = evidence_status
    output["human_review_status"] = "required" if evidence_status != "verified" else "recommended"
    output["limitations"] = _limitations(output)
    output["score_status"] = "evidence_bound"

    if any(token in name for token in ("dependency", "library ecosystem", "secret")) and review_count > 0:
        score = _score(output)
        output["status_display"] = "Provisional Strong" if score is not None and score >= 80 else "Provisional"
        output["human_review_status"] = "required"
        output["evidence_status"] = "review_required"
        output["score_status"] = "assurance_only_until_triaged"
        output["confirmed_material_findings"] = int(output.get("verified_material") or 0)
        output["review_required_candidates"] = review_count
        output["score_effect"] = "assurance_only_until_triaged"

    if "ci/cd" in name or "ci_cd" in name or "continuous integration" in name:
        required_check = output.get("assessed_commit_required_check_health", "not_observed")
        default_health = output.get("current_default_branch_required_check_health", "not_observed")
        output["ci_status"] = {
            "configuration_maturity_score": _score(output),
            "operational_readiness": "human_review_required",
            "required_check_health": required_check,
            "current_default_branch_health": default_health,
            "historical_workflow_reliability": output.get("historical_reliability") or "reported_separately_unscored",
            "configuration_score_is_not_operational_readiness": True,
        }
    return output


def _normalize_sections(node: Any) -> Any:
    if isinstance(node, list):
        return [_normalize_sections(item) for item in node]
    if not isinstance(node, Mapping):
        return node
    output: dict[str, Any] = {}
    for key, value in node.items():
        if str(key) == "sections" and isinstance(value, list):
            output[str(key)] = [
                _normalize_section(item) if isinstance(item, Mapping) else item
                for item in value
            ]
        else:
            output[str(key)] = _normalize_sections(value)
    return output


def _normalize_analyzer_records(output: dict[str, Any]) -> None:
    records = output.get("scanner_execution_records")
    if not isinstance(records, list):
        assessment = output.get("assessment") if isinstance(output.get("assessment"), Mapping) else {}
        records = assessment.get("scanner_execution_records")
    if not isinstance(records, list):
        return
    normalized: list[dict[str, Any]] = []
    for item in records:
        if not isinstance(item, Mapping):
            continue
        record = _dict(item)
        raw_status = _text(record.get("status") or record.get("state") or record.get("execution_status")).casefold().replace("-", "_")
        if raw_status not in ANALYZER_STATUSES:
            if record.get("completed") is True:
                findings = record.get("findings")
                raw_status = "completed_with_findings" if isinstance(findings, list) and findings else "completed"
            else:
                raw_status = "incomplete"
        record["authoritative_status"] = raw_status
        record["status_model_version"] = VERSION
        normalized.append(record)
    output["authoritative_analyzer_statuses"] = normalized


def _approval_metadata(output: Mapping[str, Any]) -> dict[str, Any]:
    current = _dict(output.get("human_approval_metadata"))
    return {
        "reviewer_name_or_id": _text(current.get("reviewer_name_or_id")),
        "reviewer_role": _text(current.get("reviewer_role")),
        "approval_timestamp": _text(current.get("approval_timestamp")),
        "approval_decision": _text(current.get("approval_decision")) or "pending",
        "unresolved_limitations": _unique_text(_list(current.get("unresolved_limitations"))),
        "evidence_manifest_reviewed": _truthy(current.get("evidence_manifest_reviewed")),
        "scanner_candidates_triaged": _truthy(current.get("scanner_candidates_triaged")),
        "client_delivery_authorized": _truthy(current.get("client_delivery_authorized")),
    }


def _approved(metadata: Mapping[str, Any]) -> bool:
    return bool(
        _text(metadata.get("reviewer_name_or_id"))
        and _text(metadata.get("reviewer_role"))
        and _text(metadata.get("approval_timestamp"))
        and _text(metadata.get("approval_decision")).casefold() in {"approved", "approved_with_limitations"}
        and metadata.get("evidence_manifest_reviewed") is True
        and metadata.get("scanner_candidates_triaged") is True
        and metadata.get("client_delivery_authorized") is True
    )


def apply_client_report_truth_contract(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = _normalize_sections(_normalize_findings(deepcopy(dict(canonical))))
    _normalize_analyzer_records(output)
    metadata = _approval_metadata(output)
    approved = _approved(metadata)

    sections = [item for item in _list(output.get("sections")) if isinstance(item, Mapping)]
    limitations = _unique_text(
        [text for section in sections for text in _limitations(section)]
        + _list(metadata.get("unresolved_limitations"))
    )
    review_required = any(
        _section_evidence_status(section) in {"review_required", "partially_verified", "insufficient_evidence", "not_assessed"}
        for section in sections
    )
    evidence_status = "evidence_bound_with_review_required" if review_required else "evidence_bound"

    truth = {
        "version": VERSION,
        "automated_status": "human_approved_final" if approved else "automated_draft",
        "evidence_status": evidence_status,
        "human_review_status": "approved" if approved else "pending_human_approval",
        "client_delivery_status": "authorized" if approved else "blocked_pending_human_approval",
        "score_status": "human_verified" if approved else "automated_evidence_adjusted_provisional",
        "limitations": limitations,
        "facts_interpretations_separated": True,
        "unsupported_claims_permitted": 0,
        "missing_evidence_converted_to_pass": False,
    }
    output["canonical_report_truth"] = truth
    output["human_approval_metadata"] = metadata
    output.update(
        {
            "automated_status": truth["automated_status"],
            "evidence_status": truth["evidence_status"],
            "human_review_status": truth["human_review_status"],
            "client_delivery_status": truth["client_delivery_status"],
            "score_status": truth["score_status"],
            "limitations": limitations,
            "report_finality": "approved_final" if approved else "automated_draft",
            "approval_status": "approved" if approved else "pending_human_approval",
            "human_review_required": not approved,
            "human_review_completed": approved,
            "client_ready": approved,
            "client_delivery_allowed": approved,
        }
    )
    return output


def report_truth_markdown(canonical: Mapping[str, Any], *, spanish: bool = False) -> str:
    truth = _dict(canonical.get("canonical_report_truth"))
    limitations = _unique_text(_list(truth.get("limitations")))
    if spanish:
        lines = [
            "## Estado del informe y límite de revisión",
            "",
            "- Estado automatizado: Borrador automatizado" if truth.get("automated_status") != "human_approved_final" else "- Estado automatizado: Final aprobado por una persona",
            f"- Estado de evidencia: {_text(truth.get('evidence_status'))}",
            "- Revisión humana: Pendiente" if truth.get("human_review_status") != "approved" else "- Revisión humana: Aprobada",
            "- Entrega al cliente: Bloqueada" if truth.get("client_delivery_status") != "authorized" else "- Entrega al cliente: Autorizada",
            f"- Estado de puntuación: {_text(truth.get('score_status'))}",
        ]
        if limitations:
            lines.extend(["", "### Limitaciones no resueltas", ""] + [f"- {item}" for item in limitations])
    else:
        lines = [
            "## Report Status and Review Boundary",
            "",
            "- Automated status: Automated Draft" if truth.get("automated_status") != "human_approved_final" else "- Automated status: Human Approved Final",
            f"- Evidence status: {_text(truth.get('evidence_status'))}",
            "- Human review: Pending Human Approval" if truth.get("human_review_status") != "approved" else "- Human review: Approved",
            "- Client delivery: Client Delivery Blocked" if truth.get("client_delivery_status") != "authorized" else "- Client delivery: Client Delivery Authorized",
            f"- Score status: {_text(truth.get('score_status'))}",
        ]
        if limitations:
            lines.extend(["", "### Unresolved limitations", ""] + [f"- {item}" for item in limitations])
    return "\n".join(lines).strip() + "\n"


__all__ = [
    "ANALYZER_STATUSES",
    "VERSION",
    "apply_client_report_truth_contract",
    "report_truth_markdown",
]
