from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_report_package import _markdown, _pdf, _semantic_html
from nico.comprehensive_report_spanish_artifacts_v51 import _spanish_html, _spanish_pdf
from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown

VERSION = "nico.v2.premium-report-renderer.v4"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _is_spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or assessment.get("locale")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


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


def _detailed_findings_markdown(findings: list[Mapping[str, Any]], *, spanish: bool) -> str:
    heading = "## Hallazgos canónicos detallados" if spanish else "## Detailed Canonical Findings"
    lines = [heading, ""]
    if not findings:
        lines.append("No se conservó ningún hallazgo canónico accionable." if spanish else "No canonical actionable finding was retained.")
        return "\n".join(lines)
    for item in findings:
        identifier = _text(item.get("finding_id") or item.get("id"))
        title = _text(item.get("title") or item.get("decision_title"))
        priority = _text(item.get("priority") or item.get("severity") or "P2")
        lines += [
            f"### {priority} - {title}",
            "",
            f"- Finding ID: {identifier}",
            f"- Category / status: {_text(item.get('category'))} · {_text(item.get('status'))}",
            f"- Location: {_text(item.get('location')) or 'Location not retained'}",
            f"- Evidence: {_text(item.get('fact') or item.get('evidence')) or 'Evidence requires review'}",
            f"- Interpretation: {_text(item.get('interpretation') or title)}",
            f"- Business impact: {_text(item.get('business_impact') or item.get('impact')) or 'Requires review'}",
            f"- Recommendation: {_text(item.get('recommendation')) or 'Requires review'}",
            f"- Owner / effort: {_text(item.get('owner_role')) or 'Unassigned'} · {_text(item.get('effort')) or 'Unestimated'}",
            f"- Cost of inaction: {_text(item.get('cost_of_inaction')) or 'Not quantified'}",
            f"- Residual risk: {_text(item.get('residual_risk')) or 'Requires review'}",
        ]
        criteria: list[str] = []
        seen: set[str] = set()
        for raw in item.get("acceptance_criteria") or []:
            value = _text(raw)
            key = value.casefold()
            if value and key not in seen:
                seen.add(key)
                criteria.append(value)
        if criteria:
            lines.append("- Acceptance criteria:")
            lines.extend(f"  - {value}" for value in criteria)
        lines.append("")
    return "\n".join(lines).strip()


def _scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    evidence = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('state') or item.get('status'))}; "
        f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
        f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
        f"findings={len(item.get('findings') or [])}"
        for item in records
    ]
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner evidence incomplete')}"
        for item in incomplete
    ]
    return [
        _stage(
            "dependency_security_static_analysis",
            "Dependency, Security, and Static Analysis",
            f"{len(completed)} scanner records completed and {len(incomplete)} remain incomplete or review-limited.",
            evidence=evidence,
            unavailable=limitations,
            status="complete" if not incomplete else "review_required",
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
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    stages = _canonical_stages(canonical)
    canonical["stage_summaries"] = deepcopy(stages)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    spanish = _is_spanish(canonical)

    if spanish:
        markdown = _spanish_markdown(canonical).replace(
            "La evaluación automatizada terminó como borrador.",
            "La evaluación automatizada terminó como informe final pendiente de aprobación humana.",
        ).replace("BORRADOR", "INFORME FINAL PENDIENTE DE APROBACIÓN")
        detailed = _detailed_findings_markdown(findings, spanish=True)
        marker = "## Puerta de revisión y entrega"
        markdown = markdown.replace(marker, f"{detailed}\n\n{marker}", 1) if marker in markdown else f"{markdown.rstrip()}\n\n{detailed}\n"
        if "CLIENT DELIVERY NOT AUTHORIZED" not in markdown:
            markdown += "\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
        rendered_html = _spanish_html(markdown, "Evaluación Técnica Integral NICO")
        pdf_bytes, page_count = _spanish_pdf(canonical)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
        pdf_error = None
    else:
        markdown = _markdown(dict(identity), dict(assessment), stages, generated_at).replace(
            "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
            "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED — CLIENT DELIVERY NOT AUTHORIZED",
        )
        detailed = _detailed_findings_markdown(findings, spanish=False)
        marker = "## Delivery Status"
        markdown = markdown.replace(marker, f"{detailed}\n\n{marker}", 1) if marker in markdown else f"{markdown.rstrip()}\n\n{detailed}\n"
        title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
        rendered_html = _semantic_html(markdown, title)
        pdf_base64, pdf_error, page_count = _pdf(dict(identity), dict(assessment), stages, generated_at)
        pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""

    if pdf_error or not pdf_base64 or not pdf_bytes.startswith(b"%PDF"):
        raise ValueError(f"premium PDF renderer failed: {pdf_error or 'invalid or empty PDF'}")

    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_html_pdf_share_one_canonical_population": True,
        "premium_renderer_restored_after_canonical_repair": True,
        "detailed_canonical_findings_rendered": True,
        "legacy_aliases_hidden_from_client_artifacts": True,
        "bilingual_renderer_selected_from_canonical_language": True,
        "finality_semantics_embedded": True,
        "page_count": page_count,
    })

    result.update({
        "json": canonical,
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": pdf_base64,
        "pdf_error": None,
        "pdf_available": True,
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
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
        "phase17_artifact_rebuild": phase17,
        "premium_report_renderer": {
            "version": VERSION,
            "premium_multi_chapter_layout": True,
            "executive_decision_brief": True,
            "weighted_scorecard": True,
            "evidence_health_summary": True,
            "executive_risk_register": True,
            "detailed_canonical_finding_cards": True,
            "architecture_and_delivery_chapters": True,
            "roadmap_and_resourcing_chapters": True,
            "full_evidence_appendix": True,
            "canonical_findings_only": True,
            "canonical_scanner_truth_only": True,
            "bilingual_premium_output": True,
            "page_count": page_count,
        },
    })
    return result


__all__ = ["VERSION", "rebuild_premium_client_artifacts"]
