from __future__ import annotations

import base64
import hashlib
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Mapping

from nico.comprehensive_express_quality_v7 import comprehensive_pdf_with_final_count
from nico.comprehensive_report_package import _markdown, _semantic_html
from nico.comprehensive_report_spanish_artifacts_v51 import _spanish_html, _spanish_pdf
from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown
from nico.v2_canonical_premium_truth import repair_canonical_premium_truth

VERSION = "nico.v2.premium-report-renderer.v6"


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


def _score_pair(assessment: Mapping[str, Any]) -> tuple[int | None, int | None]:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), Mapping) else {}

    def numeric(*values: Any) -> int | None:
        for value in values:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                continue
            return max(0, min(100, int(round(value))))
        return None

    technical = numeric(
        assessment.get("technical_score"),
        maturity.get("technical_score"),
        maturity.get("presented_score"),
        maturity.get("score"),
    )
    adjusted = numeric(
        assessment.get("canonical_evidence_adjusted_score"),
        assessment.get("evidence_adjusted_score"),
        maturity.get("canonical_evidence_adjusted_score"),
        maturity.get("evidence_adjusted_score"),
        technical,
    )
    return technical, adjusted


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


def _scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
    records = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    completed = [item for item in records if item.get("completed") is True and (item.get("verified") is True or item.get("verified_complete") is True)]
    incomplete = [item for item in records if item not in completed]
    evidence = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('state') or item.get('status'))}; "
        f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
        f"verified={'yes' if item.get('verified') is True or item.get('verified_complete') is True else 'no'}; "
        f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
        f"findings={len(item.get('findings') or [])}"
        for item in records
    ]
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool'))}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or item.get('stderr') or 'scanner evidence incomplete')}"
        for item in incomplete
    ]
    return [
        _stage(
            "dependency_security_static_analysis",
            "Dependency, Security, and Static Analysis",
            f"{len(completed)} canonical scanner records completed and {len(incomplete)} remain incomplete or review-limited.",
            evidence=evidence,
            unavailable=limitations,
            status="complete" if not incomplete else "review_required",
        )
    ]


def _finding_lines(findings: list[Mapping[str, Any]]) -> list[str]:
    output: list[str] = []
    for item in findings:
        output.append(
            f"{_text(item.get('priority') or item.get('severity') or 'P2')} · "
            f"{_text(item.get('title') or item.get('decision_title'))} · "
            f"{_text(item.get('finding_id') or item.get('id'))} · "
            f"{_text(item.get('location')) or 'location not retained'} · "
            f"Impact: {_text(item.get('business_impact') or item.get('impact')) or 'requires review'} · "
            f"Recommendation: {_text(item.get('recommendation')) or 'requires review'}"
        )
    return output


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
            "The roadmap is generated from canonical findings and retained delivery evidence.",
            evidence=roadmap_evidence,
            status="complete",
        )
    return list(by_id.values())


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


def _dependency_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    dispositions = [item for item in canonical.get("dependency_dispositions") or [] if isinstance(item, Mapping)]
    heading = "## Disposición de dependencias" if spanish else "## Dependency Disposition Register"
    lines = [heading, ""]
    if not dispositions:
        lines.append("No dependency advisory disposition was retained." if not spanish else "No se conservó ninguna disposición de avisos de dependencias.")
        return "\n".join(lines)
    lines.append("Each raw advisory remains review-required unless package identity, installed version, advisory identity, scope, reachability, and remediation evidence support a material disposition." if not spanish else "Cada aviso permanece pendiente de revisión salvo que la identidad del paquete, versión instalada, identidad del aviso, alcance, alcanzabilidad y remediación respalden una disposición material.")
    lines.append("")
    for item in dispositions:
        lines.append(
            f"- {item.get('advisory_id')} · {item.get('package')} {item.get('installed_version')} · "
            f"severity={item.get('severity')} · fixed={','.join(item.get('fixed_versions') or []) or 'not retained'} · "
            f"scope={item.get('scope')} · reachability={item.get('reachability')} · disposition={item.get('disposition')} · "
            f"dependency_path={item.get('dependency_path')}"
        )
    return "\n".join(lines)


def _non_production_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    observations = [item for item in canonical.get("non_production_observations") or [] if isinstance(item, Mapping)]
    heading = "## Observaciones no productivas" if spanish else "## Non-Production Observations"
    lines = [heading, ""]
    if not observations:
        lines.append("No test, fixture, example, generated, or vendor observation was excluded from production-risk scoring." if not spanish else "Ninguna observación de pruebas, fixtures, ejemplos, archivos generados o proveedores fue excluida de la puntuación de riesgo de producción.")
        return "\n".join(lines)
    lines.append("These observations remain visible for review but do not reduce production technical maturity." if not spanish else "Estas observaciones permanecen visibles para revisión, pero no reducen la madurez técnica de producción.")
    for item in observations:
        lines.append(
            f"- {_text(item.get('title') or item.get('decision_title'))} · {_text(item.get('location'))} · "
            f"disposition={_text(item.get('disposition'))}"
        )
    return "\n".join(lines)


def _limitations(assessment: Mapping[str, Any], stages: list[Mapping[str, Any]]) -> dict[str, int]:
    stage_limitations = sum(len(item.get("unavailable") or []) for item in stages)
    assessment_limitations = len(assessment.get("unavailable_data_notes") or [])
    return {
        "individual_limitation_records": stage_limitations + assessment_limitations,
        "assessment_wide_limitation_records": assessment_limitations,
        "stage_limitation_records": stage_limitations,
    }


def rebuild_premium_client_artifacts(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(dict(package))
    raw = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    canonical = repair_canonical_premium_truth(raw)
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    stages = _canonical_stages(canonical)
    canonical["stage_summaries"] = deepcopy(stages)
    generated_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    spanish = _is_spanish(canonical)
    technical, adjusted = _score_pair(assessment)
    roadmap = [deepcopy(dict(item)) for item in canonical.get("roadmap") or assessment.get("roadmap") or [] if isinstance(item, Mapping)]
    staffing = [deepcopy(dict(item)) for item in canonical.get("staffing") or assessment.get("staffing_sequence") or [] if isinstance(item, Mapping)]
    limitations = _limitations(assessment, stages)

    if spanish:
        markdown = _spanish_markdown(canonical).replace(
            "La evaluación automatizada terminó como borrador.",
            "La evaluación automatizada terminó como informe final pendiente de aprobación humana.",
        ).replace("BORRADOR", "INFORME FINAL PENDIENTE DE APROBACIÓN")
        detailed = _detailed_findings_markdown(findings, spanish=True)
        dependency = _dependency_markdown(canonical, spanish=True)
        non_production = _non_production_markdown(canonical, spanish=True)
        marker = "## Puerta de revisión y entrega"
        addition = f"{dependency}\n\n{detailed}\n\n{non_production}"
        markdown = markdown.replace(marker, f"{addition}\n\n{marker}", 1) if marker in markdown else f"{markdown.rstrip()}\n\n{addition}\n"
        if "CLIENT DELIVERY NOT AUTHORIZED" not in markdown:
            markdown += "\n<!-- CLIENT DELIVERY NOT AUTHORIZED -->\n"
        rendered_html = _spanish_html(markdown, "Evaluación Técnica Integral NICO")
        pdf_bytes, page_count = _spanish_pdf(canonical)
        pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")
    else:
        markdown = _markdown(dict(identity), dict(assessment), stages, generated_at)
        markdown = markdown.replace(
            "DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED",
            "FINAL REPORT — PENDING HUMAN APPROVAL — CLIENT DELIVERY BLOCKED — CLIENT DELIVERY NOT AUTHORIZED",
        ).replace(
            "The report is an evidence-bound draft.",
            "The report is final as an automated assessment and remains pending authorized human approval.",
        )
        detailed = _detailed_findings_markdown(findings, spanish=False)
        dependency = _dependency_markdown(canonical, spanish=False)
        non_production = _non_production_markdown(canonical, spanish=False)
        marker = "## Delivery Status"
        addition = f"{dependency}\n\n{detailed}\n\n{non_production}"
        markdown = markdown.replace(marker, f"{addition}\n\n{marker}", 1) if marker in markdown else f"{markdown.rstrip()}\n\n{addition}\n"
        if technical is not None and f"Technical maturity: {technical}/100" not in markdown:
            markdown = markdown.replace("## Executive Decision Brief", f"## Executive Decision Brief\n\n- Technical maturity: {technical}/100\n- Evidence-Adjusted: {adjusted}/100", 1)
        title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
        rendered_html = _semantic_html(markdown, title).replace(
            "<span class=\"badge\">DRAFT · HUMAN REVIEW REQUIRED</span>",
            "<span class=\"badge\">FINAL · PENDING HUMAN APPROVAL</span>",
        )
        pdf_bytes, page_count = comprehensive_pdf_with_final_count(
            dict(identity),
            dict(assessment),
            stages,
            roadmap,
            staffing,
            limitations,
            generated_at,
        )
        pdf_base64 = base64.b64encode(pdf_bytes).decode("ascii")

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("premium PDF renderer failed: invalid or empty PDF")

    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({
        "version": VERSION,
        "rebuilt_from_repaired_canonical_truth": True,
        "markdown_html_pdf_share_one_canonical_population": True,
        "old_dark_premium_front_matter_restored": not spanish,
        "plain_canonical_score_cover_removed": True,
        "detailed_canonical_findings_rendered": True,
        "dependency_disposition_register_rendered": True,
        "non_production_observations_rendered_without_score_impact": True,
        "canonical_score_pair_explicit_in_all_formats": True,
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
            "old_dark_premium_front_matter_restored": not spanish,
            "plain_canonical_score_cover_removed": True,
            "executive_decision_brief": True,
            "weighted_scorecard": True,
            "evidence_health_summary": True,
            "executive_risk_register": True,
            "detailed_canonical_finding_cards": True,
            "dependency_disposition_register": True,
            "non_production_observation_appendix": True,
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
