from __future__ import annotations

import base64
import io
from dataclasses import replace
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

VERSION = "nico.accurate_green_release.v2"
_RECORDS_MARKER = "_nico_accurate_green_records_v2"
_PUBLISH_MARKER = "_nico_accurate_green_publish_v2"
_INDEX_MARKER = "_nico_accurate_green_index_v2"
_PDF_MARKER = "_nico_accurate_green_pdf_v2"


def _text(value: Any, limit: int = 700) -> str:
    normalized = " ".join(str(value or "").split())
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _verified_green(item: dict[str, Any]) -> bool:
    score = item.get("technical_score")
    return bool(
        item.get("directly_scored") is True
        and isinstance(score, (int, float))
        and not isinstance(score, bool)
        and score >= 80
        and _text(item.get("assurance_status")).casefold() == "verified"
        and _text(item.get("canonical_status")).upper() == "GREEN"
    )


def _ensure_record_contract(item: dict[str, Any]) -> dict[str, Any]:
    item.setdefault("findings", [])
    item.setdefault("unavailable", [])
    item.setdefault("score_rationale", "")
    item["verified_green"] = _verified_green(item)
    return item


def _section_action(section_id: str) -> str:
    actions = {
        "dependency_health": (
            "Identify each current-run pip-audit, npm-audit, or OSV candidate by package, version, advisory, and reachability; "
            "repair confirmed exposure or retain a signed not-affected disposition, then rerun the exact SHA."
        ),
        "dependency_library_ecosystem": (
            "Identify each current-run pip-audit, npm-audit, or OSV candidate by package, version, advisory, and reachability; "
            "repair confirmed exposure or retain a signed not-affected disposition, then rerun the exact SHA."
        ),
        "secrets_review": (
            "Complete full-history Gitleaks and TruffleHog execution without timeout, expose redacted candidate fingerprints and exact locations, "
            "rotate confirmed credentials, and sign false-positive or synthetic dispositions before the exact-SHA rerun."
        ),
        "static_analysis": (
            "Complete Bandit, Semgrep, ESLint, and TypeScript as distinct analyzers; group duplicate candidates, retain rule, severity, path, and line, "
            "repair confirmed defects, and sign evidenced false-positive or not-applicable dispositions."
        ),
        "velocity_complexity": (
            "Retain the current-run complexity artifact, commit cadence, and pull-request traceability; close technical findings and the scanner-clean release gate, "
            "then recompute the score without lowering the 80-point threshold."
        ),
        "velocity_and_complexity": (
            "Retain the current-run complexity artifact, commit cadence, and pull-request traceability; close technical findings and the scanner-clean release gate, "
            "then recompute the score without lowering the 80-point threshold."
        ),
    }
    return actions.get(
        section_id.casefold(),
        "Resolve retained findings and unavailable evidence, preserve exact-run artifacts and signed dispositions, then rerun the immutable snapshot.",
    )


def _improvement_plan(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    plan: list[dict[str, Any]] = []
    for raw in records:
        if not isinstance(raw, dict):
            continue
        item = _ensure_record_contract(raw)
        if item.get("directly_scored") is not True or item.get("verified_green") is True:
            continue
        section_id = _text(item.get("section_id"), 120)
        score = item.get("technical_score")
        current = (
            f"{_text(item.get('technical_band_label') or 'NOT SCORED', 60)} · "
            f"{int(score)}/100 · {_text(item.get('assurance_label') or 'UNVERIFIED', 80)} · "
            f"{_text(item.get('canonical_status') or 'UNKNOWN', 40)}"
            if isinstance(score, (int, float)) and not isinstance(score, bool)
            else f"NOT SCORED · {_text(item.get('assurance_label') or 'UNVERIFIED', 80)}"
        )
        evidence_blockers = [
            _text(value, 260)
            for field in ("unavailable", "findings")
            for value in item.get(field) or []
            if _text(value)
        ][:3]
        plan.append(
            {
                "section_id": section_id,
                "label": _text(item.get("label") or section_id, 180),
                "current_state": current,
                "recommended_action": _section_action(section_id),
                "retained_blockers": evidence_blockers,
                "exit_criteria": (
                    "Technical score >= 80; evidence assurance VERIFIED; risk disposition GREEN; "
                    "all required exact-SHA artifacts parseable and digest-bound; no unresolved failed, timed-out, unavailable, or untriaged state."
                ),
            }
        )
    return plan


def _install_export_compat() -> dict[str, Any]:
    from nico import express_score_assurance_export_v1 as export

    records_current: Callable[[dict[str, Any]], list[dict[str, Any]]] = export._records
    if not getattr(records_current, _RECORDS_MARKER, False):
        @wraps(records_current)
        def records(result: dict[str, Any]) -> list[dict[str, Any]]:
            return [
                _ensure_record_contract(item)
                for item in records_current(result)
                if isinstance(item, dict)
            ]

        setattr(records, _RECORDS_MARKER, True)
        setattr(records, "_nico_previous", records_current)
        export._records = records

    publish_current: Callable[[dict[str, Any]], dict[str, Any]] = export.publish_score_assurance_exports
    if not getattr(publish_current, _PUBLISH_MARKER, False):
        @wraps(publish_current)
        def publish(result: dict[str, Any]) -> dict[str, Any]:
            output = publish_current(result)
            contract = output.get("score_assurance_export")
            records = contract.get("records") if isinstance(contract, dict) else []
            plan = _improvement_plan(records if isinstance(records, list) else [])
            output["yellow_section_improvement_plan"] = {
                "status": "complete",
                "version": VERSION,
                "controls": plan,
                "control_count": len(plan),
                "thresholds_lowered": False,
                "missing_evidence_treated_as_clean": False,
                "human_review_required": True,
                "client_delivery_allowed": False,
            }
            if isinstance(contract, dict):
                contract["yellow_section_improvement_plan"] = plan
                contract["accurate_green_compat_version"] = VERSION
            return output

        setattr(publish, _PUBLISH_MARKER, True)
        setattr(publish, "_nico_previous", publish_current)
        export.publish_score_assurance_exports = publish

    return {
        "status": "installed",
        "record_contract_hardened": True,
        "yellow_improvement_plan_attached": True,
    }


def _append_canonical_section_index(result: dict[str, Any]) -> dict[str, Any]:
    from nico import express_pdf_section_index_v1 as index

    reports = result.get("reports")
    if not isinstance(reports, dict):
        raise RuntimeError("Express report package is unavailable for PDF section indexing")
    encoded = reports.get("pdf_base64")
    if not isinstance(encoded, str) or not encoded.strip():
        raise RuntimeError("Express PDF is unavailable for canonical section indexing")

    raw = base64.b64decode(encoded, validate=True)
    reader = PdfReader(io.BytesIO(raw))
    records = index._records(result)
    existing_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    required_labels = [item["label"] for item in records]
    score_labels = list(dict.fromkeys(item["score_label"] for item in records))
    missing_labels_before = [label for label in required_labels if label not in existing_text]
    missing_scores_before = [score for score in score_labels if score not in existing_text]

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)
    if missing_labels_before or missing_scores_before:
        index_reader = PdfReader(io.BytesIO(index._index_pdf(result, records)))
        for page in index_reader.pages:
            writer.add_page(page)

    output = io.BytesIO()
    writer.write(output)
    final_bytes = output.getvalue()
    final_reader = PdfReader(io.BytesIO(final_bytes))
    final_text = "\n".join(page.extract_text() or "" for page in final_reader.pages)
    missing_labels_after = [label for label in required_labels if label not in final_text]
    missing_scores_after = [score for score in score_labels if score not in final_text]
    if missing_labels_after or missing_scores_after:
        raise RuntimeError(
            "Express PDF canonical section parity failed: "
            f"missing_labels={missing_labels_after}, missing_scores={missing_scores_after}"
        )

    reports["pdf_base64"] = base64.b64encode(final_bytes).decode("ascii")
    result["express_pdf_section_index"] = {
        "status": "complete",
        "version": VERSION,
        "record_count": len(records),
        "records": records,
        "page_count_before": len(reader.pages),
        "page_count_after": len(final_reader.pages),
        "index_appended": bool(missing_labels_before or missing_scores_before),
        "missing_labels_before": missing_labels_before,
        "missing_score_labels_before": missing_scores_before,
        "missing_labels_after": missing_labels_after,
        "missing_score_labels_after": missing_scores_after,
        "canonical_labels_present": not missing_labels_after,
        "canonical_scores_present": not missing_scores_after,
        "score_band_separated_from_assurance": True,
        "canonical_status_retained": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return result


def _install_index_compat() -> dict[str, Any]:
    from nico import express_pdf_section_index_binding_v1 as binding
    from nico import express_pdf_section_index_v1 as index

    setattr(_append_canonical_section_index, _INDEX_MARKER, True)
    index.append_canonical_section_index = _append_canonical_section_index
    binding.append_canonical_section_index = _append_canonical_section_index
    return {
        "status": "installed",
        "labels_or_scores_trigger_index": True,
        "binding_rebound": binding.append_canonical_section_index is _append_canonical_section_index,
    }


def _plan_pdf(result: dict[str, Any], plan: list[dict[str, Any]]) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "AccurateGreenTitle",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=22,
        leading=25,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=8,
    )
    subtitle = ParagraphStyle(
        "AccurateGreenSubtitle",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#334155"),
        backColor=colors.HexColor("#ecfeff"),
        borderColor=colors.HexColor("#22d3ee"),
        borderWidth=0.8,
        borderPadding=8,
        spaceAfter=9,
    )
    body = ParagraphStyle(
        "AccurateGreenBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.3,
        leading=9.2,
        textColor=colors.HexColor("#334155"),
    )
    header = ParagraphStyle(
        "AccurateGreenHeader",
        parent=body,
        fontName="Helvetica-Bold",
        fontSize=7.1,
        leading=8.8,
        textColor=colors.white,
    )

    def p(value: Any, style: Any = body) -> Paragraph:
        import html

        return Paragraph(html.escape(_text(value, 650)), style)

    rows = [[p("Control", header), p("Current state", header), p("Evidence-bound repair", header), p("Exit proof", header)]]
    for item in plan[:7]:
        blockers = " ".join(item.get("retained_blockers") or [])
        action = item["recommended_action"]
        if blockers:
            action += " Retained blockers: " + blockers
        rows.append([p(item["label"]), p(item["current_state"]), p(action), p(item["exit_criteria"])])

    table = Table(rows, colWidths=[1.35 * inch, 1.35 * inch, 2.55 * inch, 2.25 * inch], repeatRows=1)
    commands = [
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#075985")),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    for row in range(1, len(rows)):
        commands.append(("BACKGROUND", (0, row), (-1, row), colors.HexColor("#f8fafc" if row % 2 else "#eef6fb")))
    table.setStyle(TableStyle(commands))

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.42 * inch,
        leftMargin=0.42 * inch,
        topMargin=0.48 * inch,
        bottomMargin=0.58 * inch,
        title="NICO Verified Green Remediation Plan",
        author="NICO",
        invariant=1,
    )
    doc.build(
        [
            p("Verified Green Remediation Plan", title),
            p(
                "These controls are not made green by presentation changes. Each requires measured technical performance, verified evidence assurance, "
                "and a GREEN risk disposition on the same immutable snapshot. Human delivery approval remains separate.",
                subtitle,
            ),
            Spacer(1, 0.04 * inch),
            table,
            Spacer(1, 0.1 * inch),
            p("Threshold policy: no score threshold was lowered; missing, failed, timed-out, unavailable, or untriaged evidence is never counted as clean."),
        ]
    )
    return buffer.getvalue()


def _install_pdf_plan() -> dict[str, Any]:
    from nico import express_pdf_score_assurance_v1 as pdf_score
    from nico import express_score_assurance_export_v1 as export

    current: Callable[[bytes, dict[str, Any]], bytes] = pdf_score.replace_score_assurance_pages
    if getattr(current, _PDF_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    @wraps(current)
    def replace_pages(pdf_bytes: bytes, result: dict[str, Any]) -> bytes:
        rendered = current(pdf_bytes, result)
        records = export._records(result)
        plan = _improvement_plan(records)
        if not plan:
            return rendered
        reader = PdfReader(io.BytesIO(rendered))
        existing = "\n".join(page.extract_text() or "" for page in reader.pages)
        if "Verified Green Remediation Plan" in existing:
            return rendered
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        for page in PdfReader(io.BytesIO(_plan_pdf(result, plan))).pages:
            writer.add_page(page)
        output = io.BytesIO()
        writer.write(output)
        result["express_verified_green_remediation"] = {
            "status": "complete",
            "version": VERSION,
            "controls": plan,
            "control_count": len(plan),
            "page_appended": True,
            "thresholds_lowered": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        return output.getvalue()

    setattr(replace_pages, _PDF_MARKER, True)
    setattr(replace_pages, "_nico_previous", current)
    pdf_score.replace_score_assurance_pages = replace_pages
    return {
        "status": "installed",
        "version": VERSION,
        "polished_remediation_page": True,
        "yellow_controls_actionable": True,
    }


def _install_scanner_timeout_policy() -> dict[str, Any]:
    from nico import scanner_tool_runners as runners
    from nico import scanner_worker_orchestration as orchestration

    updated = []
    specs = []
    for spec in runners.TOOL_SPECS:
        timeout = spec.timeout_seconds
        output_limit = spec.max_output_chars
        if spec.name in {"gitleaks", "trufflehog"}:
            timeout = max(timeout, 600)
            output_limit = max(output_limit, 120_000)
        elif spec.name == "semgrep":
            timeout = max(timeout, 360)
        next_spec = replace(spec, timeout_seconds=timeout, max_output_chars=output_limit)
        specs.append(next_spec)
        if next_spec != spec:
            updated.append(spec.name)
    new_specs = tuple(specs)
    runners.TOOL_SPECS = new_specs
    orchestration.TOOL_SPECS = new_specs
    defaults = runners.run_scanner_tools.__defaults__
    if defaults:
        runners.run_scanner_tools.__defaults__ = (new_specs, *defaults[1:])
    return {
        "status": "installed",
        "updated_tools": updated,
        "history_scanner_timeout_seconds": 600,
        "semgrep_timeout_seconds": 360,
        "full_history_requirement_preserved": True,
    }


def install_accurate_green_release_v2() -> dict[str, Any]:
    export = _install_export_compat()
    index = _install_index_compat()
    pdf = _install_pdf_plan()
    scanner = _install_scanner_timeout_policy()
    return {
        "status": "installed",
        "version": VERSION,
        "export": export,
        "index": index,
        "pdf": pdf,
        "scanner": scanner,
        "verified_green_requires_score_80": True,
        "verified_green_requires_verified_assurance": True,
        "verified_green_requires_green_disposition": True,
        "thresholds_lowered": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_accurate_green_release_v2"]
