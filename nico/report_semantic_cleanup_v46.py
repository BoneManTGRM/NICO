from __future__ import annotations

import re
from copy import deepcopy
from typing import Any

from nico.scanner_claim_reconciliation_v45 import reconcile_scanner_claims_v45

VERSION = "nico.report_semantic_cleanup.v46"
_TECHNICAL_IDS = {
    "code_audit",
    "dependency_health",
    "secrets_review",
    "static_analysis",
    "ci_cd",
    "architecture_debt",
    "velocity_complexity",
}
_SCANNER_IDS = {"scanner_worker_evidence", "scanner_evidence", "scanner_assurance_ledger"}
_ACCEPTANCE_IDS = {"client_human_acceptance", "client_acceptance", "human_acceptance"}
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")
_TREE_TEST_RE = re.compile(r"recursive repository tree contains\s+(\d+)\s+test-path", re.I)


def _text(value: Any) -> str:
    return " ".join(_CONTROL_RE.sub("", str(value or "")).split())


def _unique(values: list[Any]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = _text(raw)
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            output.append(value)
    return output


def _replace_finality(value: str) -> str:
    replacements = (
        ("DRAFT — HUMAN REVIEW REQUIRED", "FINAL REPORT - PENDING HUMAN APPROVAL"),
        ("DRAFT - HUMAN REVIEW REQUIRED", "FINAL REPORT - PENDING HUMAN APPROVAL"),
        ("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED", "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED"),
        ("Draft only", "Pending human approval"),
        ("draft only", "pending human approval"),
        ("complete only as a draft", "complete as a final report pending human approval"),
        ("Draft report package", "Final report package pending human approval"),
        ("draft report package", "final report package pending human approval"),
    )
    output = _CONTROL_RE.sub("", value)
    for old, new in replacements:
        output = output.replace(old, new)
    return output


def _recursive_clean(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_finality(value)
    if isinstance(value, list):
        return [_recursive_clean(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_recursive_clean(item) for item in value)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            canonical_key = {
                "draft_label": "report_label",
                "draft_status": "approval_status",
                "source_draft_pdf_sha256": "source_final_report_sha256",
            }.get(str(key), str(key))
            output[canonical_key] = _recursive_clean(item)
        return output
    return value


def _section_map(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("id") or ""): item
        for item in payload.get("sections") or []
        if isinstance(item, dict) and str(item.get("id") or "")
    }


def _normalize_confidence(section: dict[str, Any]) -> None:
    assurance = _text(section.get("assurance_label") or section.get("evidence_assurance") or "").upper()
    if assurance == "VERIFIED":
        confidence = "high"
    elif assurance == "REVIEW LIMITED":
        confidence = "review-limited"
    elif assurance in {"INCOMPLETE", "UNAVAILABLE"}:
        confidence = "low"
    elif assurance == "SUPPLEMENTAL":
        confidence = "supplemental"
    elif assurance == "PENDING HUMAN APPROVAL":
        confidence = "pending-human-approval"
    else:
        return
    section["confidence"] = confidence
    section["presented_confidence"] = confidence


def _remove_bounded_sample_false_priority(payload: dict[str, Any], sections: dict[str, dict[str, Any]]) -> None:
    code = sections.get("code_audit")
    if not code:
        return
    tree_count = 0
    for item in code.get("evidence") or []:
        match = _TREE_TEST_RE.search(_text(item))
        if match:
            tree_count = max(tree_count, int(match.group(1)))
    if tree_count <= 0:
        return

    def bounded_sample(value: Any) -> bool:
        text = _text(value).casefold()
        return "no test-path signals were found in fetched text files" in text

    code["findings"] = [item for item in code.get("findings") or [] if not bounded_sample(item)]
    code["review_items"] = [item for item in code.get("review_items") or [] if not bounded_sample(item)]
    code["bounded_sample_context"] = (
        f"A bounded fetched-text sample contained zero test paths, while the recursive repository tree contained {tree_count}; "
        "the sample result is context only and is not a repository-wide finding or repair priority."
    )

    for key in ("priority_actions", "quick_wins", "next_steps"):
        values = payload.get(key)
        if isinstance(values, list):
            payload[key] = [item for item in values if not bounded_sample(item)]
    repair = payload.get("repair_intelligence")
    if isinstance(repair, dict) and isinstance(repair.get("candidates"), list):
        repair["candidates"] = [
            item
            for item in repair["candidates"]
            if not bounded_sample(item.get("title") if isinstance(item, dict) else item)
        ]


def _move_acceptance_out_of_velocity(sections: dict[str, dict[str, Any]]) -> None:
    velocity = sections.get("velocity_complexity")
    acceptance = next((sections.get(key) for key in _ACCEPTANCE_IDS if sections.get(key)), None)
    if not velocity or not acceptance:
        return
    moved: list[str] = []
    retained: list[str] = []
    for item in velocity.get("unavailable") or []:
        text = _text(item)
        lowered = text.casefold()
        if any(token in lowered for token in ("client/human acceptance", "client acceptance", "approved final report", "final delivery scoring")):
            moved.append(text)
        else:
            retained.append(text)
    velocity["unavailable"] = _unique(retained)
    acceptance["review_items"] = _unique(list(acceptance.get("review_items") or []) + moved)
    acceptance["findings"] = []
    acceptance["unavailable"] = []
    acceptance["label"] = "Review and Delivery"
    acceptance["section_group"] = "review_delivery"
    acceptance["technical_section"] = False
    acceptance["score"] = None
    acceptance["presented_score"] = None
    acceptance["score_value"] = None


def normalize_final_report_semantics(payload: dict[str, Any]) -> dict[str, Any]:
    output = _recursive_clean(deepcopy(payload))
    output = reconcile_scanner_claims_v45(output)
    sections = _section_map(output)
    for section_id, section in sections.items():
        section["evidence"] = _unique(list(section.get("evidence") or []))
        section["findings"] = _unique(list(section.get("findings") or []))
        section["unavailable"] = _unique(list(section.get("unavailable") or []))
        section["review_items"] = _unique(list(section.get("review_items") or []))
        _normalize_confidence(section)
        if section_id in _SCANNER_IDS or section.get("section_group") == "assurance_ledger":
            section["label"] = "Scanner Assurance Ledger"
            section["section_group"] = "assurance_ledger"
            section["technical_section"] = False
        elif section_id not in _TECHNICAL_IDS:
            section["technical_section"] = False
            section.setdefault("section_group", "review_delivery" if section_id in _ACCEPTANCE_IDS else "supplemental")
    _remove_bounded_sample_false_priority(output, sections)
    _move_acceptance_out_of_velocity(sections)

    truth = output.get("canonical_report_truth")
    if not isinstance(truth, dict):
        truth = {}
        output["canonical_report_truth"] = truth
    truth.update(
        {
            "report_finality": "final",
            "approval_status": "pending_human_approval",
            "delivery_status": "blocked_pending_human_approval",
            "human_review_required": True,
            "client_delivery_allowed": False,
            "semantic_cleanup_version": VERSION,
        }
    )
    output["report_finality"] = "final"
    output["approval_status"] = "pending_human_approval"
    output["delivery_status"] = "blocked_pending_human_approval"
    output.pop("draft_only", None)
    output["human_review_required"] = True
    output["client_delivery_allowed"] = False
    output["semantic_report_quality"] = {
        "status": "normalized",
        "version": VERSION,
        "technical_score_assurance_risk_separated": True,
        "bounded_sample_false_priority_removed": True,
        "acceptance_outside_technical_maturity": True,
        "scanner_claims_reconciled": True,
        "scanner_control_renamed": True,
        "legacy_draft_metadata_removed": True,
        "control_characters_removed": True,
        "final_report_pending_approval": True,
    }
    return output


__all__ = ["VERSION", "normalize_final_report_semantics"]
