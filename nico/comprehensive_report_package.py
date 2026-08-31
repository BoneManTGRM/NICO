from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any, Callable, Iterable

VERSION = "nico.comprehensive_report_package.v2.1"

_STAGE_TITLES = {
    "authorization_and_scope": "Authorization and Scope",
    "immutable_repository_snapshot": "Immutable Repository Snapshot",
    "repository_and_delivery_evidence": "Repository and Delivery Evidence",
    "dependency_security_static_analysis": "Dependency, Security, and Static Analysis",
    "ci_cd_architecture_complexity_velocity": "CI/CD, Architecture, Complexity, and Velocity",
    "evidence_reconciliation_and_scoring": "Evidence Reconciliation and Scoring",
    "decision_report_generation": "Core Decision Report",
    "deep_scanner_triage": "Deep Scanner Triage",
    "functional_qa": "Functional QA",
    "platform_parity": "Platform Parity",
    "deployment_and_infrastructure": "Deployment and Infrastructure",
    "architecture_and_data_flow": "Architecture and Data Flow",
    "developer_delivery_process": "Developer Delivery Process",
    "stakeholder_and_business_alignment": "Stakeholder and Business Alignment",
    "requirements_traceability": "Requirements Traceability",
    "historical_trends_and_change_failure": "Historical Trends and Change Failure",
    "six_month_roadmap": "Six-Month Roadmap",
    "staffing_sequencing_and_cost": "Staffing, Sequencing, and Cost",
    "risk_reduction_and_executive_briefing": "Risk Reduction and Executive Briefing",
    "final_comprehensive_report_generation": "Final Comprehensive Report",
    "cross_format_truth_verification": "Cross-Format Truth Verification",
    "human_review_request": "Human Review Request",
    "client_acceptance_pending": "Client Acceptance Pending",
}

_CHAPTERS = (
    (
        "Evidence Foundation",
        {
            "authorization_and_scope",
            "immutable_repository_snapshot",
            "repository_and_delivery_evidence",
            "dependency_security_static_analysis",
            "ci_cd_architecture_complexity_velocity",
            "evidence_reconciliation_and_scoring",
            "decision_report_generation",
        },
    ),
    (
        "Deep Technical Diligence",
        {
            "deep_scanner_triage",
            "functional_qa",
            "platform_parity",
            "deployment_and_infrastructure",
            "architecture_and_data_flow",
            "developer_delivery_process",
        },
    ),
    (
        "Business and Delivery Context",
        {
            "stakeholder_and_business_alignment",
            "requirements_traceability",
            "historical_trends_and_change_failure",
        },
    ),
    (
        "Roadmap, Resourcing, and Decision",
        {
            "six_month_roadmap",
            "staffing_sequencing_and_cost",
            "risk_reduction_and_executive_briefing",
        },
    ),
    (
        "Integrity and Acceptance",
        {
            "cross_format_truth_verification",
            "human_review_request",
            "client_acceptance_pending",
        },
    ),
)

_IGNORED_DETAIL_KEYS = {
    "stage_id",
    "status",
    "message",
    "summary",
    "run_id",
    "repository",
    "commit_sha",
    "evidence_ledger_id",
    "customer_id",
    "project_id",
    "human_review_required",
    "client_delivery_allowed",
    "report_package",
    "reports",
    "assessment",
    "pdf_base64",
    "markdown",
    "html",
    "scanner_results",
    "stage_results",
    "provider_access_evidence",
}


def _now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any, limit: int = 1200) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(key): _safe(item)
            for key, item in value.items()
            if str(key) not in {"pdf_base64", "html", "markdown"}
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe(item) for item in value]
    return _text(value)


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(
        _safe(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _flatten(
    value: Any,
    *,
    prefix: str = "",
    depth: int = 0,
    maximum: int = 120,
) -> list[str]:
    if depth > 5:
        return []
    output: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in _IGNORED_DETAIL_KEYS:
                continue
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list, tuple)):
                output.extend(_flatten(item, prefix=label, depth=depth + 1, maximum=maximum))
            elif item not in (None, ""):
                output.append(f"{label}: {_text(item, 700)}")
            if len(output) >= maximum:
                break
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            label = f"{prefix}[{index}]" if prefix else str(index + 1)
            if isinstance(item, (dict, list, tuple)):
                output.extend(_flatten(item, prefix=label, depth=depth + 1, maximum=maximum))
            elif item not in (None, ""):
                output.append(f"{label}: {_text(item, 700)}")
            if len(output) >= maximum:
                break
    elif value not in (None, ""):
        output.append(f"{prefix}: {_text(value, 700)}" if prefix else _text(value, 700))
    return output[:maximum]


def _dedupe(values: Iterable[str], limit: int = 120) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _text(value, 900)
        key = normalized.casefold()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
        if len(output) >= limit:
            break
    return output


def _flatten_client_literals(
    value: Any,
    *,
    prefix: str = "",
    depth: int = 0,
    maximum: int = 120,
) -> list[str]:
    """Flatten client-evidence structure without rewriting scalar literals."""

    from nico.comprehensive_engagement_metadata_v1 import _literal

    if depth > 5:
        return []
    output: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key) in _IGNORED_DETAIL_KEYS:
                continue
            label = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(item, (dict, list, tuple)):
                output.extend(
                    _flatten_client_literals(
                        item,
                        prefix=label,
                        depth=depth + 1,
                        maximum=maximum,
                    )
                )
            elif item not in (None, ""):
                literal = _literal(item, 6000)
                output.append(f"{label}: {literal}")
            if len(output) >= maximum:
                break
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            label = f"{prefix}[{index}]" if prefix else str(index + 1)
            if isinstance(item, (dict, list, tuple)):
                output.extend(
                    _flatten_client_literals(
                        item,
                        prefix=label,
                        depth=depth + 1,
                        maximum=maximum,
                    )
                )
            elif item not in (None, ""):
                literal = _literal(item, 6000)
                output.append(f"{label}: {literal}" if prefix else literal)
            if len(output) >= maximum:
                break
    elif value not in (None, ""):
        literal = _literal(value, 6000)
        output.append(f"{prefix}: {literal}" if prefix else literal)
    return output[:maximum]


def _dedupe_client_literals(
    values: Iterable[str], limit: int = 120
) -> list[str]:
    """Bound and deduplicate exact client-evidence strings without normalization."""

    from nico.comprehensive_engagement_metadata_v1 import _literal

    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        literal = _literal(value, 6000)
        key = literal.casefold()
        if not literal or key in seen:
            continue
        seen.add(key)
        output.append(literal)
        if len(output) >= limit:
            break
    return output


def _stage_summary(stage_id: str, result: dict[str, Any]) -> dict[str, Any]:
    client_literal_stage = (
        stage_id == "client_evidence_summary"
        or stage_id.startswith("client_human_evidence_")
    )
    flatten = _flatten_client_literals if client_literal_stage else _flatten
    dedupe = _dedupe_client_literals if client_literal_stage else _dedupe
    evidence_lines = flatten(result.get("evidence"), maximum=80)
    provider_access_lines = (
        _dedupe(result.get("provider_access_evidence") or [], 80)
        if stage_id == "repository_and_delivery_evidence"
        else []
    )
    structured_details = flatten(
        {
            key: value
            for key, value in result.items()
            if key not in _IGNORED_DETAIL_KEYS and key not in {"evidence", "findings", "unavailable", "unavailable_data_notes"}
        },
        maximum=80,
    )
    findings = _dedupe(result.get("findings") or [], 50)
    unavailable = dedupe(
        result.get("unavailable_data_notes") or result.get("unavailable") or [],
        50,
    )
    return {
        "stage_id": stage_id,
        "title": _STAGE_TITLES.get(stage_id, stage_id.replace("_", " ").title()),
        "status": _text(result.get("status") or "unknown", 40).lower(),
        "summary": _text(
            result.get("summary") or result.get("message") or "Stage evidence was recorded.",
            1600,
        ),
        "evidence": dedupe([*provider_access_lines, *evidence_lines, *structured_details], 140),
        "findings": findings,
        "unavailable": unavailable,
    }


def _assessment(stage_results: dict[str, dict[str, Any]]) -> dict[str, Any]:
    scoring = stage_results.get("evidence_reconciliation_and_scoring") or {}
    assessment = scoring.get("assessment")
    if isinstance(assessment, dict):
        return deepcopy(assessment)
    return {
        "status": "not_scored",
        "executive_summary": "A canonical technical score was not available. The report retains stage evidence and requires human review.",
        "maturity_signal": {"level": "Pending", "score": None},
        "sections": [],
        "unavailable_data_notes": [
            "Canonical scoring evidence was unavailable at report-generation time."
        ],
        "human_review_required": True,
        "client_ready": False,
    }


def _decision_summary(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
) -> str:
    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    level = _text(maturity.get("level") or "Pending", 80)
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "not scored"
    limited = sum(bool(item["unavailable"]) for item in stages)
    blocked = [
        item["title"]
        for item in stages
        if item["status"] in {"blocked", "failed", "unavailable", "timed_out"}
    ]
    boundary = (
        f"{len(blocked)} stage(s) remain blocked or unavailable: {', '.join(blocked[:4])}."
        if blocked
        else "Every automated stage represented in this package completed without a terminal execution failure."
    )
    return (
        f"NICO completed a native Comprehensive Technical Assessment for {_text(identity.get('repository'))} "
        f"at immutable commit {_text(identity.get('commit_sha'))}. The evidence-bound maturity signal is "
        f"{level} ({score_text}). {limited} stage(s) disclose unavailable or limited evidence. {boundary} "
        "The package is a review-gated draft: automated evidence and recommendations are not client approval or delivery authorization."
    )


def _constraints(
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    limit: int = 20,
) -> list[str]:
    values: list[str] = []
    for item in assessment.get("sections") or []:
        if not isinstance(item, dict):
            continue
        label = _text(item.get("label") or item.get("id"), 140)
        values.extend(f"{label}: {_text(value, 700)}" for value in item.get("findings") or [])
        values.extend(
            f"{label} — unavailable: {_text(value, 700)}"
            for value in item.get("unavailable") or []
        )
    for stage in stages:
        values.extend(f"{stage['title']}: {value}" for value in stage["findings"])
        values.extend(
            f"{stage['title']} — unavailable: {value}"
            for value in stage["unavailable"]
        )
    values.extend(
        f"Assessment-wide: {_text(value, 700)}"
        for value in assessment.get("unavailable_data_notes") or []
    )
    return _dedupe(values, limit)


def _chapter_stages(
    stages: list[dict[str, Any]],
    stage_ids: set[str],
) -> list[dict[str, Any]]:
    return [stage for stage in stages if stage["stage_id"] in stage_ids]


def _markdown(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    generated_at: str,
    *,
    localize_presentation: Callable[[str], str] | None = None,
) -> str:
    def localized(value: str) -> str:
        return localize_presentation(value) if localize_presentation else value

    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else localized("NOT SCORED")
    constraints = _constraints(assessment, stages)
    from nico.comprehensive_engagement_metadata_v1 import (
        _literal,
        markdown_literal_markup,
    )

    display_lines = []
    for label, key in (
        ("Client display name", "customer_name"),
        ("Project display name", "project_name"),
        ("Primary technical contact", "primary_technical_contact"),
        ("Access method", "access_method"),
        ("Authorized scope", "authorized_scope"),
    ):
        value = _literal(
            identity.get(key),
            {
                "customer_name": 180,
                "project_name": 180,
                "primary_technical_contact": 600,
                "access_method": 1200,
                "authorized_scope": 4000,
            }[key],
        )
        if value:
            display_lines.append(
                f"{localized(label)}: {markdown_literal_markup(value, 4000)}"
            )
    lines = [
        f"# {localized('NICO Comprehensive Technical Assessment')} — {_text(identity.get('repository'))}",
        "",
        f"{localized('Generated')}: {generated_at}",
        f"{localized('Service ID')}: comprehensive",
        f"{localized('Run ID')}: {_text(identity.get('run_id'))}",
        f"{localized('Immutable commit SHA')}: {_text(identity.get('commit_sha'))}",
        f"{localized('Evidence ledger ID')}: {_text(identity.get('evidence_ledger_id'))}",
        f"{localized('Customer scope')}: {_text(identity.get('customer_id'))}",
        f"{localized('Project scope')}: {_text(identity.get('project_id'))}",
        *display_lines,
        "",
        f"## {localized('Executive Decision Brief')}",
        localized(_decision_summary(identity, assessment, stages)),
        "",
        f"## {localized('Decision Boundary')}",
        localized("Human review is required. Client delivery is blocked. Missing evidence is disclosed and is never converted into a passing claim."),
        "",
        f"## {localized('Canonical Maturity Signal')}",
        f"- {localized('Level')}: {localized(_text(maturity.get('level') or 'Pending'))}",
        f"- {localized('Presented score')}: {score_text}",
        f"- {localized('Evidence readiness')}: {localized(_text(maturity.get('evidence_readiness_score') or 'Pending'))}",
        "",
        f"## {localized('Technical Scorecard')}",
    ]
    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    if sections:
        for item in sections:
            if not isinstance(item, dict):
                continue
            section_score = item.get("presented_score", item.get("score"))
            score_label = (
                f"{int(section_score)}/100"
                if isinstance(section_score, (int, float))
                else localized("NOT SCORED")
            )
            status = _text(item.get("presented_status") or item.get("status") or "unknown").upper()
            lines.append(
                f"- **{_text(item.get('label') or item.get('id'))}** — {localized(status)} — {score_label}"
            )
    else:
        lines.append(f"- {localized('Canonical scorecard unavailable; see the evidence limitations below.')}")

    lines += ["", f"## {localized('Priority Constraints and Risks')}"]
    lines.extend(f"- {localized(item)}" for item in constraints)
    if not constraints:
        lines.append(f"- {localized('No retained material constraint was available beyond the human-review boundary.')}")

    for chapter, stage_ids in _CHAPTERS:
        selected = _chapter_stages(stages, stage_ids)
        if not selected:
            continue
        lines += ["", f"## {localized(chapter)}"]
        for stage in selected:
            stage_id = str(stage.get("stage_id") or "")
            client_literal_stage = (
                stage_id == "client_evidence_summary"
                or stage_id.startswith("client_human_evidence_")
            )
            lines += [
                "",
                f"### {stage['title']} — {localized(stage['status'].upper())}",
                stage["summary"],
                "",
                f"{localized('Evidence')}:",
            ]
            lines.extend(
                (
                    f"- {markdown_literal_markup(item, 6000)}"
                    if client_literal_stage
                    else f"- {item}"
                    for item in stage["evidence"]
                ),
            )
            if not stage["evidence"]:
                lines.append(f"- {localized('No structured evidence line was retained for this stage.')}")
            if stage["findings"]:
                lines += ["", f"{localized('Findings')}:"] + [f"- {item}" for item in stage["findings"]]
            if stage["unavailable"]:
                lines += ["", f"{localized('Unavailable or limited evidence')}:"] + [
                    (
                        f"- {markdown_literal_markup(item, 6000)}"
                        if client_literal_stage
                        else f"- {item}"
                    )
                    for item in stage["unavailable"]
                ]

    unmatched = [
        stage
        for stage in stages
        if not any(stage["stage_id"] in stage_ids for _, stage_ids in _CHAPTERS)
    ]
    if unmatched:
        lines += ["", f"## {localized('Additional Recorded Stages')}"]
        for stage in unmatched:
            stage_id = str(stage.get("stage_id") or "")
            client_literal_stage = (
                stage_id == "client_evidence_summary"
                or stage_id.startswith("client_human_evidence_")
            )
            lines += [
                "",
                f"### {stage['title']} — {localized(stage['status'].upper())}",
                stage["summary"],
            ]
            lines.extend(
                (
                    f"- {markdown_literal_markup(item, 6000)}"
                    if client_literal_stage
                    else f"- {item}"
                )
                for item in stage["evidence"]
            )

    unavailable = _dedupe(assessment.get("unavailable_data_notes") or [], 50)
    lines += [
        "",
        f"## {localized('Assessment-Wide Limitations')}",
        *(
            [f"- {item}" for item in unavailable]
            or [f"- {localized('No assessment-wide limitation was recorded beyond stage-level disclosures.')}"]
        ),
        "",
        f"## {localized('Human Review Checklist')}",
        f"- [ ] {localized('Verify repository, run, commit, ledger, customer, and project identities.')}",
        f"- [ ] {localized('Review every failed, timed-out, unavailable, and triage-required analyzer result.')}",
        f"- [ ] {localized('Confirm the scorecard matches the evidence and all report formats.')}",
        f"- [ ] {localized('Validate business context, requirements, roadmap, staffing, and cost assumptions.')}",
        f"- [ ] {localized('Approve or reject the exact immutable report package before any client delivery.')}",
        "",
        f"## {localized('Delivery Status')}",
        f"**{localized('DRAFT — HUMAN REVIEW REQUIRED — CLIENT DELIVERY NOT AUTHORIZED')}**",
        "",
    ]
    return "\n".join(lines).strip() + "\n"


def _semantic_html(markdown: str, title: str) -> str:
    blocks: list[str] = []
    list_items: list[str] = []
    lifecycle_boundary: str | None = None
    literal_span = re.compile(
        r'<span data-nico-client-literal="true">.*?</span>'
    )

    def inline(value: str) -> str:
        """Escape Markdown text while admitting only our inert client-literal span."""

        output: list[str] = []
        cursor = 0
        for match in literal_span.finditer(value):
            output.append(html.escape(value[cursor : match.start()]))
            candidate = match.group(0)
            inner = candidate.removeprefix(
                '<span data-nico-client-literal="true">'
            ).removesuffix("</span>")
            if "<" in inner.replace("<br/>", "") or ">" in inner.replace(
                "<br/>", ""
            ):
                output.append(html.escape(candidate))
            else:
                output.append(candidate)
            cursor = match.end()
        output.append(html.escape(value[cursor:]))
        return "".join(output)

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            blocks.append("<ul>" + "".join(list_items) + "</ul>")
            list_items = []

    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            flush_list()
            continue
        if line.startswith("### "):
            flush_list()
            blocks.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            flush_list()
            blocks.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            flush_list()
            blocks.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("- [ ] "):
            list_items.append(f"<li class=\"check\">☐ {inline(line[6:])}</li>")
        elif line.startswith("- "):
            list_items.append(f"<li>{inline(line[2:])}</li>")
        elif line.startswith("**") and line.endswith("**"):
            flush_list()
            lifecycle_boundary = line.strip("*")
            blocks.append(
                f"<p class=\"warning\">{html.escape(lifecycle_boundary)}</p>"
            )
        else:
            flush_list()
            blocks.append(f"<p>{inline(line)}</p>")
    flush_list()
    body = "".join(blocks)
    badge = (
        f'<span class="badge">{html.escape(lifecycle_boundary)}</span>'
        if lifecycle_boundary is not None
        else ""
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(title)}</title>
<style>
:root{{color-scheme:dark}}body{{margin:0;background:#071124;color:#dbeafe;font:16px/1.6 Inter,system-ui,sans-serif}}main{{max-width:1080px;margin:0 auto;padding:42px 22px 80px}}header{{padding:30px;border:1px solid #274060;border-radius:24px;background:#0d1a31;margin-bottom:24px}}header h1{{margin:0;color:#fff;font-size:clamp(28px,5vw,48px)}}.badge{{display:inline-block;margin-top:14px;padding:8px 12px;border:1px solid #f59e0b;border-radius:999px;color:#fde68a;background:#4a2406;font-weight:800}}article{{padding:26px;border:1px solid #274060;border-radius:24px;background:#0b172c}}h1{{color:#fff;line-height:1.08}}h2{{margin-top:34px;padding-top:24px;border-top:1px solid #274060;color:#7dd3fc}}h3{{margin-top:26px;color:#e0f2fe}}p{{color:#cbd5e1}}ul{{padding-left:24px}}li{{margin:7px 0;color:#cbd5e1}}p,li{{white-space:break-spaces;overflow-wrap:anywhere}}.check{{list-style:none;margin-left:-22px}}.warning{{padding:16px;border:1px solid #f59e0b;border-radius:14px;background:#4a2406;color:#fde68a;font-weight:800;letter-spacing:.02em}}
</style></head><body><main><header><h1>{html.escape(title)}</h1>{badge}</header><article>{body}</article></main></body></html>"""


def _pdf(
    identity: dict[str, Any],
    assessment: dict[str, Any],
    stages: list[dict[str, Any]],
    generated_at: str,
    *,
    localize_presentation: Callable[[str], str] | None = None,
) -> tuple[str | None, str | None, int]:
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_CENTER
        from reportlab.lib.pagesizes import letter
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.lib.units import inch
        from reportlab.platypus import (
            KeepTogether,
            PageBreak,
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except Exception as exc:  # pragma: no cover
        return None, f"PDF export unavailable: {type(exc).__name__}", 0

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "Title",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=28,
        leading=32,
        textColor=colors.HexColor("#0f172a"),
        alignment=TA_CENTER,
        spaceAfter=16,
    )
    subtitle = ParagraphStyle(
        "Subtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=12,
        leading=17,
        textColor=colors.HexColor("#334155"),
        alignment=TA_CENTER,
        spaceAfter=12,
    )
    h1 = ParagraphStyle(
        "H1",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=21,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=12,
        keepWithNext=1,
    )
    h2 = ParagraphStyle(
        "H2",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#075985"),
        spaceBefore=8,
        spaceAfter=6,
        keepWithNext=1,
    )
    h3 = ParagraphStyle(
        "H3",
        parent=styles["Heading3"],
        fontName="Helvetica-Bold",
        fontSize=11,
        leading=14,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=4,
        keepWithNext=1,
    )
    body = ParagraphStyle(
        "Body",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=9.2,
        leading=13.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    small = ParagraphStyle(
        "Small",
        parent=body,
        fontSize=7.8,
        leading=10.5,
        textColor=colors.HexColor("#475569"),
        allowWidows=0,
    )
    warning = ParagraphStyle(
        "Warning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=0.8,
        borderPadding=10,
        spaceBefore=12,
        spaceAfter=12,
    )

    def p(
        value: Any,
        style: ParagraphStyle = body,
        *,
        client_literal: bool = False,
    ) -> Paragraph:
        if client_literal:
            from nico.comprehensive_engagement_metadata_v1 import reportlab_literal_markup

            rendered = reportlab_literal_markup(value, 6000)
        else:
            rendered = html.escape(_text(value, 6000))
        return Paragraph(rendered, style)

    def localized(value: str) -> str:
        return localize_presentation(value) if localize_presentation else value

    def bullets(
        values: Iterable[str],
        *,
        limit: int = 60,
        client_literal: bool = False,
    ) -> list[Paragraph]:
        if client_literal:
            items = [str(item) for item in values if str(item or "").strip()][:limit]
        else:
            items = [_text(item, 1000) for item in values if _text(item)][:limit]
        return [
            p(f"• {item}", small, client_literal=client_literal) for item in items
        ] or [p(localized("No structured item was retained."), small)]

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            0.55 * inch,
            0.38 * inch,
            f"NICO Comprehensive · {_text(identity.get('run_id'), 60)} · {localized('DRAFT')}",
        )
        canvas.drawRightString(7.95 * inch, 0.38 * inch, f"{localized('Page')} {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.55 * inch,
        leftMargin=0.55 * inch,
        topMargin=0.58 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Comprehensive Technical Assessment",
        author="NICO",
        subject=f"Comprehensive assessment {_text(identity.get('run_id'))}",
        invariant=1,
    )

    story: list[Any] = [
        Spacer(1, 1.1 * inch),
        p(
            "NICO",
            ParagraphStyle(
                "Brand",
                parent=title_style,
                fontSize=18,
                textColor=colors.HexColor("#0284c7"),
            ),
        ),
        p(localized("Comprehensive Technical Assessment"), title_style),
        p(_text(identity.get("repository")), subtitle),
        Spacer(1, 0.3 * inch),
        p(f"{localized('Immutable commit')}: {_text(identity.get('commit_sha'))}", subtitle),
        p(f"{localized('Run ID')}: {_text(identity.get('run_id'))}", subtitle),
        p(f"{localized('Generated')}: {generated_at}", subtitle),
        Spacer(1, 0.45 * inch),
        p(localized("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"), warning),
        PageBreak(),
        p(localized("Executive Decision Brief"), h1),
        p(localized(_decision_summary(identity, assessment, stages)), body),
        p(localized("Decision Boundary"), h2),
        p(
            localized(
                "The report is an evidence-bound draft. NICO has not approved findings, accepted business assumptions, or authorized delivery. Missing evidence remains visible and constrains conclusions."
            ),
            body,
        ),
    ]

    maturity = assessment.get("maturity_signal") if isinstance(assessment.get("maturity_signal"), dict) else {}
    score = maturity.get("presented_score", maturity.get("score"))
    score_text = f"{int(score)}/100" if isinstance(score, (int, float)) else "NOT SCORED"
    from nico.comprehensive_engagement_metadata_v1 import _literal

    display_metadata_supplied = any(
        _literal(identity.get(field), limit)
        for field, limit in (
            ("customer_name", 180),
            ("project_name", 180),
            ("primary_technical_contact", 600),
        )
    )
    not_supplied = localized("Not supplied")
    if display_metadata_supplied:
        customer_display = _literal(identity.get("customer_name"), 180) or not_supplied
        project_display = _literal(identity.get("project_name"), 180) or not_supplied
    else:
        # Legacy/internal packages historically display immutable scope IDs here. Keep
        # that behavior only when no display metadata was supplied at all so existing
        # canonical identity/golden contracts remain stable. Commercial engagements
        # with any display metadata use the explicit human-facing values above.
        customer_display = _text(identity.get("customer_id"), 80)
        project_display = _text(identity.get("project_id"), 80)
    identity_rows = [
        [localized("Service"), "Comprehensive", localized("Run ID"), _text(identity.get("run_id"), 80)],
        [localized("Repository"), _text(identity.get("repository"), 80), localized("Commit"), _text(identity.get("commit_sha"), 80)],
        [localized("Customer"), customer_display, localized("Project"), project_display],
        [localized("Maturity"), localized(_text(maturity.get("level") or "Pending", 80)), localized("Score"), localized(score_text)],
    ]
    identity_table = Table(
        [
            [
                p(
                    cell,
                    small,
                    client_literal=(
                        display_metadata_supplied
                        and row_index == 2
                        and column_index in {1, 3}
                    ),
                )
                for column_index, cell in enumerate(row)
            ]
            for row_index, row in enumerate(identity_rows)
        ],
        colWidths=[0.85 * inch, 2.35 * inch, 0.8 * inch, 3.5 * inch],
    )
    identity_table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#e0f2fe")),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story += [Spacer(1, 0.15 * inch), identity_table]

    constraints = _constraints(assessment, stages)
    decision_break = Spacer(1, 0.2 * inch) if display_metadata_supplied else PageBreak()
    story += [
        decision_break,
        p(localized("Priority Constraints and Decision Risks"), h1),
        *bullets((localized(item) for item in constraints), limit=24),
    ]

    sections = assessment.get("sections") if isinstance(assessment.get("sections"), list) else []
    story += [PageBreak(), p(localized("Canonical Technical Scorecard"), h1)]
    score_rows = [[localized("Control"), localized("Status"), localized("Score"), localized("Summary")]]
    for item in sections:
        if not isinstance(item, dict):
            continue
        section_score = item.get("presented_score", item.get("score"))
        section_label = (
            f"{int(section_score)}/100"
            if isinstance(section_score, (int, float))
            else "NOT SCORED"
        )
        score_rows.append(
            [
                _text(item.get("label") or item.get("id"), 90),
                localized(_text(item.get("presented_status") or item.get("status") or "unknown", 30).upper()),
                localized(section_label),
                _text(item.get("summary"), 240),
            ]
        )
    if len(score_rows) == 1:
        score_rows.append(
            [localized("Canonical scoring"), localized("PENDING"), localized("NOT SCORED"), localized("No canonical section scorecard was available.")]
        )
    score_table = Table(
        score_rows,
        colWidths=[1.5 * inch, 0.75 * inch, 0.75 * inch, 4.45 * inch],
        repeatRows=1,
    )
    score_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("FONTSIZE", (0, 0), (-1, -1), 7.2),
                ("LEADING", (0, 0), (-1, -1), 9.5),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    story.append(score_table)

    for item in sections:
        if not isinstance(item, dict):
            continue
        section_score = item.get("presented_score", item.get("score"))
        section_label = (
            f"{int(section_score)}/100"
            if isinstance(section_score, (int, float))
            else "NOT SCORED"
        )
        story += [
            PageBreak(),
            p(_text(item.get("label") or item.get("id")), h1),
            p(
                f"{localized(_text(item.get('presented_status') or item.get('status') or 'unknown').upper())} · {localized(section_label)}",
                warning if section_score is None else h2,
            ),
            p(item.get("summary") or localized("No section summary was retained."), body),
            p(localized("Evidence"), h2),
            *bullets(item.get("evidence") or [], limit=30),
        ]
        if item.get("findings"):
            story += [p(localized("Findings"), h2), *bullets(item.get("findings") or [], limit=24)]
        if item.get("unavailable"):
            story += [p(localized("Unavailable or Limited Evidence"), h2), *bullets(item.get("unavailable") or [], limit=24)]

    for chapter, stage_ids in _CHAPTERS:
        selected = _chapter_stages(stages, stage_ids)
        if not selected:
            continue
        story += [PageBreak(), p(localized(chapter), h1)]
        for stage in selected:
            stage_id = str(stage.get("stage_id") or "")
            client_literal_stage = (
                stage_id == "client_evidence_summary"
                or stage_id.startswith("client_human_evidence_")
            )
            block: list[Any] = [
                p(f"{stage['title']} · {localized(stage['status'].upper())}", h2),
                p(stage["summary"], body),
            ]
            preview = stage["evidence"][:10]
            block.extend(
                bullets(preview, limit=10, client_literal=client_literal_stage)
            )
            if stage["findings"]:
                block.extend([p(localized("Findings"), h3), *bullets(stage["findings"], limit=12)])
            if stage["unavailable"]:
                block.extend([p(localized("Evidence Limitations"), h3), *bullets(stage["unavailable"], limit=12)])
            story.append(KeepTogether(block))
            story.append(Spacer(1, 0.12 * inch))

    story += [PageBreak(), p(localized("Evidence Appendix"), h1), p(localized("The appendix preserves full bounded stage evidence for the immutable run. It is intentionally separate from the decision-oriented body."), body)]
    for stage in stages:
        stage_id = str(stage.get("stage_id") or "")
        client_literal_stage = (
            stage_id == "client_evidence_summary"
            or stage_id.startswith("client_human_evidence_")
        )
        story += [
            PageBreak(),
            p(stage["title"], h1),
            p(f"{localized('Stage ID')}: {stage['stage_id']} · {localized('Status')}: {localized(stage['status'].upper())}", small),
            p(stage["summary"], body),
            p(localized("Retained Evidence"), h2),
            *bullets(
                stage["evidence"],
                limit=100,
                client_literal=client_literal_stage,
            ),
        ]
        if stage["findings"]:
            story += [p(localized("Findings"), h2), *bullets(stage["findings"], limit=50)]
        if stage["unavailable"]:
            story += [p(localized("Unavailable or Limited Evidence"), h2), *bullets(stage["unavailable"], limit=50)]

    story += [
        PageBreak(),
        p(localized("Human Review and Acceptance Gate"), h1),
        p(localized("The automated assessment is complete only as a draft. The following decisions remain human responsibilities:"), body),
        *bullets(
            [
                localized("Verify the exact repository, run, commit, evidence ledger, customer, and project identities."),
                localized("Triage every failed, timed-out, unavailable, and review-required scanner result."),
                localized("Validate business context, requirements, roadmap, staffing, sequencing, and cost assumptions."),
                localized("Confirm Markdown, HTML, JSON, and PDF show the same status and score truth."),
                localized("Approve or reject the immutable report package before creating any delivery access."),
            ]
        ),
        p(localized("DRAFT · HUMAN REVIEW REQUIRED · CLIENT DELIVERY NOT AUTHORIZED"), warning),
    ]

    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    pdf_bytes = buffer.getvalue()
    page_count = 0
    try:
        from pypdf import PdfReader

        page_count = len(PdfReader(io.BytesIO(pdf_bytes)).pages)
    except Exception:
        page_count = 0
    return base64.b64encode(pdf_bytes).decode("ascii"), None, page_count


def build_comprehensive_report_package(
    *,
    identity: dict[str, Any],
    stage_results: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    required_identity = {
        field: _text(identity.get(field), 180)
        for field in (
            "run_id",
            "repository",
            "commit_sha",
            "evidence_ledger_id",
            "customer_id",
            "project_id",
        )
    }
    missing = [field for field, value in required_identity.items() if not value]
    if missing:
        return {
            "status": "blocked",
            "reason": "missing_report_identity:" + ",".join(missing),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    from nico.comprehensive_engagement_metadata_v1 import _literal

    report_identity = dict(required_identity)
    for field, limit in (
        ("customer_name", 180),
        ("project_name", 180),
        ("primary_technical_contact", 600),
        ("access_method", 1200),
        ("authorized_scope", 4000),
    ):
        value = _literal(identity.get(field), limit)
        if value:
            report_identity[field] = value

    generated_at = _now()
    ordered = [
        _stage_summary(stage_id, result)
        for stage_id, result in stage_results.items()
        if isinstance(result, dict) and stage_id != "final_comprehensive_report_generation"
    ]
    assessment = _assessment(stage_results)
    assessment["human_review_required"] = True
    assessment["client_ready"] = False
    assessment["client_delivery_allowed"] = False
    assessment["service_id"] = "comprehensive"
    assessment["repository"] = report_identity["repository"]
    assessment["commit_sha"] = report_identity["commit_sha"]
    assessment["run_id"] = report_identity["run_id"]
    assessment["executive_summary"] = _decision_summary(report_identity, assessment, ordered)

    markdown = _markdown(report_identity, assessment, ordered, generated_at)
    title = f"NICO Comprehensive Technical Assessment — {report_identity['repository']}"
    rendered_html = _semantic_html(markdown, title)
    pdf_base64, pdf_error, page_count = _pdf(report_identity, assessment, ordered, generated_at)
    pdf_bytes = base64.b64decode(pdf_base64) if pdf_base64 else b""
    report_id = f"comprehensive_report_{_canonical_hash({'identity': report_identity, 'stages': ordered})[:20]}"
    safe_repo = re.sub(r"[^A-Za-z0-9_.-]+", "-", report_identity["repository"]).strip("-") or "repository"
    filename = (
        f"nico-comprehensive-assessment-{safe_repo}-{report_identity['run_id']}-DRAFT.pdf"
    )
    canonical = {
        "service_id": "comprehensive",
        "identity": report_identity,
        "assessment": assessment,
        "stage_summaries": ordered,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    truth_sha = _canonical_hash(canonical)
    technical_controls = [
        item
        for item in assessment.get("sections") or []
        if isinstance(item, dict)
    ]
    quality = {
        "version": VERSION,
        "semantic_html": "<article>" in rendered_html and "<pre>" not in rendered_html,
        "comprehensive_module_count": len(ordered),
        "technical_control_count": len(technical_controls),
        "decision_oriented_body": True,
        "full_evidence_appendix": True,
        "not_scored_format_valid": "NOT SCORED/100" not in markdown,
        "mid_brand_leakage_absent": "NICO MID TECHNICAL" not in markdown.upper(),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    complete = bool(
        pdf_base64
        and not pdf_error
        and pdf_bytes.startswith(b"%PDF")
        and quality["semantic_html"]
        and quality["not_scored_format_valid"]
        and quality["mid_brand_leakage_absent"]
    )
    return {
        "status": "complete" if complete else "blocked",
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "report_id": report_id,
        "generated_at": generated_at,
        "assessment": assessment,
        "stage_summaries": ordered,
        "canonical_truth_sha256": truth_sha,
        "report_quality_contract": quality,
        "report_package": {
            "service_id": "comprehensive",
            "report_id": report_id,
            "markdown": markdown,
            "html": rendered_html,
            "json": canonical,
            "pdf_base64": pdf_base64,
            "pdf_error": pdf_error,
            "pdf_filename": filename,
            "pdf_sha256": hashlib.sha256(pdf_bytes).hexdigest() if pdf_bytes else "",
            "pdf_page_count": page_count,
            "canonical_truth_sha256": truth_sha,
            "report_quality_contract": quality,
            "human_review_required": True,
            "client_delivery_allowed": False,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "build_comprehensive_report_package"]
