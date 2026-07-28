from __future__ import annotations

from typing import Any

VERSION = "nico.phase6_pdf_layout.v1"
_PATCH_MARKER = "_nico_phase6_pdf_layout_v1"


def _risk_rows(executive: list[dict[str, Any]]) -> list[list[Any]]:
    rows: list[list[Any]] = [[
        "Priority",
        "Risk ID",
        "Decision title",
        "Business impact",
        "Primary location",
        "Required action",
    ]]
    for item in executive:
        rows.append([
            item.get("priority"),
            item.get("finding_id") or item.get("id"),
            item.get("executive_title") or item.get("title"),
            item.get("business_impact") or item.get("impact"),
            item.get("canonical_location") or item.get("location"),
            item.get("recommendation"),
        ])
    if len(rows) == 1:
        rows.append([
            "—",
            "—",
            "No actionable technical risk retained",
            "Human review remains required",
            "—",
            "Verify evidence completeness and dispositions",
        ])
    return rows


def _disposition_rows(assessment: dict[str, Any]) -> list[list[Any]]:
    rows: list[list[Any]] = [["Analyzer", "Rule", "Source", "Disposition and rationale"]]
    for item in assessment.get("finding_dispositions") or []:
        if not isinstance(item, dict):
            continue
        disposition = item.get("disposition") if isinstance(item.get("disposition"), dict) else {}
        rows.append([
            item.get("tool") or "unknown",
            item.get("rule_id") or "unknown",
            item.get("canonical_location") or item.get("location"),
            f"{disposition.get('classification') or 'reviewed'}: {disposition.get('rationale') or 'Source-specific rationale retained in canonical JSON.'}",
        ])
    return rows


def _patched_risk_architecture_and_controls(self: Any) -> list[Any]:
    c = self.c
    p, table, bullets = c["p"], c["table"], c["bullets"]
    PageBreak, CondPageBreak, KeepTogether, HRFlowable = (
        c["PageBreak"],
        c["CondPageBreak"],
        c["KeepTogether"],
        c["HRFlowable"],
    )
    colors, inch = c["colors"], c["inch"]
    executive, sections = c["executive"], c["sections"]

    story: list[Any] = [
        PageBreak(),
        p("Executive Risk Register", c["h1"]),
        p(
            "Each actionable risk appears once with one stable identity and canonical source location. "
            "Full analyzer text and acceptance detail remain in the finding cards and evidence appendix.",
            c["body"],
        ),
        table(
            _risk_rows(executive),
            [.45 * inch, .8 * inch, 1.25 * inch, 1.45 * inch, 1.25 * inch, 2.25 * inch],
            font_size=5.8,
        ),
    ]

    disposition_rows = _disposition_rows(c["assessment"])
    if len(disposition_rows) > 1:
        story.extend([
            CondPageBreak(2.4 * inch),
            p("Source-Reviewed Analyzer Dispositions", c["h2"]),
            p(
                "These records were not silently suppressed. Each result was reviewed against the exact source and retained with a bounded rationale that expires when the source changes.",
                c["body"],
            ),
            table(
                disposition_rows,
                [.75 * inch, 1.2 * inch, 1.65 * inch, 3.85 * inch],
                font_size=5.7,
            ),
        ])

    architecture = next((item for item in sections if item.get("id") == "architecture_debt"), {})
    story.extend([
        PageBreak(),
        p("Architecture and Actionable Complexity", c["h1"]),
        p("Measured and classified population", c["h2"]),
        *bullets(architecture.get("evidence") or [], 12),
        p("Priority actionable hotspots", c["h2"]),
        *bullets(architecture.get("findings") or [], 8),
        PageBreak(),
        p("CI/CD, Security, and Dependency Evidence", c["h1"]),
    ])

    for section_id in ("ci_cd", "dependency_health", "secrets_review", "static_analysis"):
        section = next((item for item in sections if item.get("id") == section_id), None)
        if not section:
            continue
        block = [
            p(
                f"{section.get('label')} — {section.get('technical_score_display')} · {section.get('assurance_label')}",
                c["h2"],
            ),
            p(section.get("summary"), c["body"]),
            *bullets(section.get("evidence") or [], 9),
        ]
        if section.get("findings"):
            block.extend([p("Findings", c["h3"]), *bullets(section.get("findings") or [], 7)])
        if section.get("unavailable"):
            block.extend([p("Evidence limitations", c["h3"]), *bullets(section.get("unavailable") or [], 7)])
        story.extend([
            CondPageBreak(2.15 * inch),
            KeepTogether(block),
            HRFlowable(
                width="100%",
                thickness=.4,
                color=colors.HexColor("#cbd5e1"),
                spaceBefore=4,
                spaceAfter=4,
            ),
        ])
    return story


def install_phase6_pdf_layout_v1() -> dict[str, Any]:
    from nico.comprehensive_premium_pdf_v6 import _PdfStoryBuilder

    current = _PdfStoryBuilder.risk_architecture_and_controls
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(_patched_risk_architecture_and_controls, _PATCH_MARKER, True)
    _PdfStoryBuilder.risk_architecture_and_controls = _patched_risk_architecture_and_controls
    return {
        "status": "installed",
        "version": VERSION,
        "six_column_executive_register": True,
        "source_reviewed_dispositions_visible": True,
        "dense_ten_column_register_removed": True,
        "nearly_empty_split_page_risk_reduced": True,
    }


__all__ = ["VERSION", "install_phase6_pdf_layout_v1"]
