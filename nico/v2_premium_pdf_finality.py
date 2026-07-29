from __future__ import annotations

import threading
from typing import Any

VERSION = "nico.v2.premium-pdf-finality.v2"
_BUILD_MARKER = "__nico_v2_premium_pdf_build_finality_v2__"
_BUILD_LOCK = threading.RLock()


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


def _bind_source_footer_repair(premium: Any) -> bool:
    current = premium._build_pdf
    if getattr(current, _BUILD_MARKER, False):
        return True

    def repaired_build(*args: Any, **kwargs: Any) -> bytes:
        from reportlab.pdfgen.canvas import Canvas

        with _BUILD_LOCK:
            native_draw_string = Canvas.drawString

            def final_draw_string(canvas: Any, x: float, y: float, text: Any, *draw_args: Any, **draw_kwargs: Any) -> Any:
                if isinstance(text, str):
                    text = text.replace(
                        " · DRAFT",
                        " · FINAL · PENDING HUMAN APPROVAL",
                    )
                return native_draw_string(canvas, x, y, text, *draw_args, **draw_kwargs)

            Canvas.drawString = final_draw_string
            try:
                return current(*args, **kwargs)
            finally:
                Canvas.drawString = native_draw_string

    setattr(repaired_build, _BUILD_MARKER, True)
    setattr(repaired_build, "_nico_previous", current)
    premium._build_pdf = repaired_build
    return premium._build_pdf is repaired_build


def install_v2_premium_pdf_finality() -> dict[str, Any]:
    from nico import comprehensive_premium_pdf_v6 as premium

    premium._PdfStoryBuilder.appendix_and_review = _final_appendix_and_review
    build_bound = _bind_source_footer_repair(premium)
    return {
        "status": "installed" if build_bound else "blocked",
        "version": VERSION,
        "premium_review_gate_uses_final_pending_approval": True,
        "legacy_draft_text_replaced_during_source_render": build_bound,
        "pdf_text_extraction_contains_no_legacy_draft_footer": build_bound,
        "client_delivery_remains_blocked": True,
    }


__all__ = ["VERSION", "install_v2_premium_pdf_finality"]
