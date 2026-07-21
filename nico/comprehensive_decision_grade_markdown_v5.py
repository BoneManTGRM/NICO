from __future__ import annotations

import base64
import csv
import hashlib
import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable

from nico import comprehensive_report_package as base_report
from nico.comprehensive_decision_grade_model_v5 import (
    APPENDIX_HEADING,
    REVIEW_HEADING,
    VERSION,
    _assurance,
    _bounded_int,
    _score_band,
    _text,
)
from nico.comprehensive_decision_grade_roadmap_v5 import build_roadmap

def _clean_limitation(value: Any) -> str:
    text = _text(value, 900)
    lowered = text.casefold()
    if "/tmp/" in text or "cannot fork" in lowered or "getaddrinfo() thread failed" in lowered:
        return "Snapshot-bound git transport could not allocate required process or network resources; NICO used the immutable exact-commit archive fallback, so git-history scanners were unavailable for this run."
    return text


def _clean_evidence(values: Iterable[Any], limit: int = 16) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _text(value, 900)
        if not text or text.endswith(":"):
            continue
        text = _clean_limitation(text)
        key = text.casefold()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
        if len(output) >= limit:
            break
    return output


def _decorate_assessment(assessment: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(assessment)
    sections = output.get("sections") if isinstance(output.get("sections"), list) else []
    for section in sections:
        if not isinstance(section, dict):
            continue
        score = section.get("score_value")
        if score is None:
            score = section.get("presented_score", section.get("score"))
        scored = isinstance(score, (int, float))
        status = section.get("presented_status") or section.get("status") or ("gray" if not scored else "yellow")
        section.update(_score_band(score))
        section.update(_assurance(status, scored=scored))
        section["score_value"] = int(score) if scored else None
        section["technical_score_display"] = f"{section['score_band_label']} · {int(score)}/100" if scored else "NOT SCORED"
        section["assurance_display"] = section["assurance_label"]
    maturity = output.get("maturity_signal") if isinstance(output.get("maturity_signal"), dict) else {}
    overall = maturity.get("presented_score", maturity.get("score"))
    maturity.update(_score_band(overall))
    output["maturity_signal"] = maturity
    output["sections"] = sections
    output.setdefault("findings_register", [])
    output.setdefault("limitation_metrics", {})
    output["decision_grade_schema"] = VERSION
    output["human_review_required"] = True
    output["client_ready"] = False
    output["client_delivery_allowed"] = False
    return output


def _stage_summaries(stage_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    stages: list[dict[str, Any]] = []
    for stage_id, result in stage_results.items():
        if not isinstance(result, dict) or stage_id == "final_comprehensive_report_generation":
            continue
        stage = base_report._stage_summary(stage_id, result)
        stage["evidence"] = _clean_evidence(stage.get("evidence") or [], 18)
        stage["findings"] = _clean_evidence(stage.get("findings") or [], 12)
        stage["unavailable"] = _clean_evidence(stage.get("unavailable") or [], 12)
        if stage_id == "decision_report_generation":
            stage["evidence"] = [
                line.replace("pdf_page_count:", "core_report_page_count_at_stage:", 1)
                if line.startswith("pdf_page_count:")
                else line
                for line in stage["evidence"]
            ]
        stages.append(stage)
    return stages


def _limitation_metrics(assessment: dict[str, Any], stages: list[dict[str, Any]]) -> dict[str, int]:
    stage_records = sum(len(stage.get("unavailable") or []) for stage in stages)
    stages_with = sum(bool(stage.get("unavailable")) for stage in stages)
    assessment_records = len(_clean_evidence(assessment.get("unavailable_data_notes") or [], 200))
    section_score_affecting = sum(
        len(section.get("findings") or []) + len(section.get("unavailable") or [])
        for section in assessment.get("sections") or []
        if isinstance(section, dict)
    )
    individual = len(
        {
            _clean_limitation(item).casefold()
            for stage in stages
            for item in stage.get("unavailable") or []
            if _clean_limitation(item)
        }
        | {
            _clean_limitation(item).casefold()
            for item in assessment.get("unavailable_data_notes") or []
            if _clean_limitation(item)
        }
    )
    return {
        "stages_with_limitations": stages_with,
        "individual_limitation_records": individual,
        "stage_limitation_records": stage_records,
        "assessment_wide_records": assessment_records,
        "score_affecting_records": section_score_affecting,
        "informational_records": max(0, individual - min(individual, section_score_affecting)),
    }


def _roadmap_from_stages(stage_results: dict[str, dict[str, Any]], assessment: dict[str, Any]) -> list[dict[str, Any]]:
    stage = stage_results.get("six_month_roadmap") if isinstance(stage_results.get("six_month_roadmap"), dict) else {}
    roadmap = stage.get("roadmap") if isinstance(stage.get("roadmap"), list) else []
    return roadmap or build_roadmap(assessment)


def _staffing_from_stages(stage_results: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    stage = stage_results.get("staffing_sequencing_and_cost") if isinstance(stage_results.get("staffing_sequencing_and_cost"), dict) else {}
    return stage.get("staffing_plan") if isinstance(stage.get("staffing_plan"), list) else []


def _escape_md(value: Any) -> str:
    return _text(value, 1000).replace("|", "\\|")


def _markdown_table(headers: list[str], rows: list[list[Any]]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    for row in rows:
        lines.append("| " + " | ".join(_escape_md(value) for value in row) + " |")
    return lines


def _decision_summary(identity: dict[str, Any], assessment: dict[str, Any], limitations: dict[str, int]) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "not scored"
    band = maturity.get("score_band_label") or _score_band(score)["score_band_label"]
    material = _bounded_int((assessment.get("limitation_metrics") or {}).get("material_findings"))
    return (
        f"NICO completed a Comprehensive Technical Assessment for {_text(identity.get('repository'))} at immutable commit "
        f"{_text(identity.get('commit_sha'))}. Technical maturity is {band.title()} ({score_text}). "
        f"Evidence assurance remains independently review-gated: {limitations['stages_with_limitations']} stage(s) contain "
        f"{limitations['individual_limitation_records']} distinct limitation record(s), and {material} material scanner finding(s) were retained. "
        "Automated evidence is not client approval; an authorized human must disposition findings and approve the exact package."
    )


def _build_markdown(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    roadmap: list[dict[str, Any]],
    staffing: list[dict[str, Any]],
    limitations: dict[str, int],
    generated_at: str,
) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    findings = assessment.get("findings_register") if isinstance(assessment.get("findings_register"), list) else []
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    lines = [
        f"# NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}",
        "",
        f"Generated: {generated_at}",
        f"Run ID: {_text(identity.get('run_id'))}",
        f"Immutable commit SHA: {_text(identity.get('commit_sha'))}",
        f"Evidence ledger ID: {_text(identity.get('evidence_ledger_id'))}",
        f"Customer scope: {_text(identity.get('customer_id'))}",
        f"Project scope: {_text(identity.get('project_id'))}",
        "",
        "## Executive Decision Brief",
        _decision_summary(identity, assessment, limitations),
        "",
        "## Decision Boundary",
        "Technical score, evidence assurance, and client-delivery authorization are independent. Human review is mandatory. Client delivery is blocked until the exact immutable package is approved.",
        "",
        "## Assessment Dashboard",
        *_markdown_table(
            ["Dimension", "Result", "Meaning"],
            [
                ["Technical maturity", f"{maturity.get('score_band_label') or _score_band(score)['score_band_label']} · {score_text}", "Score-derived engineering health"],
                ["Evidence readiness", maturity.get("evidence_readiness_score") or "Pending", "Completeness and reliability of required evidence"],
                ["Human review", "REQUIRED", "Findings, assumptions, and delivery decision remain human responsibilities"],
                ["Client delivery", "NOT AUTHORIZED", "No report may be delivered until approved"],
            ],
        ),
        "",
        "## Limitation Accounting",
        *_markdown_table(
            ["Metric", "Count", "Definition"],
            [
                ["Stages with limitations", limitations["stages_with_limitations"], "Stages containing at least one unavailable or limited-evidence record"],
                ["Distinct limitation records", limitations["individual_limitation_records"], "Deduplicated limitation statements across stages and assessment-wide notes"],
                ["Score-affecting records", limitations["score_affecting_records"], "Section findings or evidence gaps that constrain score or assurance"],
                ["Informational records", limitations["informational_records"], "Disclosures that do not independently change a technical score"],
            ],
        ),
        "",
        "## Canonical Technical Scorecard",
        *_markdown_table(
            ["Control", "Technical score", "Band", "Evidence assurance", "Summary"],
            [
                [
                    section.get("label") or section.get("id"),
                    f"{section.get('score_value')}/100" if isinstance(section.get("score_value"), int) else "NOT SCORED",
                    section.get("score_band_label") or "NOT SCORED",
                    section.get("assurance_label") or "HUMAN REVIEW PENDING",
                    section.get("summary") or "",
                ]
                for section in sections
                if isinstance(section, dict)
            ],
        ),
        "",
        "## Executive Risk Register",
        *_markdown_table(
            ["Priority", "Finding", "Business impact", "Confidence", "Recommended action"],
            [
                [item.get("priority"), item.get("title"), item.get("impact"), item.get("confidence"), item.get("recommendation")]
                for item in findings[:12]
                if isinstance(item, dict)
            ]
            or [["—", "No structured technical finding was retained.", "Human review still required.", "—", "Verify evidence completeness."]],
        ),
        "",
        "## Detailed Findings Register",
    ]
    for item in findings:
        if not isinstance(item, dict):
            continue
        lines.extend(
            [
                "",
                f"### {item.get('priority')} · {item.get('title')}",
                f"- Category: {item.get('category')}",
                f"- Location: {item.get('location')}",
                f"- Evidence: {item.get('evidence')}",
                f"- Impact: {item.get('impact')}",
                f"- Confidence: {item.get('confidence')}",
                f"- Owner role: {item.get('owner_role')}",
                f"- Estimated effort: {item.get('effort')}",
                f"- Recommendation: {item.get('recommendation')}",
                f"- Acceptance criteria: {item.get('acceptance_criteria')}",
            ]
        )
    lines.extend(["", "## Architecture and Data Flow", "Repository → Immutable Snapshot → Repository/Scanner/Complexity Evidence → Reconciled Scoring → Decision Report → Human Review → Authorized Delivery", ""])
    architecture = next((item for item in sections if isinstance(item, dict) and item.get("id") == "architecture_debt"), {})
    lines.extend(["### Complexity Profile", *[f"- {item}" for item in architecture.get("evidence") or []]])
    if architecture.get("findings"):
        lines.extend(["", "### Named Hotspots", *[f"- {item}" for item in architecture.get("findings") or []]])

    lines.extend(["", "## Six-Month Execution Roadmap"])
    for window in roadmap:
        if not isinstance(window, dict):
            continue
        lines.extend(["", f"### {window.get('window')} — {window.get('objective')}"])
        for package in window.get("work_packages") or []:
            if not isinstance(package, dict):
                continue
            lines.extend(
                [
                    f"- **{package.get('title')}**",
                    f"  - Owner: {package.get('owner_role')}",
                    f"  - Effort: {package.get('effort')}",
                    f"  - Objective: {package.get('objective')}",
                    f"  - Dependencies: {', '.join(package.get('dependencies') or []) or 'None retained'}",
                    f"  - Acceptance: {'; '.join(package.get('acceptance_criteria') or []) or 'Requires human approval'}",
                    f"  - Expected impact: {package.get('expected_impact')}",
                ]
            )

    lines.extend(["", "## Staffing and Sequencing"])
    for item in staffing:
        if isinstance(item, dict):
            lines.append(
                f"- **Sequence {item.get('sequence')}: {item.get('role')}** — {item.get('focus')} Capacity: {item.get('estimated_load') or 'Requires client planning.'}"
            )
    if not staffing:
        lines.append("- Staffing details require stakeholder approval.")

    lines.extend(
        [
            "",
            APPENDIX_HEADING,
            "The client-facing report contains bounded, decision-relevant stage evidence. The complete machine-readable evidence ledger remains in the canonical JSON and CSV artifacts.",
        ]
    )
    for index, stage in enumerate(stages, start=1):
        lines.extend(
            [
                "",
                f"### A{index}. {stage['title']} — {stage['status'].upper()}",
                f"- Stage ID: `{stage['stage_id']}`",
                f"- Summary: {stage['summary']}",
                f"- Evidence records retained: {len(stage.get('evidence') or [])}",
                f"- Finding records retained: {len(stage.get('findings') or [])}",
                f"- Limitation records retained: {len(stage.get('unavailable') or [])}",
            ]
        )
        lines.extend(f"- Evidence: {item}" for item in (stage.get("evidence") or [])[:8])
        lines.extend(f"- Finding: {item}" for item in (stage.get("findings") or [])[:6])
        lines.extend(f"- Limitation: {item}" for item in (stage.get("unavailable") or [])[:6])

    lines.extend(
        [
            "",
            REVIEW_HEADING,
            "- [ ] Verify repository, run, commit, evidence-ledger, customer, and project identities.",
            "- [ ] Triage every material, review-required, failed, timed-out, and unavailable analyzer result.",
            "- [ ] Confirm technical score, score band, evidence assurance, and delivery status match across JSON, CSV, Markdown, HTML, and PDF.",
            "- [ ] Validate business context, requirements, roadmap, staffing, sequencing, effort, and cost assumptions.",
            "- [ ] Approve or reject the exact immutable report package before any delivery access is created.",
            "",
            "## Delivery Status",
            "**DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED**",
            "",
        ]
    )
    return "\n".join(lines).strip() + "\n"



__all__ = ["_clean_limitation", "_clean_evidence", "_decorate_assessment", "_stage_summaries", "_limitation_metrics", "_roadmap_from_stages", "_staffing_from_stages", "_build_markdown", "_decision_summary"]
