from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from nico.admin_security import require_admin_write
from nico.mid_assessment_runs import load_mid_assessment_run
from nico.mid_truth_status import (
    FAILED,
    HUMAN_REVIEW_REQUIRED,
    UNAVAILABLE,
    VERIFIED,
    VERIFIED_WITH_LIMITATIONS,
    build_mid_truth_status,
)
from nico.storage import STORE, StorageAdapter, utc_now

PACKET_VERSION = "mid-review-by-exception-v1"
CRITICAL_TERMS = ("critical", "high risk", "high-risk", "credential exposure", "secret exposure")
SCANNER_UNIT_IDS = {"snapshot_scanner_match", "dependency_scanners", "secret_scanners", "static_scanners"}


def _store(store: StorageAdapter | None = None) -> StorageAdapter:
    return store or STORE


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _text_list(value: Any) -> list[str]:
    return [str(item).strip() for item in _list(value) if str(item).strip()]


def _severity_rank(value: str) -> int:
    return {"critical": 4, "high": 3, "medium": 2, "low": 1, "informational": 0}.get(str(value).lower(), 0)


def _item_id(run_id: str, category: str, section_id: str, reason: str) -> str:
    digest = hashlib.sha256(f"{run_id}|{category}|{section_id}|{reason}".encode()).hexdigest()[:18]
    return f"midreview_{digest}"


def _add_item(items: list[dict[str, Any]], seen: set[tuple[str, str, str]], *, run_id: str, category: str, section_id: str, title: str, reason: str, severity: str = "medium", evidence: list[str] | None = None, blockers: list[str] | None = None, score_change_material: bool = False, inference_based: bool = False) -> None:
    key = (category, section_id, reason)
    if key in seen:
        return
    seen.add(key)
    items.append(
        {
            "item_id": _item_id(run_id, category, section_id, reason),
            "category": category,
            "section_id": section_id,
            "title": title,
            "reason": reason,
            "severity": severity,
            "evidence": sorted(set(evidence or [])),
            "blockers": sorted(set(blockers or [])),
            "score_change_material": bool(score_change_material),
            "inference_based": bool(inference_based),
            "requires_human_review": True,
            "decision_status": "pending",
        }
    )


def _finding_texts(section: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("findings", "risk_findings", "verified_claims", "unverified_claims"):
        for item in _list(section.get(key)):
            if isinstance(item, dict):
                text = str(item.get("title") or item.get("summary") or item.get("finding") or "").strip()
                severity = str(item.get("severity") or item.get("risk_level") or "").strip()
                if text:
                    values.append(f"{severity}: {text}" if severity else text)
            elif str(item).strip():
                values.append(str(item).strip())
    return values


def _high_risk_findings(section: dict[str, Any]) -> list[str]:
    values: list[str] = []
    explicit = str(section.get("risk_level") or section.get("severity") or "").lower()
    if explicit in {"critical", "high"}:
        values.extend(_finding_texts(section) or [str(section.get("summary") or section.get("label") or section.get("id") or "High-risk section")])
    for text in _finding_texts(section):
        lowered = text.lower()
        if any(term in lowered for term in CRITICAL_TERMS):
            values.append(text)
    return sorted(set(values))


def _conflicts(section: dict[str, Any]) -> list[str]:
    values: list[str] = []
    for key in ("conflicts", "conflicting_evidence", "contradictions"):
        values.extend(_text_list(section.get(key)))
    return sorted(set(values))


def _score_is_material(section: dict[str, Any]) -> bool:
    if section.get("score_change_material") is True:
        return True
    try:
        score = float(section.get("score"))
    except (TypeError, ValueError):
        return False
    return 0 <= score <= 100 and section.get("truth_status") != VERIFIED


def _source_packet(record: dict[str, Any]) -> dict[str, Any]:
    response = deepcopy(_dict(record.get("response")))
    truth = _dict(response.get("mid_truth_status"))
    if not truth.get("sections"):
        truth = build_mid_truth_status(response)
    return {
        "run_id": record.get("run_id") or "",
        "customer_id": record.get("customer_id") or "default_customer",
        "project_id": record.get("project_id") or "default_project",
        "repository": record.get("repository") or "",
        "snapshot_id": record.get("snapshot_id") or "",
        "snapshot_commit_sha": record.get("snapshot_commit_sha") or "",
        "status": record.get("status") or "unknown",
        "truth": truth,
        "scanner_evidence": response.get("scanner_evidence") or {},
        "optional_evidence": response.get("optional_evidence") or {},
        "assessment": response.get("assessment") or {},
        "export_truth_gate": response.get("export_truth_gate") or {},
    }


def build_mid_review_packet(
    run_id: str,
    customer_id: str,
    project_id: str,
    admin_token: str = "",
    store: StorageAdapter | None = None,
) -> dict[str, Any]:
    """Create one deterministic reviewer packet containing only exceptions plus collapsed verified sections."""

    allowed, admin = require_admin_write(admin_token)
    if not allowed:
        return {"status": "blocked", "error": "Admin authentication is required to inspect Mid review exceptions.", "admin_write": admin}
    active = _store(store)
    record = load_mid_assessment_run(str(run_id or ""), store=active)
    if not record:
        return {"status": "not_found", "error": "Mid Assessment run not found."}
    if str(record.get("customer_id") or "default_customer") != str(customer_id) or str(record.get("project_id") or "default_project") != str(project_id):
        return {"status": "not_found", "error": "Mid Assessment run not found."}

    source = _source_packet(record)
    truth = _dict(source["truth"])
    sections = [item for item in _list(truth.get("sections")) if isinstance(item, dict)]
    coverage = _dict(truth.get("evidence_coverage"))
    coverage_units = [item for item in _list(coverage.get("units")) if isinstance(item, dict)]
    summary = _dict(truth.get("summary"))
    items: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    verified_sections: list[dict[str, Any]] = []

    for section in sections:
        section_id = str(section.get("id") or "unknown")
        label = str(section.get("label") or section_id.replace("_", " ").title())
        status = str(section.get("truth_status") or UNAVAILABLE)
        evidence = _text_list(section.get("evidence"))
        missing = _text_list(section.get("missing_evidence_sources")) + _text_list(section.get("unavailable"))
        failed_tools = _text_list(section.get("failed_evidence_tools"))
        findings = _high_risk_findings(section)
        conflicts = _conflicts(section)

        if status == VERIFIED and not findings and not conflicts:
            verified_sections.append(
                {
                    "section_id": section_id,
                    "label": label,
                    "truth_status": VERIFIED,
                    "summary": str(section.get("summary") or "Direct evidence is available."),
                    "evidence_count": len(evidence),
                    "collapsed_by_default": True,
                }
            )
            continue

        if findings:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="critical_or_high_risk_finding",
                section_id=section_id,
                title=f"High-risk finding in {label}",
                reason="Critical or high-risk evidence requires explicit reviewer confirmation.",
                severity="critical" if any("critical" in item.lower() for item in findings) else "high",
                evidence=findings + evidence,
                score_change_material=_score_is_material(section),
            )
        if conflicts:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="conflicting_evidence",
                section_id=section_id,
                title=f"Conflicting evidence in {label}",
                reason="The section contains conflicting or contradictory evidence.",
                severity="high",
                evidence=conflicts + evidence,
                blockers=conflicts,
                score_change_material=_score_is_material(section),
            )
        if status == VERIFIED_WITH_LIMITATIONS:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="low_confidence_or_limited_conclusion",
                section_id=section_id,
                title=f"Limited conclusion in {label}",
                reason="The section is verified only with limitations and requires reviewer judgment.",
                severity="medium",
                evidence=evidence,
                blockers=missing,
                score_change_material=_score_is_material(section),
            )
        elif status == FAILED:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="incomplete_tool_execution",
                section_id=section_id,
                title=f"Failed evidence execution in {label}",
                reason="Required evidence collection or scanner execution failed.",
                severity="high",
                evidence=evidence,
                blockers=failed_tools + missing,
                score_change_material=_score_is_material(section),
            )
        elif status == UNAVAILABLE:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="missing_evidence_affecting_delivery",
                section_id=section_id,
                title=f"Unavailable evidence for {label}",
                reason="Evidence required to support this section is unavailable.",
                severity="medium",
                evidence=evidence,
                blockers=missing or [str(section.get("summary") or "Required evidence unavailable.")],
                score_change_material=_score_is_material(section),
            )
        elif status == HUMAN_REVIEW_REQUIRED:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="inference_or_external_context",
                section_id=section_id,
                title=f"Human validation required for {label}",
                reason="The section relies on user-submitted context or inference rather than direct repository proof.",
                severity="medium",
                evidence=evidence,
                blockers=missing,
                score_change_material=_score_is_material(section),
                inference_based=True,
            )

        if _score_is_material(section) and status != VERIFIED:
            _add_item(
                items,
                seen,
                run_id=run_id,
                category="score_changing_claim",
                section_id=section_id,
                title=f"Score-affecting claim in {label}",
                reason="A non-fully-verified section materially contributes to a reported score.",
                severity="high" if status in {FAILED, UNAVAILABLE} else "medium",
                evidence=evidence,
                blockers=failed_tools + missing,
                score_change_material=True,
                inference_based=status == HUMAN_REVIEW_REQUIRED,
            )

    for unit in coverage_units:
        if unit.get("available"):
            continue
        unit_id = str(unit.get("id") or "unknown")
        category = "incomplete_tool_execution" if unit_id in SCANNER_UNIT_IDS else "missing_evidence_affecting_delivery"
        _add_item(
            items,
            seen,
            run_id=run_id,
            category=category,
            section_id=f"coverage:{unit_id}",
            title=f"Missing coverage unit: {unit.get('label') or unit_id}",
            reason="A measured evidence-coverage unit is unavailable for this exact Mid run.",
            severity="high" if unit_id in SCANNER_UNIT_IDS else "medium",
            evidence=[str(unit.get("evidence") or "")],
            blockers=[str(unit.get("limitation") or "Evidence unit unavailable.")],
        )

    unsupported = int(summary.get("unsupported_claims_permitted") or truth.get("unsupported_claims_permitted") or 0)
    if unsupported:
        _add_item(
            items,
            seen,
            run_id=run_id,
            category="unsupported_claim",
            section_id="report",
            title="Unsupported claims detected",
            reason="The Mid report cannot proceed while unsupported claims are permitted.",
            severity="critical",
            blockers=[f"unsupported_claims_permitted={unsupported}"],
        )

    export_gate = _dict(source.get("export_truth_gate"))
    export_blockers = _text_list(export_gate.get("blockers"))
    if export_blockers:
        _add_item(
            items,
            seen,
            run_id=run_id,
            category="missing_evidence_affecting_delivery",
            section_id="export_truth_gate",
            title="Export truth gate blockers",
            reason="Delivery remains blocked by the export truth gate.",
            severity="high",
            blockers=export_blockers,
        )

    items.sort(key=lambda item: (-_severity_rank(str(item.get("severity"))), str(item.get("category")), str(item.get("section_id"))))
    source_identity = {
        "packet_version": PACKET_VERSION,
        "run_id": source["run_id"],
        "customer_id": source["customer_id"],
        "project_id": source["project_id"],
        "repository": source["repository"],
        "snapshot_id": source["snapshot_id"],
        "snapshot_commit_sha": source["snapshot_commit_sha"],
        "truth_version": truth.get("version") or "",
        "truth_sha256": _canonical_hash(truth),
        "exception_item_sha256": _canonical_hash(items),
        "verified_section_sha256": _canonical_hash(verified_sections),
    }
    packet_hash = _canonical_hash(source_identity)
    packet_id = f"mid_review_packet_{hashlib.sha256(f'{run_id}|{packet_hash}'.encode()).hexdigest()[:20]}"
    category_counts: dict[str, int] = {}
    for item in items:
        category = str(item.get("category") or "unknown")
        category_counts[category] = category_counts.get(category, 0) + 1
    packet = {
        "status": "ready_for_review",
        "packet_version": PACKET_VERSION,
        "review_packet_id": packet_id,
        "review_packet_sha256": packet_hash,
        "source_identity": source_identity,
        "run_id": source["run_id"],
        "customer_id": source["customer_id"],
        "project_id": source["project_id"],
        "repository": source["repository"],
        "snapshot_id": source["snapshot_id"],
        "snapshot_commit_sha": source["snapshot_commit_sha"],
        "generated_at": utc_now(),
        "exceptions": items,
        "verified_sections": verified_sections,
        "summary": {
            "section_count": len(sections),
            "sections_verified": len(verified_sections),
            "items_requiring_review": len(items),
            "unavailable_evidence_sources": int(summary.get("unavailable_evidence_sources") or 0),
            "unsupported_claims_permitted": unsupported,
            "critical_items": sum(1 for item in items if item.get("severity") == "critical"),
            "high_items": sum(1 for item in items if item.get("severity") == "high"),
            "inference_items": sum(1 for item in items if item.get("inference_based")),
            "score_changing_items": sum(1 for item in items if item.get("score_change_material")),
            "category_counts": category_counts,
        },
        "human_approval_required": True,
        "approval_controls_available": False,
        "approval_controls_note": "This packet supports focused review only. Approval controls become available only after the exact Mid draft report is generated and hash-bound to this packet.",
        "rule": "Verified sections are collapsed by default. Every critical/high-risk finding, conflict, limited conclusion, failed tool, score-changing claim, missing delivery evidence, and inference-based claim remains explicit for human review.",
    }
    active.put(
        "evidence_items",
        packet_id,
        {
            "evidence_id": packet_id,
            "customer_id": source["customer_id"],
            "project_id": source["project_id"],
            "run_id": source["run_id"],
            "filename": "mid-review-by-exception.json",
            "content_type": "application/json",
            "size_bytes": len(json.dumps(packet, default=str).encode()),
            "source": "mid_review_by_exception",
            "repository": source["repository"],
            "evidence": packet,
        },
    )
    active.audit(
        "mid.review_packet_generated",
        {
            "review_packet_id": packet_id,
            "review_packet_sha256": packet_hash,
            "run_id": source["run_id"],
            "snapshot_id": source["snapshot_id"],
            "snapshot_commit_sha": source["snapshot_commit_sha"],
            "items_requiring_review": len(items),
            "sections_verified": len(verified_sections),
            "unsupported_claims_permitted": unsupported,
        },
        customer_id=source["customer_id"],
        project_id=source["project_id"],
    )
    return packet
