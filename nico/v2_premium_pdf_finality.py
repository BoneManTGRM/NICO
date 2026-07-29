from __future__ import annotations

import io
from typing import Any

VERSION = "nico.v2.premium-pdf-finality.v1"
_INSTALL_MARKER = "__nico_v2_premium_pdf_finality_v1__"


def _text(value: Any, limit: int = 80) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _final_appendix_and_review(self: Any) -> list[Any]:
    c = self.c
    p, bullets = c["p"], c["bullets"]
    PageBreak, CondPageBreak, HRFlowable = c["PageBreak"], c["CondPageBreak"], c["HRFlowable"]
    colors = c["colors"]
    story = [
        PageBreak(),
        p("Evidence Appendix", c["h1"]),
        p(
            "Bounded decision-relevant evidence is rendered here; the complete machine-readable ledger is included in JSON and CSV artifacts.",
            c["body"],
        ),
    ]
    for index, stage in enumerate(c["stages"], 1):
        story.extend([
            CondPageBreak(2.5 * c["inch"]),
            p(f"A{index}. {stage.get('title')} — {_text(stage.get('status')).upper()}", c["h2"]),
            p(f"Stage ID: {stage.get('stage_id')}", c["small"]),
            p(stage.get("summary"), c["body"]),
            p(
                f"Evidence records: {len(stage.get('evidence') or [])} · "
                f"Findings: {len(stage.get('findings') or [])} · "
                f"Limitations: {len(stage.get('unavailable') or [])}",
                c["small"],
            ),
            *bullets(stage.get("evidence") or [], 8),
        ])
        if stage.get("findings"):
            story.extend([p("Findings", c["h3"]), *bullets(stage.get("findings") or [], 5)])
        if stage.get("unavailable"):
            story.extend([p("Unavailable or limited evidence", c["h3"]), *bullets(stage.get("unavailable") or [], 5)])
        story.append(HRFlowable(
            width="100%",
            thickness=.35,
            color=colors.HexColor("#cbd5e1"),
            spaceBefore=4,
            spaceAfter=5,
        ))
    story.extend([
        PageBreak(),
        p("Human Review and Acceptance Gate", c["h1"]),
        p(
            "The automated assessment and immutable report package are complete. The report remains pending authorized human approval and is not authorized for client delivery.",
            c["body"],
        ),
        *bullets([
            "Verify exact repository, run, commit, evidence-ledger, customer, and project identities.",
            "Triage every material, review-required, failed, timed-out, and unavailable analyzer result.",
            "Confirm JSON, CSV, Markdown, HTML, and PDF show the same technical score, Evidence-Adjusted score, assurance, limitation accounting, and delivery status.",
            "Disposition every P1 against its binary acceptance criteria and residual-risk statement.",
            "Validate business context, assumptions, roadmap, staffing, effort, and any financial scenario inputs.",
            "Approve or reject the exact immutable report package before delivery.",
        ], 10),
        p(
            "FINAL REPORT · PENDING HUMAN APPROVAL · CLIENT DELIVERY BLOCKED · CLIENT DELIVERY NOT AUTHORIZED",
            c["warning"],
        ),
    ])
    return story


def _final_footer_overlay(pdf_bytes: bytes, identity: dict[str, Any]) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    reader = PdfReader(io.BytesIO(pdf_bytes))
    writer = PdfWriter()
    width, _ = letter
    for index, page in enumerate(reader.pages):
        if index >= 2:
            buffer = io.BytesIO()
            overlay = canvas.Canvas(buffer, pagesize=letter, invariant=1)
            overlay.setFillColor(colors.white)
            overlay.rect(0, 0, width, 31, stroke=0, fill=1)
            overlay.setFillColor(colors.HexColor("#64748b"))
            overlay.setFont("Helvetica", 7)
            overlay.drawString(
                39.6,
                10,
                f"NICO Comprehensive · {_text(identity.get('run_id'), 32)} · "
                f"{_text(identity.get('commit_sha'), 12)} · FINAL · PENDING HUMAN APPROVAL",
            )
            overlay.drawRightString(width - 39.6, 10, f"Page {index + 1}")
            overlay.save()
            replacement = PdfReader(io.BytesIO(buffer.getvalue())).pages[0]
            page.merge_page(replacement, over=True)
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def install_v2_premium_pdf_finality() -> dict[str, Any]:
    from nico import comprehensive_express_quality_v7 as quality
    from nico import comprehensive_premium_pdf_v6 as premium

    premium._PdfStoryBuilder.appendix_and_review = _final_appendix_and_review
    current = quality.comprehensive_pdf_with_final_count
    if not getattr(current, _INSTALL_MARKER, False):
        def wrapped(
            identity: dict[str, Any],
            assessment: dict[str, Any],
            stages: list[dict[str, Any]],
            roadmap: list[dict[str, Any]],
            staffing: list[dict[str, Any]],
            limitations: dict[str, int],
            generated_at: str,
        ) -> tuple[bytes, int]:
            pdf, count = current(identity, assessment, stages, roadmap, staffing, limitations, generated_at)
            repaired = _final_footer_overlay(pdf, identity)
            return repaired, count

        setattr(wrapped, _INSTALL_MARKER, True)
        setattr(wrapped, "_nico_previous", current)
        quality.comprehensive_pdf_with_final_count = wrapped
    return {
        "status": "installed",
        "version": VERSION,
        "premium_review_gate_uses_final_pending_approval": True,
        "legacy_draft_footers_overlaid": True,
        "client_delivery_remains_blocked": True,
    }


__all__ = ["VERSION", "install_v2_premium_pdf_finality"]
