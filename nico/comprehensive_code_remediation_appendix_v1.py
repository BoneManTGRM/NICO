from __future__ import annotations

import csv
import hashlib
import html
import io
import re
from functools import wraps
from typing import Any, Callable

VERSION = "nico.comprehensive_code_remediation_appendix.v1"
_PATCH_MARKER = "_nico_comprehensive_code_remediation_appendix_v1"
_LOCATION_RE = re.compile(
    r"(?P<path>[A-Za-z0-9_./-]+\.(?:py|pyi|ts|tsx|js|jsx|mjs|cjs|go|rs|java|kt|swift|rb|php|cs|cpp|cc|c|h|hpp|sql|yml|yaml|json|toml|ini|cfg|sh|ps1)):(?P<line>\d+)"
)


def _text(value: Any, limit: int = 2600) -> str:
    value = " ".join(str(value or "").split())
    return value if len(value) <= limit else value[: limit - 3].rstrip() + "..."


def _specific_change(finding: dict[str, Any]) -> str:
    title = _text(finding.get("title")).casefold()
    location = _text(finding.get("location"))
    recommendation = _text(finding.get("recommendation"))
    if "complexity hotspot" in title:
        return (
            f"Refactor the code centered at {location} into bounded responsibilities. Preserve current behavior with characterization tests, "
            "then extract state/lifecycle handling, evidence interpretation, report actions, and presentation logic into independently testable units. "
            + recommendation
        )
    if "dynamic code execution" in title or "python_eval_exec" in title:
        return (
            f"Inspect the exact expression at {location}. If it performs dynamic execution, replace it with a typed dispatch table, direct function call, "
            "or explicit parser appropriate to the data. If the match is a scanner false positive in TypeScript/JavaScript text, retain the source excerpt and "
            "record a bounded reviewer disposition instead of changing safe code blindly."
        )
    if "dependency" in title or _text(finding.get("category")).casefold() == "dependency":
        return (
            f"Trace the dependency evidence associated with {location or 'the retained manifest/lockfile boundary'}, update or constrain the affected package, "
            "regenerate the exact lockfile, run dependency analyzers, and verify the application build and tests on the same proposed revision."
        )
    return recommendation or (
        f"Review the exact code at {location}, apply the smallest behavior-preserving repair supported by the retained evidence, and verify it with targeted and full regression tests."
    )


def build_code_remediation_plan(assessment: dict[str, Any]) -> list[dict[str, Any]]:
    findings = [
        item for item in assessment.get("findings_register") or []
        if isinstance(item, dict)
    ]
    plan: list[dict[str, Any]] = []
    for finding in findings:
        location = _text(finding.get("location"), 500)
        match = _LOCATION_RE.search(location)
        if not match:
            continue
        index = len(plan) + 1
        acceptance = _text(finding.get("acceptance_criteria"))
        priority = _text(finding.get("priority")) or "P2"
        title = _text(finding.get("title")) or "Code remediation item"
        plan.append(
            {
                "remediation_id": f"NICO-CODE-{index:03d}",
                "priority": priority,
                "title": title,
                "category": _text(finding.get("category")) or "code",
                "file_path": match.group("path"),
                "line": int(match.group("line")),
                "location": location,
                "evidence": _text(finding.get("evidence")),
                "technical_consequence": _text(finding.get("impact")),
                "specific_code_update": _specific_change(finding),
                "implementation_steps": [
                    f"Open the exact immutable-revision location {location} and retain a source excerpt in the review record.",
                    "Add or identify characterization tests that prove the current intended behavior before editing.",
                    "Apply the smallest bounded change described in the proposed update; do not broaden scope into unrelated refactoring.",
                    "Run targeted tests, type/lint/static checks, and the full regression suite required by the affected subsystem.",
                    "Rerun NICO against the resulting exact commit and confirm the finding is resolved or explicitly dispositioned without new regression evidence.",
                ],
                "verification_test": acceptance or "Targeted and full regression tests pass, and the exact-SHA rerun closes the finding.",
                "rollback_plan": "Revert the isolated remediation commit or pull request if targeted/full verification fails; retain the failed evidence and do not authorize delivery.",
                "exit_criteria": acceptance or "Exact location is reviewed, repaired or dispositioned, tests pass, and the next exact-SHA assessment no longer reports an unresolved material finding.",
                "owner_role": _text(finding.get("owner_role")) or "Senior Product Engineer",
                "effort": _text(finding.get("effort")) or "Requires engineering estimate",
                "patch_status": "PROPOSED · SOURCE-CONTEXT REVIEW REQUIRED",
                "automatic_merge_allowed": False,
                "human_review_required": True,
            }
        )
        if len(plan) >= 12:
            break
    return plan


def code_remediation_csv(plan: list[dict[str, Any]]) -> str:
    buffer = io.StringIO()
    fields = [
        "remediation_id", "priority", "title", "category", "file_path", "line",
        "location", "evidence", "technical_consequence", "specific_code_update",
        "verification_test", "rollback_plan", "exit_criteria", "owner_role", "effort",
        "patch_status", "automatic_merge_allowed", "human_review_required",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
    writer.writeheader()
    for item in plan:
        writer.writerow({field: item.get(field, "") for field in fields})
    return buffer.getvalue()


def _markdown_section(plan: list[dict[str, Any]]) -> str:
    if not plan:
        return "\n\n## Code Remediation Plan\n\nNo exact file-and-line code remediation item was retained for this run.\n"
    lines = ["", "", "## Code Remediation Plan", "", "Proposed changes remain subject to exact-source review, testing, and human approval.", ""]
    for item in plan:
        lines += [
            f"### {item['remediation_id']} · {item['priority']} · {item['title']}",
            "",
            f"- Exact location: `{item['location']}`",
            f"- Owner / effort: {item['owner_role']} · {item['effort']}",
            f"- Patch status: {item['patch_status']}",
            f"- Technical consequence: {item['technical_consequence']}",
            f"- Specific code update: {item['specific_code_update']}",
            f"- Verification: {item['verification_test']}",
            f"- Rollback: {item['rollback_plan']}",
            f"- Exit criteria: {item['exit_criteria']}",
            "",
        ]
    return "\n".join(lines)


def _html_section(plan: list[dict[str, Any]]) -> str:
    rows: list[str] = [
        '<section id="code-remediation-plan">',
        "<h2>Code Remediation Plan</h2>",
        "<p>Proposed changes remain subject to exact-source review, testing, and human approval.</p>",
    ]
    if not plan:
        rows.append("<p>No exact file-and-line code remediation item was retained for this run.</p>")
    for item in plan:
        rows += [
            f"<h3>{html.escape(item['remediation_id'])} · {html.escape(item['priority'])} · {html.escape(item['title'])}</h3>",
            "<table>",
            f"<tr><th>Exact location</th><td><code>{html.escape(item['location'])}</code></td></tr>",
            f"<tr><th>Technical consequence</th><td>{html.escape(item['technical_consequence'])}</td></tr>",
            f"<tr><th>Specific code update</th><td>{html.escape(item['specific_code_update'])}</td></tr>",
            f"<tr><th>Verification</th><td>{html.escape(item['verification_test'])}</td></tr>",
            f"<tr><th>Rollback</th><td>{html.escape(item['rollback_plan'])}</td></tr>",
            f"<tr><th>Exit criteria</th><td>{html.escape(item['exit_criteria'])}</td></tr>",
            f"<tr><th>Owner / effort</th><td>{html.escape(item['owner_role'])} · {html.escape(item['effort'])}</td></tr>",
            f"<tr><th>Patch status</th><td>{html.escape(item['patch_status'])}</td></tr>",
            "</table>",
        ]
    rows.append("</section>")
    return "\n".join(rows)


def _appendix_pdf(plan: list[dict[str, Any]], *, base_page_count: int, final_page_count: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("CR-H1", parent=styles["Heading1"], fontName="Helvetica-Bold", fontSize=19, leading=23, textColor=colors.HexColor("#0f172a"), spaceAfter=10)
    h2 = ParagraphStyle("CR-H2", parent=styles["Heading2"], fontName="Helvetica-Bold", fontSize=12, leading=15, textColor=colors.HexColor("#075985"), spaceAfter=7)
    body = ParagraphStyle("CR-Body", parent=styles["BodyText"], fontSize=8.2, leading=11.2, textColor=colors.HexColor("#334155"), spaceAfter=5)
    small = ParagraphStyle("CR-Small", parent=body, fontSize=7.2, leading=9.6)
    warning = ParagraphStyle("CR-Warning", parent=body, fontName="Helvetica-Bold", textColor=colors.HexColor("#92400e"), backColor=colors.HexColor("#fef3c7"), borderColor=colors.HexColor("#f59e0b"), borderWidth=.8, borderPadding=7, spaceAfter=8)

    def p(value: Any, style: ParagraphStyle = body) -> Paragraph:
        return Paragraph(html.escape(_text(value)), style)

    def footer(canvas: Any, doc: Any) -> None:
        page_number = base_page_count + doc.page
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(.55 * inch, .36 * inch, "NICO Unified Strategic Assessment · Code Remediation Appendix")
        canvas.drawRightString(7.95 * inch, .36 * inch, f"Page {page_number} of {final_page_count}")
        canvas.restoreState()

    story: list[Any] = []
    if not plan:
        story = [p("Code Remediation Plan", h1), p("No exact file-and-line code remediation item was retained for this run.", warning)]
    for index, item in enumerate(plan):
        story += [
            p("Code Remediation Plan", h1),
            p(f"{item['remediation_id']} · {item['priority']} · {item['title']}", h2),
            p("PROPOSED CHANGE · EXACT SOURCE REVIEW AND HUMAN APPROVAL REQUIRED", warning),
        ]
        rows = [
            ["Exact location", item["location"]],
            ["Owner / effort", f"{item['owner_role']} · {item['effort']}"],
            ["Evidence", item["evidence"]],
            ["Technical consequence", item["technical_consequence"]],
            ["Specific code update", item["specific_code_update"]],
            ["Verification test", item["verification_test"]],
            ["Rollback", item["rollback_plan"]],
            ["Exit criteria", item["exit_criteria"]],
            ["Patch status", item["patch_status"]],
        ]
        table = Table([[p(left, small), p(right, small)] for left, right in rows], colWidths=[1.35 * inch, 6.1 * inch], hAlign="LEFT")
        table.setStyle(TableStyle([
            ("GRID", (0, 0), (-1, -1), .35, colors.HexColor("#cbd5e1")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
            ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ]))
        story += [table, Spacer(1, .08 * inch), p("Implementation sequence", h2)]
        for step_number, step in enumerate(item.get("implementation_steps") or [], 1):
            story.append(p(f"{step_number}. {step}", small))
        if index < len(plan) - 1:
            story.append(PageBreak())

    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=.55 * inch, leftMargin=.55 * inch, topMargin=.55 * inch, bottomMargin=.6 * inch, title="NICO Code Remediation Plan", author="NICO", invariant=1)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _page_count_overlay(identity: dict[str, Any], limitations: dict[str, int], final_page_count: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    width, _height = letter

    page.setFillColor(colors.HexColor("#020617"))
    page.rect(0, 0, width, 88, stroke=0, fill=1)
    page.setFillColor(colors.HexColor("#a9b6c9"))
    page.setFont("Helvetica", 7)
    page.drawString(42, 68, "READ-ONLY · IMMUTABLE SNAPSHOT · HUMAN REVIEW REQUIRED")
    page.setFillColor(colors.HexColor("#38bdf8"))
    page.setFont("Helvetica-Bold", 7)
    page.drawRightString(570, 68, "POWERED BY REPARODYNAMICS")
    page.setFillColor(colors.HexColor("#fb7185"))
    page.setFont("Helvetica", 7)
    page.drawString(42, 51, "Not approved for client delivery")
    page.setFillColor(colors.white)
    page.drawRightString(570, 51, f"Page 1 of {final_page_count}")
    page.showPage()

    page.setFillColor(colors.white)
    page.rect(0, 0, width, 94, stroke=0, fill=1)
    page.setFillColor(colors.HexColor("#075985"))
    page.setFont("Helvetica-Bold", 7)
    page.drawString(42, 76, "PACKAGE IDENTITY")
    page.setFillColor(colors.HexColor("#475569"))
    page.setFont("Helvetica", 6.7)
    page.drawString(42, 62, f"Run: {_text(identity.get('run_id'), 48)}")
    page.drawCentredString(width / 2, 62, f"Limitations: {limitations.get('individual_limitation_records', 0)}")
    page.drawRightString(570, 62, f"Final PDF pages: {final_page_count}")
    page.drawString(42, 38, "NICO Unified Strategic Assessment · evidence-bound · report only · human review required")
    page.drawRightString(570, 38, f"Page 2 of {final_page_count}")
    page.showPage()
    page.save()
    return buffer.getvalue()


def _append_code_pages(
    original_bytes: bytes,
    *,
    identity: dict[str, Any],
    assessment: dict[str, Any],
    limitations: dict[str, int],
) -> tuple[bytes, int]:
    from pypdf import PdfReader, PdfWriter

    plan = assessment.get("code_remediation_plan") if isinstance(assessment.get("code_remediation_plan"), list) else build_code_remediation_plan(assessment)
    base_reader = PdfReader(io.BytesIO(original_bytes))
    provisional = _appendix_pdf(plan, base_page_count=len(base_reader.pages), final_page_count=len(base_reader.pages) + max(1, len(plan)))
    appendix_reader = PdfReader(io.BytesIO(provisional))
    final_count = len(base_reader.pages) + len(appendix_reader.pages)
    appendix_reader = PdfReader(io.BytesIO(_appendix_pdf(plan, base_page_count=len(base_reader.pages), final_page_count=final_count)))
    overlay_reader = PdfReader(io.BytesIO(_page_count_overlay(identity, limitations, final_count)))

    writer = PdfWriter()
    for index, page in enumerate(base_reader.pages):
        if index < len(overlay_reader.pages):
            page.merge_page(overlay_reader.pages[index], over=True)
        writer.add_page(page)
    for page in appendix_reader.pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), final_count


def install_comprehensive_code_remediation_appendix_v1() -> dict[str, Any]:
    from nico import comprehensive_decision_grade_report_v5 as report

    current_decorate: Callable[[dict[str, Any]], dict[str, Any]] = report._decorate_assessment
    current_markdown: Callable[..., str] = report._build_markdown
    current_html: Callable[..., str] = report._build_html
    current_pdf: Callable[..., tuple[bytes, int]] = report.comprehensive_pdf_with_final_count
    current_build: Callable[..., dict[str, Any]] = report.build_comprehensive_report_package

    if getattr(current_build, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "exact_location_code_plan": True,
            "pdf_code_pages": True,
            "machine_readable_code_plan": True,
            "automatic_merge_allowed": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    @wraps(current_decorate)
    def decorate(assessment: dict[str, Any]) -> dict[str, Any]:
        output = current_decorate(assessment)
        output["code_remediation_plan"] = build_code_remediation_plan(output)
        output["code_remediation_contract"] = {
            "version": VERSION,
            "exact_file_and_line_required": True,
            "proposed_patches_require_source_context": True,
            "automatic_merge_allowed": False,
            "human_review_required": True,
        }
        return output

    @wraps(current_markdown)
    def markdown(*args: Any, **kwargs: Any) -> str:
        assessment = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs.get("assessment", {})
        plan = assessment.get("code_remediation_plan") if isinstance(assessment, dict) else []
        return current_markdown(*args, **kwargs) + _markdown_section(plan or [])

    @wraps(current_html)
    def rendered_html(*args: Any, **kwargs: Any) -> str:
        assessment = args[1] if len(args) > 1 and isinstance(args[1], dict) else kwargs.get("assessment", {})
        plan = assessment.get("code_remediation_plan") if isinstance(assessment, dict) else []
        original = current_html(*args, **kwargs)
        section = _html_section(plan or [])
        return original.replace("</body>", section + "\n</body>") if "</body>" in original else original + section

    @wraps(current_pdf)
    def pdf_with_code_pages(
        identity: dict[str, Any],
        assessment: dict[str, Any],
        stages: list[dict[str, Any]],
        roadmap: list[dict[str, Any]],
        staffing: list[dict[str, Any]],
        limitations: dict[str, int],
        generated_at: str,
    ) -> tuple[bytes, int]:
        pdf_bytes, _page_count = current_pdf(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
        return _append_code_pages(pdf_bytes, identity=identity, assessment=assessment, limitations=limitations)

    @wraps(current_build)
    def build(*args: Any, **kwargs: Any) -> dict[str, Any]:
        result = current_build(*args, **kwargs)
        assessment = result.get("assessment") if isinstance(result.get("assessment"), dict) else {}
        plan = assessment.get("code_remediation_plan") if isinstance(assessment.get("code_remediation_plan"), list) else []
        csv_text = code_remediation_csv(plan)
        package = result.get("report_package") if isinstance(result.get("report_package"), dict) else {}
        package["code_remediation_plan"] = plan
        package["code_remediation_csv"] = csv_text
        package["code_remediation_csv_sha256"] = hashlib.sha256(csv_text.encode("utf-8")).hexdigest()
        package["code_remediation_appendix_present"] = True
        quality = result.get("report_quality_contract") if isinstance(result.get("report_quality_contract"), dict) else {}
        quality["exact_location_code_remediation_plan"] = bool(plan) or not assessment.get("findings_register")
        quality["pdf_code_remediation_appendix"] = bool(package.get("pdf_base64"))
        quality["automatic_code_merge_allowed"] = False
        result["report_package"] = package
        result["report_quality_contract"] = quality
        return result

    setattr(decorate, _PATCH_MARKER, True)
    setattr(markdown, _PATCH_MARKER, True)
    setattr(rendered_html, _PATCH_MARKER, True)
    setattr(pdf_with_code_pages, _PATCH_MARKER, True)
    setattr(build, _PATCH_MARKER, True)
    report._decorate_assessment = decorate
    report._build_markdown = markdown
    report._build_html = rendered_html
    report.comprehensive_pdf_with_final_count = pdf_with_code_pages
    report.build_comprehensive_report_package = build

    return {
        "status": "installed",
        "version": VERSION,
        "exact_location_code_plan": True,
        "pdf_code_pages": True,
        "markdown_code_section": True,
        "html_code_section": True,
        "machine_readable_code_plan": True,
        "code_remediation_csv": True,
        "page_count_reconciled_after_appendix": True,
        "automatic_merge_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "build_code_remediation_plan",
    "code_remediation_csv",
    "install_comprehensive_code_remediation_appendix_v1",
]
