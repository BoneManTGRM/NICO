from __future__ import annotations

import io
from copy import deepcopy
from typing import Any

VERSION = "nico.express_pdf_score_assurance_layout.v44"


def _target_signature(result: dict[str, Any]) -> bool:
    from nico.express_truth_calibration_v38_compat import _uses_v36_truth_model

    return _uses_v36_truth_model(result)


def _overview_pdf(result: dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.units import inch
    from reportlab.platypus import SimpleDocTemplate, Spacer
    from nico import express_pdf_score_assurance_v1 as target

    records = target._records(result)
    styles = target._styles()
    p = lambda value, style=styles["body"]: target._paragraph(value, style)

    # Scanner Worker Evidence can expose an execution-coverage metric while
    # remaining supplemental and excluded from technical maturity. The broader
    # headings prevent that operational metric from being mislabeled as a second
    # technical-health score.
    rows = [[
        p("Control", styles["label"]),
        p("Technical / execution metric", styles["label"]),
        p("Band / treatment", styles["label"]),
        p("Evidence assurance", styles["label"]),
    ]]
    for item in records:
        rows.append([
            p(item["label"]),
            p(item["score_label"]),
            p(item["band"]),
            p(item["assurance"]),
        ])

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=.45 * inch,
        leftMargin=.45 * inch,
        topMargin=.5 * inch,
        bottomMargin=.6 * inch,
        title="NICO Express Technical Score and Assurance",
        author="NICO",
        invariant=1,
    )
    doc.build([
        p("Technical Score, Execution Coverage, and Evidence Assurance", styles["title"]),
        p(
            "Technical health, analyzer execution coverage, and evidence assurance are separate dimensions. Core technical controls contribute to maturity. Supplemental scanner coverage shows whether observed analyzers completed, but is excluded from maturity because those outputs are already mapped into the core controls. Delivery approval remains a separate human decision.",
            styles["callout"],
        ),
        Spacer(1, .06 * inch),
        target._table(rows, [2.30 * inch, 1.55 * inch, 1.45 * inch, 2.00 * inch]),
    ])
    return buffer.getvalue()


def _compact_decision_pdf(result: dict[str, Any], section_id: str, title: str) -> bytes:
    from nico import express_pdf_score_assurance_v1 as target

    original = getattr(_compact_decision_pdf, "_nico_original")
    if not _target_signature(result):
        return original(result, section_id, title)

    section = target._section(result, section_id)
    if not section:
        return original(result, section_id, title)

    limits = {
        "static_analysis": (6, 3, 2),
        "architecture_debt": (7, 5, 2),
        "velocity_complexity": (6, 3, 2),
        "dependency_health": (7, 3, 2),
        "secrets_review": (7, 3, 2),
    }
    evidence_limit, finding_limit, unavailable_limit = limits.get(section_id, (7, 5, 3))
    saved = {
        "evidence": deepcopy(section.get("evidence")),
        "findings": deepcopy(section.get("findings")),
        "unavailable": deepcopy(section.get("unavailable")),
    }
    section["evidence"] = list(section.get("evidence") or [])[:evidence_limit]
    section["findings"] = list(section.get("findings") or [])[:finding_limit]
    section["unavailable"] = list(section.get("unavailable") or [])[:unavailable_limit]
    try:
        return original(result, section_id, title)
    finally:
        section.update(saved)


def install_express_pdf_score_assurance_layout_v39() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as target

    original_overview = getattr(target._overview_pdf, "_nico_original", target._overview_pdf)
    original_decision = getattr(target._decision_pdf, "_nico_original", target._decision_pdf)

    def overview(result: dict[str, Any]) -> bytes:
        return _overview_pdf(result) if _target_signature(result) else original_overview(result)

    setattr(overview, "_nico_original", original_overview)
    setattr(_compact_decision_pdf, "_nico_original", original_decision)
    target._overview_pdf = overview
    target._decision_pdf = _compact_decision_pdf
    return {
        "status": "installed",
        "version": VERSION,
        "duplicate_legacy_status_column_removed_for_calibrated_reports": True,
        "supplemental_execution_coverage_labeled_separately": True,
        "scanner_execution_coverage_excluded_from_maturity": True,
        "long_assurance_labels_fit_without_mid_word_split": True,
        "decision_record_orphan_pages_reduced": True,
        "full_machine_readable_evidence_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_pdf_score_assurance_layout_v39"]
