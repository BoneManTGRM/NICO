from __future__ import annotations

import html
import io
from collections import Counter
from typing import Any


VERSION = "nico.express_compact_dossier_pdf.v1"
_PATCH_MARKER = "_nico_express_compact_dossier_pdf_v1"
_MAX_DETAILED_DOSSIERS = 5


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _severity_rank(value: Any) -> int:
    return {
        "critical": 0,
        "high": 1,
        "medium": 2,
        "low": 3,
        "informational": 4,
        "unclassified": 5,
    }.get(_clean(value).lower(), 6)


def _confidence_rank(value: Any) -> int:
    return {"high": 0, "standard": 1, "medium": 1, "review-limited": 2, "low": 3}.get(
        _clean(value).lower(), 4
    )


def _compact_dossier_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    from nico.express_report_finding_dossiers_v15 import build_finding_dossiers, report_labels
    from nico.express_report_dossier_export_v15 import _locale

    locale = _locale(result)
    labels = report_labels(locale)
    dossiers = list(build_finding_dossiers(result))
    dossiers.sort(
        key=lambda item: (
            _severity_rank(getattr(item, "severity", "")),
            _confidence_rank(getattr(item, "confidence", "")),
            _clean(getattr(item, "finding_id", "")),
        )
    )
    detailed = dossiers[:_MAX_DETAILED_DOSSIERS]
    remaining = dossiers[_MAX_DETAILED_DOSSIERS:]

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.46 * inch,
        leftMargin=0.46 * inch,
        topMargin=0.44 * inch,
        bottomMargin=0.52 * inch,
        title=labels["title"],
        author="NICO",
        invariant=1,
    )
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "CompactDossierTitle",
        parent=styles["Title"],
        fontSize=16,
        leading=18,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=6,
    )
    h2 = ParagraphStyle(
        "CompactDossierH2",
        parent=styles["Heading2"],
        fontSize=9.2,
        leading=11,
        textColor=colors.HexColor("#075985"),
        spaceBefore=3,
        spaceAfter=2,
    )
    body = ParagraphStyle(
        "CompactDossierBody",
        parent=styles["BodyText"],
        fontSize=7.0,
        leading=8.6,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2,
    )
    tiny = ParagraphStyle(
        "CompactDossierTiny",
        parent=body,
        fontSize=6.1,
        leading=7.2,
        textColor=colors.HexColor("#475569"),
    )

    def p(value: Any, style: Any = body) -> Paragraph:
        return Paragraph(html.escape(_clean(value)), style)

    story: list[Any] = [
        p(f"{labels['finding_dossier']} Appendix", title),
        p(labels["human_review"], h2),
        p(
            (
                "The PDF contains the highest-priority decision records. The complete finding set remains available "
                "in the Markdown, HTML, JSON evidence bundle, and immutable evidence ledger."
                if locale == "en"
                else "El PDF contiene los registros de decisión de mayor prioridad. El conjunto completo de hallazgos "
                "permanece disponible en Markdown, HTML, el paquete JSON y el libro mayor inmutable de evidencia."
            ),
            body,
        ),
        Spacer(1, 0.04 * inch),
    ]

    for dossier in detailed:
        evidence = list(getattr(dossier, "evidence", []) or [])[:2]
        card = [
            Table(
                [
                    [p(f"{dossier.finding_id} — {dossier.title}", h2)],
                    [
                        p(
                            f"Section: {dossier.section_id} · Severity: {str(dossier.severity).upper()} · "
                            f"Confidence: {dossier.confidence} · Disposition: {dossier.disposition}",
                            tiny,
                        )
                    ],
                ],
                colWidths=[7.58 * inch],
                style=TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0f2fe")),
                        ("BOX", (0, 0), (-1, -1), 0.45, colors.HexColor("#94a3b8")),
                        ("LEFTPADDING", (0, 0), (-1, -1), 5),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]
                ),
            ),
            p(f"{labels['business_impact']}: {dossier.business_impact}", body),
        ]
        if evidence:
            card.append(p("Evidence: " + " | ".join(_clean(item) for item in evidence), tiny))
        card.extend(
            [
                p(f"{labels['repair_specification']}: {dossier.repair_specification}", body),
                p(f"{labels['verification']}: {dossier.verification}", tiny),
                Spacer(1, 0.06 * inch),
            ]
        )
        story.append(KeepTogether(card))

    if remaining:
        severity_counts = Counter(_clean(item.severity).lower() or "pending" for item in remaining)
        section_counts = Counter(_clean(item.section_id) or "unknown" for item in remaining)
        story.extend(
            [
                p("Remaining finding inventory", h2),
                p(
                    f"{len(remaining)} additional decision records are retained outside the concise PDF appendix. "
                    f"Severity inventory: {', '.join(f'{key}={value}' for key, value in sorted(severity_counts.items()))}. "
                    f"Section inventory: {', '.join(f'{key}={value}' for key, value in sorted(section_counts.items()))}.",
                    body,
                ),
            ]
        )

    doc.build(story)
    return buffer.getvalue()


def install_express_compact_dossier_pdf() -> dict[str, Any]:
    from nico import express_report_dossier_export_v15 as exporter

    current = exporter._dossier_pdf
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}
    setattr(_compact_dossier_pdf, _PATCH_MARKER, True)
    setattr(_compact_dossier_pdf, "_nico_previous", current)
    exporter._dossier_pdf = _compact_dossier_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "max_detailed_dossiers": _MAX_DETAILED_DOSSIERS,
        "full_evidence_retained_outside_pdf": True,
    }


__all__ = ["VERSION", "install_express_compact_dossier_pdf"]
