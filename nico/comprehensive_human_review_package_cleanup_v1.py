from __future__ import annotations

import base64
import html
import io
import json
import re
from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

from nico.comprehensive_operational_evidence_v1 import (
    deployment_population_from_context,
    format_deployment_classification,
)

VERSION = "nico.comprehensive-human-review-package-cleanup.v1"
_MARKER = "__nico_comprehensive_human_review_package_cleanup_v1__"

_PLACEHOLDER_IDENTITIES = {
    "",
    "default_customer",
    "default_project",
    "unknown_customer",
    "unknown_project",
}
_PUNCTUATION_ONLY = re.compile(r"^[\s.\-–—_:;|/\\]+$")
_INTERNAL_DOTTED_LINE = re.compile(
    r"^[a-z][a-z0-9_]*(?:\.[a-z0-9_]+){2,}(?::|\s*$)",
    re.IGNORECASE,
)
_COMPLEXITY_FINDING = re.compile(r"\breduce complexity in\b", re.IGNORECASE)
_AMBIGUOUS_SCANNER_LANGUAGE = (
    "remain incomplete or review-limited",
    "retained finding count=",
)

_TOC_TITLES = (
    "Comprehensive Technical Assessment",
    "Executive Decision Brief",
    "Priority Constraints and Decision Risks",
    "Canonical Technical Scorecard",
    "Code Audit",
    "Dependency / Library Ecosystem",
    "Secrets Exposure Review",
    "Static Analysis",
    "CI/CD Analysis",
    "Architecture & Technical Debt",
    "Velocity / Complexity",
    "Repository and Delivery Evidence",
    "Evidence Reconciliation and Scoring",
    "Executive Risk Register and Decision Briefing",
    "Authorization and Scope",
    "Architecture and Data Flow",
    "Developer Delivery Process",
    "Dependency, Security, and Static Analysis",
    "CI/CD, Architecture, Complexity, and Velocity",
    "Review-Required Candidate Register",
    "CI/CD Operational Readiness and Historical Health",
    "Functional QA",
    "Platform Parity",
    "Historical Trends and Change Failure",
    "Requirements Traceability",
    "Stakeholder and Business Alignment",
    "Risk Reduction and Executive Briefing",
    "Six-Month Roadmap",
    "Staffing, Sequencing, and Cost",
    "Compact Finding and Remediation Register",
    "Complete Exact-Source Index",
    "Client Evidence Summary",
    "Human Review and Acceptance Gate",
    "Client Artifact Manifest",
    "Human Review and Exact-Artifact Approval Record",
)


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    try:
        return max(0, int(str(value).strip()))
    except (TypeError, ValueError):
        return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value in (None, ""):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _meaningful(value: Any) -> bool:
    normalized = _text(value)
    return bool(normalized and not _PUNCTUATION_ONLY.fullmatch(normalized))


def _client_identity(value: Any) -> str:
    normalized = _text(value, 300)
    if normalized.casefold() in _PLACEHOLDER_IDENTITIES or not _meaningful(normalized):
        return "Not supplied"
    return normalized


def sanitize_client_identity(canonical: Mapping[str, Any]) -> dict[str, Any]:
    """Project client-safe identity values without inventing a customer or project."""

    result = deepcopy(dict(canonical))
    identity = (
        deepcopy(dict(result.get("identity") or {}))
        if isinstance(result.get("identity"), Mapping)
        else {}
    )
    customer = (
        identity.get("customer_name")
        or result.get("customer_name")
        or identity.get("customer_id")
        or result.get("customer_id")
    )
    project = (
        identity.get("project_name")
        or result.get("project_name")
        or identity.get("project_id")
        or result.get("project_id")
    )
    identity["customer_id"] = _client_identity(customer)
    identity["project_id"] = _client_identity(project)
    result["identity"] = identity
    result["customer_id"] = identity["customer_id"]
    result["project_id"] = identity["project_id"]

    contract = deepcopy(dict(result.get("v2_pipeline_contract") or {}))
    contract.update(
        {
            "human_review_package_cleanup_version": VERSION,
            "client_identity_placeholders_sanitized": True,
            "missing_client_identity_renders_not_supplied": True,
            "numeric_scores_unchanged_by_cleanup": True,
            "candidate_dispositions_unchanged_by_cleanup": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    result["v2_pipeline_contract"] = contract
    return result


def _candidate_summary(canonical: Mapping[str, Any]) -> Mapping[str, Any]:
    direct = canonical.get("review_candidate_summary")
    if isinstance(direct, Mapping):
        return direct
    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    nested = assessment.get("review_candidate_summary")
    return nested if isinstance(nested, Mapping) else {}


def _sum_categories(summary: Mapping[str, Any], key: str) -> int:
    by_category = (
        summary.get("by_category")
        if isinstance(summary.get("by_category"), Mapping)
        else {}
    )
    return sum(
        _integer(counts.get(key)) or 0
        for counts in by_category.values()
        if isinstance(counts, Mapping)
    )


def _candidate_totals(canonical: Mapping[str, Any]) -> dict[str, int]:
    summary = _candidate_summary(canonical)
    raw = _integer(summary.get("raw_total"))
    review = _integer(summary.get("review_required_total"))
    material = _integer(
        summary.get("verified_material_total")
        if summary.get("verified_material_total") is not None
        else summary.get("confirmed_material_total")
    )
    excluded = _integer(summary.get("excluded_test_only_total"))
    approved = _integer(summary.get("approved_or_nonblocking_total"))
    return {
        "raw": raw if raw is not None else _sum_categories(summary, "raw"),
        "review_required": (
            review if review is not None else _sum_categories(summary, "review_required")
        ),
        "confirmed_material": (
            material if material is not None else _sum_categories(summary, "material")
        ),
        "excluded_test_only": (
            excluded if excluded is not None else _sum_categories(summary, "excluded_test_only")
        ),
        "approved_or_nonblocking": (
            approved
            if approved is not None
            else _sum_categories(summary, "approved_or_nonblocking")
        ),
    }


def _scanner_material_count(record: Mapping[str, Any]) -> int:
    findings = record.get("findings")
    if isinstance(findings, list):
        return len(findings)
    for key in (
        "confirmed_material_finding_count",
        "material_finding_count",
        "finding_count",
        "findings_count",
    ):
        value = _integer(record.get(key))
        if value is not None:
            return value
    summary = (
        record.get("finding_summary")
        if isinstance(record.get("finding_summary"), Mapping)
        else {}
    )
    for key in ("confirmed_material", "material", "verified_material"):
        value = _integer(summary.get(key))
        if value is not None:
            return value
    return 0


def build_scanner_execution_stage(
    canonical: Mapping[str, Any],
    renderer: Any,
) -> dict[str, Any]:
    records = [
        item
        for item in canonical.get("scanner_execution_records") or []
        if isinstance(item, Mapping)
    ]
    completed = [item for item in records if item.get("completed") is True]
    incomplete = [item for item in records if item.get("completed") is not True]
    totals = _candidate_totals(canonical)
    evidence: list[str] = [
        f"Raw candidate count: {totals['raw']}.",
        f"Confirmed material finding count: {totals['confirmed_material']}.",
        f"Review-required candidate count: {totals['review_required']}.",
        f"Excluded test-only count: {totals['excluded_test_only']}.",
        f"Approved or nonblocking count: {totals['approved_or_nonblocking']}.",
    ]
    for item in records:
        name = _text(item.get("scanner_name") or item.get("tool") or "unnamed scanner")
        state = _text(item.get("state") or item.get("status") or "unknown")
        evidence.append(
            f"{name}: {state}; "
            f"exact commit={'yes' if item.get('exact_commit_match') else 'no'}; "
            f"artifact={'retained' if item.get('artifact_hash') else 'missing'}; "
            f"confirmed material finding count={_scanner_material_count(item)}; "
            f"raw finding payload embedded={'yes' if item.get('findings') else 'no'}."
        )
    limitations = [
        f"{_text(item.get('scanner_name') or item.get('tool') or 'unnamed scanner')}: "
        f"{_text(item.get('failure_reason') or item.get('reason') or 'scanner execution evidence incomplete')}"
        for item in incomplete
    ]
    return renderer._stage(
        "dependency_security_static_analysis",
        "Dependency, Security, and Static Analysis",
        (
            f"{len(completed)} of {len(records)} applicable scanner executions completed. "
            f"{'No scanner execution remains incomplete. ' if not incomplete else f'{len(incomplete)} scanner execution(s) remain incomplete. '}"
            f"{totals['review_required']} resulting candidates remain pending human disposition. "
            "Scanner completion does not equal candidate approval."
        ),
        evidence=evidence,
        unavailable=limitations,
        status="complete" if not incomplete else "review_required",
    )


def _percent(numerator: int, denominator: int) -> str:
    if denominator <= 0:
        return "Not available"
    value = (100.0 * numerator) / denominator
    return f"{value:.1f}".rstrip("0").rstrip(".") + "%"


def _supported_job_success(context: Mapping[str, Any]) -> tuple[int | None, int | None, str]:
    observed = _integer(context.get("jobs_observed"))
    for key in (
        "successful_jobs",
        "jobs_succeeded",
        "job_success_count",
        "successful_job_count",
    ):
        success = _integer(context.get(key))
        if success is not None and observed is not None:
            return success, observed, "retained job counts"
    rate = _number(context.get("job_success_rate"))
    if observed is not None and rate is not None:
        product = rate * observed
        rounded = round(product)
        if abs(product - rounded) < 1e-9:
            return int(rounded), observed, "retained rate and denominator"
    return None, observed, "successful count not separately retained"


def build_ci_operational_stage(
    canonical: Mapping[str, Any],
    renderer: Any,
) -> dict[str, Any] | None:
    context = (
        canonical.get("ci_operational_context")
        if isinstance(canonical.get("ci_operational_context"), Mapping)
        else {}
    )
    if not context:
        return None

    evidence = [
        "CI/CD configuration maturity remains the immutable scored control.",
        "Workflow runs, workflow jobs, and deployments are separate operational populations and have no technical-score effect.",
    ]

    outcome_classes = (
        context.get("workflow_outcome_classes")
        if isinstance(context.get("workflow_outcome_classes"), Mapping)
        else {}
    )
    successful_runs = _integer(context.get("successful_runs"))
    if successful_runs is None:
        successful_runs = _integer(outcome_classes.get("success"))
    workflow_total = sum(
        _integer(value) or 0 for value in outcome_classes.values()
    )
    if workflow_total <= 0:
        observed = _integer(context.get("workflow_runs_observed"))
        workflow_total = observed or 0
    if successful_runs is not None and workflow_total:
        classes = "; ".join(
            f"{_text(key)}={_integer(value) or 0}"
            for key, value in outcome_classes.items()
        )
        suffix = f"; outcome classes: {classes}" if classes else ""
        evidence.append(
            f"Workflow runs: {successful_runs} successful of {workflow_total} observed "
            f"({_percent(successful_runs, workflow_total)}); unscored historical context{suffix}."
        )

    successful_jobs, jobs_observed, job_source = _supported_job_success(context)
    if jobs_observed is not None and successful_jobs is not None:
        evidence.append(
            f"Workflow jobs: {successful_jobs} successful of {jobs_observed} observed "
            f"({_percent(successful_jobs, jobs_observed)}); bounded observed job sample; "
            f"count basis={job_source}."
        )
    elif jobs_observed is not None:
        evidence.append(
            f"Workflow jobs: {jobs_observed} observed; successful count and success rate "
            "are not reported because a supported numerator was not retained."
        )

    population = deployment_population_from_context(context)
    deployments = population.get("deployments_observed")
    successful_deployments = population.get("successful_deployments")
    non_success_or_unresolved = population.get(
        "non_success_or_unresolved_deployments"
    )
    if deployments is not None:
        if successful_deployments is not None:
            evidence.append(
                f"Deployments: {successful_deployments} successful of {deployments} observed "
                f"({_percent(successful_deployments, deployments)})."
            )
        else:
            evidence.append(
                f"Deployments: {deployments} observed; successful count: Not available."
            )
        if non_success_or_unresolved is not None:
            evidence.append(
                "Non-success or unresolved deployment observations: "
                f"{non_success_or_unresolved}."
            )
        else:
            evidence.append(
                "Non-success or unresolved deployment observations: Not available."
            )
        evidence.append(
            "Outcome classification breakdown: "
            + format_deployment_classification(population)
            + "."
        )

    for key, label in (
        ("observation_scope", "Observation scope"),
        ("observation_window", "Observation window"),
        ("time_window", "Observation window"),
        ("evidence_source", "Evidence source"),
        ("evidence_id", "Evidence source"),
        ("required_check_health", "Required-check health"),
        ("assessed_commit_required_check_health", "Assessed-commit required-check health"),
        ("current_default_branch_required_check_health", "Current default-branch required-check health"),
    ):
        value = context.get(key)
        if _meaningful(value):
            line = f"{label}: {_text(value)}."
            if line not in evidence:
                evidence.append(line)

    return renderer._stage(
        "ci_cd_operational_readiness",
        "CI/CD Operational Readiness and Historical Health",
        (
            "Operational workflow and deployment evidence is disclosed separately from "
            "exact-commit workflow-configuration maturity."
        ),
        evidence=evidence,
        status="complete",
    )


def sanitize_rendered_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    item = deepcopy(dict(stage))
    stage_id = _text(item.get("stage_id")).casefold()

    evidence: list[str] = []
    seen: set[str] = set()
    for raw in item.get("evidence") or []:
        value = _text(raw)
        if not value or _INTERNAL_DOTTED_LINE.match(value):
            continue
        key = value.casefold()
        if key not in seen:
            seen.add(key)
            evidence.append(value)
    item["evidence"] = evidence

    findings: list[str] = []
    for raw in item.get("findings") or []:
        value = _text(raw)
        if not value:
            continue
        if stage_id == "dependency_security_static_analysis" and _COMPLEXITY_FINDING.search(value):
            continue
        findings.append(value)
    item["findings"] = findings
    return item


def _outline_title(text: str) -> str:
    lines = [_text(line, 180) for line in str(text or "").splitlines() if _text(line)]
    for title in _TOC_TITLES:
        if any(
            line == title
            or line.startswith(title + " ·")
            or line.startswith(title + " —")
            for line in lines[:32]
        ):
            return title
    joined = "\n".join(lines[:32])
    if "NICO · compact finding register" in joined or "Priority / ID" in joined or "Pri. Finding ID" in joined:
        return "Compact Finding and Remediation Register · continuation"
    return "Report page"


def _filename_markup(value: Any) -> str:
    raw = _text(value, 900)
    if not raw:
        return "Not available"
    chunks: list[str] = []
    remainder = raw
    while len(remainder) > 44:
        split_at = max(
            remainder.rfind("-", 0, 45),
            remainder.rfind("_", 0, 45),
            remainder.rfind(".", 0, 45),
        )
        if split_at < 16:
            split_at = 44
        else:
            split_at += 1
        chunks.append(remainder[:split_at])
        remainder = remainder[split_at:]
    chunks.append(remainder)
    return "<br/>".join(html.escape(chunk) for chunk in chunks if chunk)


def _digest_markup(value: Any) -> str:
    raw = _text(value, 900)
    if re.fullmatch(r"[0-9a-fA-F]{64}", raw):
        return html.escape(raw[:32]) + "<br/>" + html.escape(raw[32:])
    return _filename_markup(raw or "Bound in detached manifest after final rendering")


def render_manifest_approval_supplement(
    canonical: Mapping[str, Any],
    entries: list[dict[str, Any]],
) -> bytes:
    """Render the existing two-page approval supplement with legible identifiers."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest

    identity = manifest._canonical_identity(canonical)
    lifecycle = (
        canonical.get("lifecycle")
        if isinstance(canonical.get("lifecycle"), Mapping)
        else manifest._lifecycle()
    )
    approval = (
        canonical.get("approval")
        if isinstance(canonical.get("approval"), Mapping)
        else manifest._pending_approval_record()
    )
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "CleanupManifestTitle",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=9,
    )
    heading = ParagraphStyle(
        "CleanupManifestHeading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=11.5,
        leading=14,
        textColor=colors.HexColor("#075985"),
        spaceBefore=6,
        spaceAfter=4,
    )
    body = ParagraphStyle(
        "CleanupManifestBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.8,
        leading=10.1,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    small = ParagraphStyle(
        "CleanupManifestSmall",
        parent=body,
        fontSize=6.2,
        leading=7.7,
        textColor=colors.HexColor("#475569"),
        spaceAfter=1,
    )
    digest = ParagraphStyle(
        "CleanupManifestDigest",
        parent=small,
        fontName="Courier",
        fontSize=5.4,
        leading=6.6,
    )
    warning = ParagraphStyle(
        "CleanupManifestWarning",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=.7,
        borderPadding=7,
        spaceAfter=8,
    )

    def p(value: Any, style: ParagraphStyle = body, *, markup: bool = False) -> Paragraph:
        rendered = str(value or "") if markup else html.escape(_text(value, 1800))
        return Paragraph(rendered, style)

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .35 * inch, "NICO | exact-artifact review package | automated draft")
        canvas.drawRightString(7.95 * inch, .35 * inch, f"Integrity {doc.page}")
        canvas.restoreState()

    identity_rows = [
        ["Repository", identity.get("repository") or "Not available"],
        ["Exact commit", identity.get("commit_sha") or "Not available"],
        ["Run ID", identity.get("run_id") or "Not available"],
        ["Evidence ledger ID", identity.get("evidence_ledger_id") or "Not available"],
        ["Generated", identity.get("generation_timestamp") or "Not available"],
    ]
    identity_table = Table(
        [[p(left, small), p(right, small)] for left, right in identity_rows],
        colWidths=[1.35 * inch, 6.05 * inch],
    )
    identity_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    artifact_rows: list[list[Any]] = [[p("Artifact", small), p("Filename", small), p("SHA-256", small)]]
    for item in entries:
        artifact_rows.append(
            [
                p(item.get("artifact_type") or "", small),
                p(_filename_markup(item.get("filename")), small, markup=True),
                p(_digest_markup(item.get("sha256")), digest, markup=True),
            ]
        )
    artifact_table = Table(
        artifact_rows,
        colWidths=[1.25 * inch, 2.9 * inch, 3.25 * inch],
        repeatRows=1,
    )
    artifact_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0c4a6e")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )

    approval_rows = [
        ["Reviewer identity", approval.get("reviewer_identity") or "Pending"],
        ["Reviewer role", approval.get("reviewer_role") or "Pending"],
        ["Reviewer authorization", "Confirmed" if approval.get("reviewer_authorized") else "Pending"],
        ["Review timestamp", approval.get("review_timestamp") or "Pending"],
        ["Decision", approval.get("decision") or "Pending"],
        ["Residual-risk acceptance", approval.get("residual_risk_acceptance") or "Pending"],
        ["Approved PDF SHA-256", approval.get("approved_pdf_sha256") or "Recorded in detached approval receipt after decision"],
        ["Approved JSON SHA-256", approval.get("approved_json_sha256") or "Recorded in detached approval receipt after decision"],
        ["Evidence manifest SHA-256", approval.get("evidence_manifest_sha256") or "Recorded in detached approval receipt after decision"],
        ["Approval record ID", approval.get("approval_record_id") or "Pending"],
        ["Reviewer notes", approval.get("reviewer_notes") or "Pending"],
    ]
    approval_table = Table(
        [[p(left, small), p(right, small)] for left, right in approval_rows],
        colWidths=[1.65 * inch, 5.75 * inch],
    )
    approval_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("GRID", (0, 0), (-1, -1), .3, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )

    story: list[Any] = [
        p("Client Artifact Manifest", title),
        p("AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED", warning),
        identity_table,
        p("Retained structured artifacts", heading),
        artifact_table,
        Spacer(1, .08 * inch),
        p(
            "The final PDF and canonical JSON byte digests are recorded in the detached evidence manifest after rendering. A document cannot truthfully embed its own final byte digest without changing that digest. The detached manifest binds those final hashes to the same run, commit, and manifest ID.",
            body,
        ),
        PageBreak(),
        p("Human Review and Exact-Artifact Approval Record", title),
        p("REVIEW PACKAGE READY · HUMAN APPROVAL PENDING · CLIENT DELIVERY BLOCKED", warning),
        p("Lifecycle", heading),
        p(f"Review package ready: {'Yes' if lifecycle.get('review_package_ready') else 'No'}", body),
        p(f"Human approval: {_text(lifecycle.get('human_review_status') or 'pending').title()}", body),
        p(f"Client delivery: {_text(lifecycle.get('client_delivery_status') or 'blocked').title()}", body),
        p("Required approval record", heading),
        approval_table,
        p("Approval rule", heading),
        p(
            "Only an authorized human reviewer may approve the exact immutable PDF, canonical JSON, and detached evidence manifest digests. Any regeneration, score change, finding change, candidate disposition change, evidence change, or artifact replacement creates a new draft and invalidates prior approval.",
            body,
        ),
        p(
            "Automation cannot change this package to APPROVED FINAL or CLIENT DELIVERY AUTHORIZED.",
            warning,
        ),
    ]
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.55 * inch,
        rightMargin=.55 * inch,
        topMargin=.55 * inch,
        bottomMargin=.62 * inch,
        invariant=1,
        title="NICO Client Artifact Manifest and Approval Record",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _pdf_text(pdf: bytes) -> tuple[list[str], str]:
    reader = PdfReader(io.BytesIO(pdf))
    pages = [page.extract_text() or "" for page in reader.pages]
    return pages, "\n".join(pages)


def _substantive_lines(page_text: str) -> list[str]:
    output: list[str] = []
    for raw in page_text.splitlines():
        line = _text(raw, 1000)
        if not line:
            continue
        if line.startswith("NICO Comprehensive ·") or line.startswith("NICO |"):
            continue
        if line.startswith("Document page ") or re.fullmatch(r"(?:Page|Integrity sheet)\s+\d+(?:\s+of\s+\d+)?", line, re.IGNORECASE):
            continue
        if line in {
            "AUTOMATED DRAFT",
            "AUTOMATED DRAFT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED",
            "AUTOMATED DRAFT | HUMAN DECISION PENDING | CLIENT DELIVERY BLOCKED",
        }:
            continue
        output.append(line)
    return output


def assert_human_review_package_cleanup(
    canonical: Mapping[str, Any],
    markdown: str,
    rendered_html: str,
    pdf: bytes,
) -> None:
    pages, extracted = _pdf_text(pdf)
    combined = "\n".join((markdown, html.unescape(rendered_html), extracted))
    lowered = combined.casefold()
    identity = (
        canonical.get("identity")
        if isinstance(canonical.get("identity"), Mapping)
        else {}
    )

    for field in ("customer_id", "project_id"):
        value = _text(identity.get(field)).casefold()
        if value in _PLACEHOLDER_IDENTITIES:
            raise ValueError(f"canonical client identity retained placeholder field: {field}")
    for placeholder in _PLACEHOLDER_IDENTITIES - {""}:
        if placeholder in lowered:
            raise ValueError(f"client report exposed placeholder identity: {placeholder}")
    for phrase in _AMBIGUOUS_SCANNER_LANGUAGE:
        if phrase in lowered:
            raise ValueError(f"client report retained ambiguous scanner language: {phrase}")
    if re.search(r"non-success deployments:\s*[.\-–—]*\s*(?:\n|$)", combined, re.IGNORECASE):
        raise ValueError("client report retained a blank non-success deployment metric")

    for stage in canonical.get("stage_summaries") or []:
        if not isinstance(stage, Mapping):
            continue
        for line in stage.get("evidence") or []:
            value = _text(line)
            if not value or _PUNCTUATION_ONLY.fullmatch(value):
                raise ValueError("client stage evidence retained a blank or punctuation-only value")

    toc = next((page for page in pages if "Table of Contents" in page), "")
    if any(_INTERNAL_DOTTED_LINE.match(_text(line)) for line in toc.splitlines()):
        raise ValueError("table of contents exposed an internal dotted canonical key")
    if _COMPLEXITY_FINDING.search(toc):
        raise ValueError("table of contents used an individual finding as a section title")

    for index, page in enumerate(pages, start=1):
        lines = _substantive_lines(page)
        if len(lines) <= 2 and any(
            _INTERNAL_DOTTED_LINE.match(line) or _COMPLEXITY_FINDING.search(line)
            for line in lines
        ):
            raise ValueError(f"client PDF retained an accidental orphan detail page at page {index}")
        if re.search(r"\b[0-9a-f]{20,63}\s*\n\s*[0-9a-f]\b", page, re.IGNORECASE):
            raise ValueError(f"client artifact digest wrapped to an isolated character at page {index}")


def install_comprehensive_human_review_package_cleanup_v1() -> dict[str, Any]:
    """Install the final human-review package cleanup without changing scores or dispositions."""

    from nico import client_report_completion_v2 as completion
    from nico import comprehensive_artifact_manifest_approval_v1 as manifest
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import v2_premium_report_renderer as renderer

    current_prepare = completion.prepare_client_report_package
    if not getattr(current_prepare, _MARKER, False):
        @wraps(current_prepare)
        def prepare(package: Mapping[str, Any]) -> dict[str, Any]:
            result = deepcopy(dict(current_prepare(package)))
            canonical = (
                result.get("json")
                if isinstance(result.get("json"), Mapping)
                else {}
            )
            result["json"] = sanitize_client_identity(canonical)
            return result

        setattr(prepare, _MARKER, True)
        setattr(prepare, "_nico_previous", current_prepare)
        completion.prepare_client_report_package = prepare

    current_scanners = renderer._scanner_stages
    if not getattr(current_scanners, _MARKER, False):
        @wraps(current_scanners)
        def scanner_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
            existing = [
                sanitize_rendered_stage(item)
                for item in current_scanners(canonical)
                if isinstance(item, Mapping)
            ]
            replacement = build_scanner_execution_stage(canonical, renderer)
            output: list[dict[str, Any]] = []
            replaced = False
            for item in existing:
                if _text(item.get("stage_id")) == "dependency_security_static_analysis":
                    output.append(replacement)
                    replaced = True
                else:
                    output.append(item)
            if not replaced:
                output.insert(0, replacement)
            return output

        setattr(scanner_stages, _MARKER, True)
        setattr(scanner_stages, "_nico_previous", current_scanners)
        renderer._scanner_stages = scanner_stages

    current_stages = renderer._canonical_stages
    if not getattr(current_stages, _MARKER, False):
        @wraps(current_stages)
        def canonical_stages(canonical: Mapping[str, Any]) -> list[dict[str, Any]]:
            stages = [
                sanitize_rendered_stage(item)
                for item in current_stages(canonical)
                if isinstance(item, Mapping)
            ]
            scanner = build_scanner_execution_stage(canonical, renderer)
            operational = build_ci_operational_stage(canonical, renderer)
            output: list[dict[str, Any]] = []
            seen_scanner = False
            seen_operational = False
            for item in stages:
                stage_id = _text(item.get("stage_id"))
                if stage_id == "dependency_security_static_analysis":
                    output.append(scanner)
                    seen_scanner = True
                elif stage_id == "ci_cd_operational_readiness" and operational:
                    output.append(operational)
                    seen_operational = True
                else:
                    output.append(item)
            if not seen_scanner:
                output.append(scanner)
            if operational and not seen_operational:
                output.append(operational)
            return output

        setattr(canonical_stages, _MARKER, True)
        setattr(canonical_stages, "_nico_previous", current_stages)
        renderer._canonical_stages = canonical_stages

    current_outline = navigation._outline_title
    if not getattr(current_outline, _MARKER, False):
        @wraps(current_outline)
        def outline_title(text: str) -> str:
            return _outline_title(text)

        setattr(outline_title, _MARKER, True)
        setattr(outline_title, "_nico_previous", current_outline)
        navigation._outline_title = outline_title

    current_manifest = manifest._render_manifest_approval_supplement
    if not getattr(current_manifest, _MARKER, False):
        @wraps(current_manifest)
        def render_manifest(
            canonical: Mapping[str, Any],
            entries: list[dict[str, Any]],
        ) -> bytes:
            return render_manifest_approval_supplement(canonical, entries)

        setattr(render_manifest, _MARKER, True)
        setattr(render_manifest, "_nico_previous", current_manifest)
        manifest._render_manifest_approval_supplement = render_manifest

    current_validate = completion._validate_final_surfaces
    if not getattr(current_validate, _MARKER, False):
        @wraps(current_validate)
        def validate(
            canonical: Mapping[str, Any],
            register: Mapping[str, Any],
            markdown: str,
            rendered_html: str,
            pdf: bytes,
        ) -> dict[str, Any]:
            result = dict(
                current_validate(canonical, register, markdown, rendered_html, pdf)
            )
            assert_human_review_package_cleanup(
                canonical, markdown, rendered_html, pdf
            )
            result.update(
                {
                    "client_identity_placeholders_absent": True,
                    "scanner_execution_and_disposition_separated": True,
                    "punctuation_only_metrics_absent": True,
                    "operational_populations_separately_labeled": True,
                    "internal_toc_entries_absent": True,
                    "orphan_detail_pages_absent": True,
                }
            )
            return result

        setattr(validate, _MARKER, True)
        setattr(validate, "_nico_previous", current_validate)
        completion._validate_final_surfaces = validate

    current_final = navigation._validate_final_package
    if not getattr(current_final, _MARKER, False):
        @wraps(current_final)
        def validate_final(result: Mapping[str, Any]) -> None:
            current_final(result)
            canonical = (
                result.get("json")
                if isinstance(result.get("json"), Mapping)
                else {}
            )
            pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
            assert_human_review_package_cleanup(
                canonical,
                str(result.get("markdown") or ""),
                str(result.get("html") or ""),
                pdf,
            )

        setattr(validate_final, _MARKER, True)
        setattr(validate_final, "_nico_previous", current_final)
        navigation._validate_final_package = validate_final

    return {
        "status": "installed",
        "version": VERSION,
        "client_identity_sanitization_bound": getattr(
            completion.prepare_client_report_package, _MARKER, False
        ),
        "scanner_language_bound": getattr(renderer._scanner_stages, _MARKER, False),
        "operational_population_rendering_bound": getattr(
            renderer._canonical_stages, _MARKER, False
        ),
        "toc_allowlist_bound": getattr(navigation._outline_title, _MARKER, False),
        "manifest_layout_bound": getattr(
            manifest._render_manifest_approval_supplement, _MARKER, False
        ),
        "final_surface_gate_bound": getattr(
            navigation._validate_final_package, _MARKER, False
        ),
        "scores_unchanged": True,
        "candidate_dispositions_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_client_identity",
    "_digest_markup",
    "_filename_markup",
    "_outline_title",
    "assert_human_review_package_cleanup",
    "build_ci_operational_stage",
    "build_scanner_execution_stage",
    "install_comprehensive_human_review_package_cleanup_v1",
    "render_manifest_approval_supplement",
    "sanitize_client_identity",
    "sanitize_rendered_stage",
]
