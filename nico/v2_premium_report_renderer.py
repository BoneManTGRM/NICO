from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_report_package import _markdown, _pdf, _semantic_html

VERSION = "nico.v2.premium-report-renderer.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _stage(stage_id: str, title: str, summary: str, *, evidence: list[str] | None = None,
           findings: list[str] | None = None, unavailable: list[str] | None = None,
           status: str = "complete") -> dict[str, Any]:
    return {
        "stage_id": stage_id,
        "title": title,
        "status": status,
        "summary": summary,
        "evidence": list(evidence or []),
        "findings": list(findings or []),
        "unavailable": list(unavailable or []),
    }


def _finding_lines(findings: list[Mapping[str, Any]]) -> list[str]:
    output: list[str] = []
    for item in findings:
        identifier = _text(item.get("finding_id") or item.get("id"))
        title = _text(item.get("title") or item.get("decision_title"))
        priority = _text(item.get("priority") or item.get("severity") or "P2")
        location = _text(item.get("location"))
        impact = _text(item.get("business_impact") or item.get("impact"))
        recommendation = _text(item.get("recommendation"))
        output.append(
            f"{priority} · {title} · {identifier} · {location or 'location not retained'} · "
            f"Impact: {impact or 'requires review'} · Recommendation: {recommendation or 'requires review'}"
        )
    return output


def _scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    evidence = []
    for item in records:
        evidence.append(
            f"{_text(item.get('scanner_name') or item.get('tool'))}: "
            f"{_text(item.get('state') or item.get('status'))}; "
            f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
            f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
            f"findings={len(item.get('findings') or [])}"
        )
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner evidence incomplete')}"
        for item in incomplete
    ]
    status = "complete" if not incomplete else "review_required"
    return [
        _stage(
            "dependency_security_static_analysis",
            "Dependency, Security, and Static Analysis",
            f"{len(completed)} scanner records completed and {len(incomplete)} remain incomplete or review-limited.",
            evidence=evidence,
            unavailable=limitations,
            status=status,
        )
    ]


def _canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    existing = [deepcopy(dict(item)) for item in canonical.get("stage_summaries") or [] if isinstance(item, Mapping)]
    by_id = {_text(item.get("stage_id")): item for item in existing if _text(item.get("stage_id"))}
    for item in _scanner_stages(canonical):
        by_id[item["stage_id"]] = item

    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    by_id["risk_reduction_and_executive_briefing"] = _stage(
        "risk_reduction_and_executive_briefing",
        "Executive Risk Register and Decision Briefing",
        f"The canonical register contains {len(findings)} unique decision-grade findings.",
        findings=_finding_lines(findings),
        status="complete",
    )

    roadmap = [item for item in canonical.get("roadmap") or [] if isinstance(item, Mapping)]
    roadmap_evidence: list[str] = []
    for window in roadmap:
        label = _text(window.get("window") or window.get("title"))
        objective = _text(window.get("objective"))
        roadmap_evidence.append(f"{label}: {objective}")
        for work in window.get("work_packages") or []:
            if isinstance(work, Mapping):
                roadmap_evidence.append(
                    f"{label} · {_text(work.get('work_package_id') or work.get('id'))}: "
                    f"{_text(work.get('title') or work.get('objective'))}; "
                    f"owner={_text(work.get('owner_role') or work.get('owner'))}; "
                    f"effort={_text(work.get('effort') or work.get('effort_range'))}"
                )
    if roadmap_evidence:
        by_id["six_month_roadmap"] = _stage(
            "six_month_roadmap",
            "Six-Month Roadmap",
            "The roadmap is generated from the canonical findings and retained delivery evidence.",
            evidence=roadmap_evidence,
            status="complete",
        )

    return list(by_id.values())


def rebuild_premium_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    canonical = deepcopy(dict(result.get("json") or {})) if isinstance(result.get("json"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    stages = _canonical_stages(canonical)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    markdown = _markdown(dict(identity), dict(assessment), stages, generated_at)
    markdown = markdown.replace(
        "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
        "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY NOT AUTHORIZED",
    )
    title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
    rendered_html = _semantic_html(markdown, title)
    pdf_base64, pdf_error, page_count = _pdf(dict(identity), dict(assessment), stages, generated_at)
    if pdf_error or not pdf_base64:
        raise ValueError(f"premium PDF renderer failed: {pdf_error or 'empty PDF'}")
    pdf_bytes = base64.b64decode(pdf_base64)
    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("premium PDF renderer produced invalid bytes")

    result.update({
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": pdf_base64,
        "pdf_error": None,
        "pdf_available": True,
        "pdf_page_count": page_count,
        "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest(),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "status": "review_required",
        "assessment_state": "review_required",
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "delivery_status": "blocked_pending_human_approval",
        "human_review_required": True,
        "human_review_completed": False,
        "client_delivery_allowed": False,
        "premium_report_renderer": {
            "version": VERSION,
            "premium_multi_chapter_layout": True,
            "executive_decision_brief": True,
            "weighted_scorecard": True,
            "evidence_health_summary": True,
            "executive_risk_register": True,
            "architecture_and_delivery_chapters": True,
            "roadmap_and_resourcing_chapters": True,
            "full_evidence_appendix": True,
            "canonical_findings_only": True,
            "canonical_scanner_truth_only": True,
            "page_count": page_count,
        },
    })
    return result


__all__ = ["VERSION", "rebuild_premium_client_artifacts"]
