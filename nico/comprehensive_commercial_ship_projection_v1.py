from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from copy import deepcopy
from typing import Any, Iterable, Mapping

VERSION = "nico.comprehensive_commercial_ship_projection.v1"

_PROCESSING_COMPLETE_EVIDENCE_LIMITED = "PROCESSING COMPLETE · EVIDENCE LIMITED"
_PROCESSING_COMPLETE_REQUIREMENTS_MISSING = (
    "PROCESSING COMPLETE · AUTHORITATIVE REQUIREMENTS NOT SUPPLIED"
)
_DEPLOYMENT_PREFIX = "Deployment outcome taxonomy (unscored context)"

_PDF_PAGE_COUNT = re.compile(r"\bpdf_page_count\s*[:=]\s*(?P<count>\d+)\b", re.I)
_COMBINED_DEPLOYMENT = re.compile(
    r"GitHub\s+deployment\s+evidence\s*:\s*observed\s*=\s*(?P<observed>\d+)\s*,\s*"
    r"success\s*=\s*(?P<successful>\d+)\s*,\s*non[- ]success\s*=\s*(?P<remainder>\d+)",
    re.I,
)
_OBSERVED_PATTERNS = (
    re.compile(r"\bobserved[_ .-]*deployments?\s*[:=]\s*(\d+)\b", re.I),
    re.compile(r"\bdeployments?[_ .-]*observed\s*[:=]\s*(\d+)\b", re.I),
)
_SUCCESS_PATTERNS = (
    re.compile(r"\bsuccess(?:ful)?[_ .-]*deployments?\s*[:=]\s*(\d+)\b", re.I),
    re.compile(r"\bdeployments?[_ .-]*success(?:ful)?\s*[:=]\s*(\d+)\b", re.I),
)
_FAILED_PATTERNS = (
    re.compile(r"\bnon[-_ .]*success[_ .-]*deployment[_ .-]*classification\s*[:=]\s*(\d+)\b", re.I),
    re.compile(r"\bfailed[_ .-]*deployments?\s*[:=]\s*(\d+)\b", re.I),
)
_REMAINDER_PATTERNS = (
    re.compile(r"\bnon[-_ .]*success[_ .-]*deployments?\s*[:=]\s*(\d+)\b", re.I),
    re.compile(r"\bunsuccessful[_ .-]*deployments?\s*[:=]\s*(\d+)\b", re.I),
)
_DEPLOYMENT_MARKER = re.compile(
    r"(?:deployment|deployments|despliegue|despliegues).*(?:observed|success|successful|non[- ]success|failed|observad|exitos|fallid|no\s+exitos)",
    re.I,
)

_LIMITATION_MARKERS = (
    "unavailable or limited evidence",
    "evidence limitations",
    "unavailable evidence",
    "evidencia no disponible",
    "evidencia limitada",
    "limitaciones de evidencia",
)
_TARGET_STAGE_MARKERS = (
    "six-month roadmap",
    "roadmap",
    "staffing, sequencing, and cost",
    "staffing",
    "hoja de ruta",
    "personal",
    "dotación",
    "secuenciación",
)
_FOOTER_LINE = re.compile(
    r"^(?:NICO\s+Comprehensive\b.*|(?:Page|Página)\s+\d+\s*$)", re.I
)

_INSTALLED = False
_ORIGINAL_ENGLISH_ARTIFACTS: Any = None
_ORIGINAL_SPANISH_ARTIFACTS: Any = None
_ORIGINAL_BUILD_SAME_RUN: Any = None
_ORIGINAL_PDF_RESPONSE: Any = None
_ORIGINAL_FROZEN_SOURCE: Any = None
_ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR: Any = None


def _normal(value: Any) -> str:
    return " ".join(str(value or "").split())


def _strings(stage: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    summary = stage.get("summary")
    if summary not in (None, ""):
        values.append(str(summary))
    for key in ("evidence", "findings", "unavailable"):
        items = stage.get(key)
        if isinstance(items, (list, tuple)):
            values.extend(str(item) for item in items if item not in (None, ""))
    return values


def _first_match(patterns: Iterable[re.Pattern[str]], values: Iterable[str]) -> int | None:
    for value in values:
        for pattern in patterns:
            match = pattern.search(str(value))
            if match:
                return int(match.group(1))
    return None


def _deployment_counts(values: Iterable[str]) -> dict[str, int | None]:
    source = [str(value) for value in values]
    observed = _first_match(_OBSERVED_PATTERNS, source)
    successful = _first_match(_SUCCESS_PATTERNS, source)
    failed = _first_match(_FAILED_PATTERNS, source)
    remainder = _first_match(_REMAINDER_PATTERNS, source)

    for value in source:
        match = _COMBINED_DEPLOYMENT.search(value)
        if not match:
            continue
        observed = observed if observed is not None else int(match.group("observed"))
        successful = successful if successful is not None else int(match.group("successful"))
        remainder = remainder if remainder is not None else int(match.group("remainder"))

    return {
        "observed": observed,
        "successful": successful,
        "failed": failed,
        "remainder": remainder,
    }


def _deployment_taxonomy(values: Iterable[str]) -> str | None:
    counts = _deployment_counts(values)
    observed = counts["observed"]
    successful = counts["successful"]
    failed = counts["failed"]
    remainder = counts["remainder"]
    if observed is None or successful is None:
        return None

    if failed is not None:
        unresolved = max(0, int(observed) - int(successful) - int(failed))
        return (
            f"{_DEPLOYMENT_PREFIX}: observed={observed}; successful={successful}; "
            f"failed/non-success={failed}; unresolved={unresolved}."
        )

    if remainder is not None:
        return (
            f"{_DEPLOYMENT_PREFIX}: observed={observed}; successful={successful}; "
            "failed/non-success=not separately evidenced; unresolved=not separately evidenced; "
            f"failed-or-unresolved remainder={remainder}."
        )
    return (
        f"{_DEPLOYMENT_PREFIX}: observed={observed}; successful={successful}; "
        "failed/non-success=not separately evidenced; unresolved=not separately evidenced."
    )


def _is_deployment_metric(value: str) -> bool:
    text = str(value or "")
    if _COMBINED_DEPLOYMENT.search(text):
        return True
    if not _DEPLOYMENT_MARKER.search(text):
        return False
    patterns = (*_OBSERVED_PATTERNS, *_SUCCESS_PATTERNS, *_FAILED_PATTERNS, *_REMAINDER_PATTERNS)
    return any(pattern.search(text) for pattern in patterns)


def _scope_page_count(value: str, stage_id: str) -> str:
    match = _PDF_PAGE_COUNT.search(str(value or ""))
    if not match:
        return str(value)
    count = int(match.group("count"))
    if stage_id == "decision_report_generation":
        return (
            f"Core decision-report PDF page count: {count} "
            "(intermediate artifact; not final assembled report length)."
        )
    if stage_id == "final_comprehensive_report_generation":
        return f"Final Comprehensive report-stage PDF page count: {count}."
    return f"PDF page count for stage {stage_id}: {count}."


def _project_stage(stage: Mapping[str, Any]) -> dict[str, Any]:
    projected = deepcopy(dict(stage))
    stage_id = str(projected.get("stage_id") or "").strip()
    raw_status = str(projected.get("status") or "unknown").strip().lower()
    unavailable = projected.get("unavailable")
    unavailable_items = (
        [str(item) for item in unavailable if item not in (None, "")]
        if isinstance(unavailable, (list, tuple))
        else []
    )

    if raw_status == "complete" and unavailable_items:
        if stage_id == "requirements_traceability":
            projected["status"] = _PROCESSING_COMPLETE_REQUIREMENTS_MISSING.lower()
        else:
            projected["status"] = _PROCESSING_COMPLETE_EVIDENCE_LIMITED.lower()

    all_values = _strings(projected)
    taxonomy = _deployment_taxonomy(all_values)

    for key in ("evidence", "findings", "unavailable"):
        items = projected.get(key)
        if not isinstance(items, list):
            continue
        rewritten: list[str] = []
        for item in items:
            text = str(item)
            if taxonomy and _is_deployment_metric(text):
                continue
            rewritten.append(_scope_page_count(text, stage_id))
        projected[key] = rewritten

    summary = str(projected.get("summary") or "")
    if taxonomy and _is_deployment_metric(summary):
        projected["summary"] = taxonomy
    else:
        projected["summary"] = _scope_page_count(summary, stage_id)

    if taxonomy:
        evidence = projected.get("evidence")
        if not isinstance(evidence, list):
            evidence = []
            projected["evidence"] = evidence
        if taxonomy not in evidence and projected.get("summary") != taxonomy:
            evidence.append(taxonomy)

    return projected


def project_canonical_for_client_presentation(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Return a display-only copy; the persisted canonical object is never mutated."""

    projected = deepcopy(dict(canonical))
    stages = projected.get("stage_summaries")
    if isinstance(stages, list):
        projected["stage_summaries"] = [
            _project_stage(item) if isinstance(item, Mapping) else deepcopy(item)
            for item in stages
        ]
    return projected


def _page_text(page: Any) -> str:
    try:
        return str(page.extract_text() or "")
    except Exception:
        return ""


def _meaningful_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in str(text or "").splitlines():
        line = _normal(raw)
        if not line or _FOOTER_LINE.match(line):
            continue
        lines.append(line)
    return lines


def _sparse_target_page(text: str) -> bool:
    normalized = _normal(text).casefold()
    if not normalized or len(normalized) > 1_450:
        return False
    if not any(marker in normalized for marker in _LIMITATION_MARKERS):
        return False
    return any(marker in normalized for marker in _TARGET_STAGE_MARKERS)


def _render_compact_group(texts: list[str], *, first_page_number: int) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "NICOCompactLimitationHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=19,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=7,
        spaceAfter=5,
    )
    body = ParagraphStyle(
        "NICOCompactLimitationBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.4,
        leading=11.2,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    bullet = ParagraphStyle(
        "NICOCompactLimitationBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
    )

    def footer(canvas: Any, doc: Any) -> None:
        canvas.saveState()
        canvas.setFont("Helvetica", 7)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(0.55 * inch, 0.38 * inch, "NICO Comprehensive · limitation evidence")
        canvas.drawRightString(
            7.95 * inch,
            0.38 * inch,
            f"Page {first_page_number + int(doc.page) - 1}",
        )
        canvas.restoreState()

    story: list[Any] = []
    seen: set[str] = set()
    for text in texts:
        for line in _meaningful_lines(text):
            key = line.casefold()
            if key in seen:
                continue
            seen.add(key)
            escaped = html.escape(line)
            lower = line.casefold()
            if any(marker in lower for marker in _TARGET_STAGE_MARKERS) and len(line) < 120:
                story.append(Paragraph(escaped, heading))
            elif line.startswith(("•", "-")):
                story.append(Paragraph("• " + html.escape(line.lstrip("•- ")), bullet))
            else:
                story.append(Paragraph(escaped, body))
        story.append(Spacer(1, 0.08 * inch))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.55 * inch,
        rightMargin=0.55 * inch,
        topMargin=0.55 * inch,
        bottomMargin=0.62 * inch,
        title="NICO Comprehensive limitation evidence",
        author="NICO",
        invariant=1,
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()


def _group_preserves_text(original_texts: list[str], replacement_pdf: bytes) -> bool:
    from pypdf import PdfReader

    replacement = " ".join(
        _normal(_page_text(page)) for page in PdfReader(io.BytesIO(replacement_pdf)).pages
    ).casefold()
    for text in original_texts:
        for line in _meaningful_lines(text):
            normalized = _normal(line).casefold()
            if len(normalized) < 4:
                continue
            if normalized not in replacement:
                return False
    return True


def compact_sparse_limitation_pages(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Compact only consecutive sparse Roadmap/Staffing limitation pages, fail closed."""

    from pypdf import PdfReader, PdfWriter

    if not pdf_bytes.startswith(b"%PDF"):
        raise ValueError("commercial ship projection requires a valid PDF")

    reader = PdfReader(io.BytesIO(pdf_bytes))
    texts = [_page_text(page) for page in reader.pages]
    candidates = [_sparse_target_page(text) for text in texts]
    groups: list[tuple[int, int]] = []
    start: int | None = None
    for index, candidate in enumerate(candidates + [False]):
        if candidate and start is None:
            start = index
        elif not candidate and start is not None:
            if index - start >= 2:
                groups.append((start, index))
            start = None

    if not groups:
        return pdf_bytes, {
            "status": "unchanged",
            "original_pages": len(reader.pages),
            "final_pages": len(reader.pages),
            "compacted_groups": 0,
            "pages_removed": 0,
            "truth_preserved": True,
        }

    replacements: dict[int, tuple[int, bytes]] = {}
    for group_start, group_end in groups:
        original_texts = texts[group_start:group_end]
        replacement = _render_compact_group(
            original_texts,
            first_page_number=group_start + 1,
        )
        replacement_reader = PdfReader(io.BytesIO(replacement))
        original_count = group_end - group_start
        if len(replacement_reader.pages) >= original_count:
            continue
        if not _group_preserves_text(original_texts, replacement):
            continue
        replacements[group_start] = (group_end, replacement)

    if not replacements:
        return pdf_bytes, {
            "status": "unchanged",
            "original_pages": len(reader.pages),
            "final_pages": len(reader.pages),
            "compacted_groups": 0,
            "pages_removed": 0,
            "truth_preserved": True,
        }

    writer = PdfWriter()
    index = 0
    while index < len(reader.pages):
        replacement = replacements.get(index)
        if replacement is None:
            writer.add_page(reader.pages[index])
            index += 1
            continue
        group_end, replacement_pdf = replacement
        replacement_reader = PdfReader(io.BytesIO(replacement_pdf))
        for page in replacement_reader.pages:
            writer.add_page(page)
        index = group_end

    try:
        metadata = reader.metadata
        if metadata:
            writer.add_metadata({str(k): str(v) for k, v in metadata.items() if v is not None})
    except Exception:
        pass

    output = io.BytesIO()
    writer.write(output)
    compacted = output.getvalue()
    final_reader = PdfReader(io.BytesIO(compacted))
    pages_removed = len(reader.pages) - len(final_reader.pages)
    if pages_removed <= 0:
        return pdf_bytes, {
            "status": "unchanged",
            "original_pages": len(reader.pages),
            "final_pages": len(reader.pages),
            "compacted_groups": 0,
            "pages_removed": 0,
            "truth_preserved": True,
        }
    return compacted, {
        "status": "compacted",
        "original_pages": len(reader.pages),
        "final_pages": len(final_reader.pages),
        "compacted_groups": len(replacements),
        "pages_removed": pages_removed,
        "truth_preserved": True,
    }


def _compact_artifacts(artifacts: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(artifacts))
    encoded = output.get("pdf_base64")
    if not isinstance(encoded, str) or not encoded:
        return output
    try:
        pdf_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("localized report contained an invalid PDF payload") from exc
    compacted, manifest = compact_sparse_limitation_pages(pdf_bytes)
    output["pdf_base64"] = base64.b64encode(compacted).decode("ascii")
    output["pdf_sha256"] = hashlib.sha256(compacted).hexdigest()
    output["pdf_page_count"] = int(manifest["final_pages"])
    output["pdf_page_count_scope"] = "client_facing_same_run_projection"
    output["pagination_compaction"] = manifest
    return output


def _spanish_dynamic_translation(value: Any, *args: Any, **kwargs: Any) -> Any:
    text = _normal(value)
    folded = text.casefold()
    if folded == _PROCESSING_COMPLETE_EVIDENCE_LIMITED.casefold():
        return "PROCESAMIENTO COMPLETO · EVIDENCIA LIMITADA"
    if folded == _PROCESSING_COMPLETE_REQUIREMENTS_MISSING.casefold():
        return "PROCESAMIENTO COMPLETO · REQUISITOS AUTORITATIVOS NO PROPORCIONADOS"
    if text.startswith(_DEPLOYMENT_PREFIX + ":"):
        translated = text.replace(
            _DEPLOYMENT_PREFIX,
            "Taxonomía de resultados de despliegue (contexto sin puntuación)",
            1,
        )
        replacements = (
            ("observed=", "observados="),
            ("successful=", "exitosos="),
            ("failed/non-success=", "fallidos/no exitosos="),
            ("unresolved=", "no resueltos="),
            ("failed-or-unresolved remainder=", "remanente fallido-o-no-resuelto="),
            ("not separately evidenced", "sin evidencia separada"),
        )
        for source, target in replacements:
            translated = translated.replace(source, target)
        return translated
    match = re.fullmatch(
        r"Core decision-report PDF page count: (\d+) \(intermediate artifact; not final assembled report length\)\.",
        text,
        flags=re.I,
    )
    if match:
        return (
            f"Recuento de páginas PDF del informe de decisión central: {match.group(1)} "
            "(artefacto intermedio; no es la longitud del informe final ensamblado)."
        )
    match = re.fullmatch(r"Final Comprehensive report-stage PDF page count: (\d+)\.", text, flags=re.I)
    if match:
        return f"Recuento de páginas PDF de la etapa del informe Integral final: {match.group(1)}."
    if _ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR is None:
        return value
    return _ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR(value, *args, **kwargs)


def _projected_english_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    if _ORIGINAL_ENGLISH_ARTIFACTS is None:
        raise RuntimeError("English report renderer was not captured")
    return _compact_artifacts(
        _ORIGINAL_ENGLISH_ARTIFACTS(project_canonical_for_client_presentation(canonical))
    )


def _projected_spanish_artifacts(canonical: Mapping[str, Any]) -> dict[str, Any]:
    if _ORIGINAL_SPANISH_ARTIFACTS is None:
        raise RuntimeError("Spanish report renderer was not captured")
    return _compact_artifacts(
        _ORIGINAL_SPANISH_ARTIFACTS(project_canonical_for_client_presentation(canonical))
    )


def _status_without_frozen_presentation(status: Mapping[str, Any]) -> dict[str, Any]:
    output = deepcopy(dict(status))
    reports = output.get("reports")
    if isinstance(reports, Mapping):
        reports_copy = deepcopy(dict(reports))
        for key in ("markdown", "html", "pdf_base64"):
            reports_copy.pop(key, None)
        output["reports"] = reports_copy
    return output


def _projected_same_run_report(status: Mapping[str, Any], report_language: str) -> dict[str, Any]:
    if _ORIGINAL_BUILD_SAME_RUN is None:
        raise RuntimeError("Same-run report builder was not captured")
    result = _ORIGINAL_BUILD_SAME_RUN(
        _status_without_frozen_presentation(status),
        report_language,
    )
    report = result.get("report") if isinstance(result.get("report"), dict) else None
    if report is not None:
        report["pdf_page_count_scope"] = "client_facing_same_run_projection"
        report["presentation_projection_version"] = VERSION
    result["assessment_rerun"] = False
    result["approval_state_mutated"] = False
    result["delivery_state_mutated"] = False
    result["canonical_truth_preserved"] = True
    return result


def _no_frozen_source_pdf(status: Mapping[str, Any], report_language: str) -> None:
    del status, report_language
    return None


def _projected_pdf_response(status: Mapping[str, Any], report_language: str) -> Any:
    if _ORIGINAL_PDF_RESPONSE is None:
        raise RuntimeError("Same-run PDF response builder was not captured")
    response = _ORIGINAL_PDF_RESPONSE(status, report_language)
    repository = str(status.get("repository") or "").strip()
    commit_sha = str(status.get("commit_sha") or "").strip()
    if repository:
        response.headers["X-NICO-Repository"] = repository
    if commit_sha:
        response.headers["X-NICO-Commit-SHA"] = commit_sha
    response.headers["X-NICO-Artifact-Scope"] = "client-facing-same-run-projection"
    response.headers["X-NICO-Assessment-Rerun"] = "false"
    response.headers["X-NICO-Approval-State-Mutated"] = "false"
    response.headers["X-NICO-Delivery-State-Mutated"] = "false"
    return response


def install_comprehensive_commercial_ship_projection_v1() -> dict[str, Any]:
    """Bind read-only client presentation fixes without changing canonical assessment truth."""

    global _INSTALLED
    global _ORIGINAL_ENGLISH_ARTIFACTS
    global _ORIGINAL_SPANISH_ARTIFACTS
    global _ORIGINAL_BUILD_SAME_RUN
    global _ORIGINAL_PDF_RESPONSE
    global _ORIGINAL_FROZEN_SOURCE
    global _ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR

    from nico import comprehensive_same_run_locale_report_v1 as locale_report
    from nico import comprehensive_spanish_canonical_report_v87 as spanish_report

    if _INSTALLED:
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "canonical_truth_mutated": False,
            "assessment_rerun": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    _ORIGINAL_ENGLISH_ARTIFACTS = locale_report._english_artifacts
    _ORIGINAL_SPANISH_ARTIFACTS = locale_report._spanish_artifacts
    _ORIGINAL_BUILD_SAME_RUN = locale_report.build_same_run_locale_report
    _ORIGINAL_PDF_RESPONSE = locale_report.build_same_run_locale_pdf_response
    _ORIGINAL_FROZEN_SOURCE = locale_report._frozen_source_pdf_response
    _ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR = getattr(
        spanish_report,
        "_localize_dynamic_sentence",
        None,
    )

    locale_report._english_artifacts = _projected_english_artifacts
    locale_report._spanish_artifacts = _projected_spanish_artifacts
    locale_report._frozen_source_pdf_response = _no_frozen_source_pdf
    locale_report.build_same_run_locale_report = _projected_same_run_report
    locale_report.build_same_run_locale_pdf_response = _projected_pdf_response
    if _ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR is not None:
        spanish_report._localize_dynamic_sentence = _spanish_dynamic_translation

    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "presentation_only_projection": True,
        "processing_complete_distinguished_from_evidence_sufficiency": True,
        "deployment_outcomes_mutually_exclusive_when_failure_classification_available": True,
        "intermediate_pdf_page_count_scoped": True,
        "sparse_limitation_pagination_compaction_fail_closed": True,
        "same_run_source_artifact_rerendered_from_persisted_canonical_truth": True,
        "exact_run_repository_commit_locale_headers": True,
        "canonical_truth_mutated": False,
        "assessment_rerun": False,
        "approval_state_mutated": False,
        "delivery_state_mutated": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "compact_sparse_limitation_pages",
    "install_comprehensive_commercial_ship_projection_v1",
    "project_canonical_for_client_presentation",
]
