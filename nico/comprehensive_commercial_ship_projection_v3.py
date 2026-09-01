from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from functools import wraps
from typing import Any, Mapping

from pypdf import PdfReader

from nico import comprehensive_commercial_ship_projection_v1 as v1
from nico import comprehensive_pdf_reflow_v1 as pdf_reflow
from nico.comprehensive_commercial_ship_projection_v2 import (
    _deployment_metric_order_independent,
)

VERSION = "nico.comprehensive_commercial_ship_projection.v3.9"
_STAGE_MARKER = "__nico_commercial_ship_stage_projection_v3__"
_NAV_MARKER = "__nico_commercial_ship_navigation_projection_v3__"
_LOCALE_MARKER = "__nico_commercial_ship_locale_projection_v3__"
_RESPONSE_MARKER = "__nico_commercial_ship_pdf_response_v3__"
_FROZEN_SOURCE_MARKER = "__nico_commercial_ship_frozen_source_v3__"
_REPORT_MARKER = "__nico_commercial_ship_report_v3__"
_RENDER_TARGET_MARKER = "__nico_commercial_ship_render_target_v3__"
_INSTALLED = False
_VISIBLE_MANIFEST_TYPES = frozenset(
    {
        "findings_csv",
        "evidence_csv",
        "candidate_register_json",
        "remediation_backlog_json",
        "markdown_report",
        "html_report",
    }
)
_LEGACY_GITHUB_TEXT_SAMPLE = (
    "No eligible source files were present in the authorized GitHub text-file sample."
)
_PROVIDER_NEUTRAL_TEXT_SAMPLE = (
    "No eligible source files were present in the authorized repository text-file sample."
)

# Correct the helper before any stage projection is evaluated.
v1._is_deployment_metric = _deployment_metric_order_independent
# The Spanish renderer localizes the running page header from AUTOMATED DRAFT to
# BORRADOR AUTOMATIZADO. The sparse-page reflow is locale-neutral, so recognize both
# approved source-language header forms without changing any rendered report copy.
pdf_reflow._HEADER = re.compile(
    r"^NICO\s+Comprehensive\b.*(?:AUTOMATED\s+DRAFT|BORRADOR\s+AUTOMATIZADO)",
    re.I,
)


def project_canonical_for_client_presentation(
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    projected = v1.project_canonical_for_client_presentation(canonical)

    def neutralize(value: Any) -> Any:
        if isinstance(value, Mapping):
            return {str(key): neutralize(item) for key, item in value.items()}
        if isinstance(value, list):
            return [neutralize(item) for item in value]
        if isinstance(value, tuple):
            return tuple(neutralize(item) for item in value)
        if value == _LEGACY_GITHUB_TEXT_SAMPLE:
            return _PROVIDER_NEUTRAL_TEXT_SAMPLE
        return value

    projected = neutralize(projected)
    summary = projected.get("review_candidate_summary")
    stages = projected.get("stage_summaries")
    if isinstance(summary, Mapping) and isinstance(stages, list):
        stage_ids = {
            str(stage.get("stage_id") or "")
            for stage in stages
            if isinstance(stage, Mapping)
        }
        if "review_required_candidate_register" not in stage_ids:
            from nico import v2_premium_report_renderer as renderer
            from nico.comprehensive_report_content_render_v66 import _candidate_stage

            candidate = _candidate_stage(projected, renderer)
            if candidate:
                insert_at = next(
                    (
                        index
                        for index, stage in enumerate(stages)
                        if isinstance(stage, Mapping)
                        and str(stage.get("stage_id") or "")
                        in {"ci_cd_operational_readiness", "client_evidence_summary"}
                    ),
                    len(stages),
                )
                stages.insert(insert_at, candidate)
    return projected


def _contains_exact_presentation_literal(value: Any, literal: str) -> bool:
    if isinstance(value, Mapping):
        return any(
            _contains_exact_presentation_literal(item, literal)
            for item in value.values()
        )
    if isinstance(value, (list, tuple)):
        return any(
            _contains_exact_presentation_literal(item, literal)
            for item in value
        )
    return value == literal


def compact_sparse_limitation_pages(pdf_bytes: bytes) -> tuple[bytes, dict[str, Any]]:
    """Run both bounded sparse-page compactors before final navigation is rebuilt."""

    limitation_pdf, limitation_manifest = v1.compact_sparse_limitation_pages(pdf_bytes)
    reflowed_pdf, reflow_manifest = pdf_reflow.compact_sparse_stage_pages(limitation_pdf)
    original_pages = int(limitation_manifest.get("original_pages") or 0)
    final_pages = int(reflow_manifest.get("final_pages") or limitation_manifest.get("final_pages") or original_pages)
    pages_removed = max(0, original_pages - final_pages)
    return reflowed_pdf, {
        "status": "compacted" if pages_removed else "unchanged",
        "original_pages": original_pages,
        "final_pages": final_pages,
        "compacted_groups": int(limitation_manifest.get("compacted_groups") or 0)
        + int(reflow_manifest.get("compacted_groups") or 0),
        "pages_removed": pages_removed,
        "truth_preserved": limitation_manifest.get("truth_preserved") is True
        and reflow_manifest.get("truth_preserved") is True,
        "canonical_truth_mutated": False,
        "limitation_compaction": limitation_manifest,
        "sparse_stage_reflow": reflow_manifest,
    }


def _bind_final_pdf_layout() -> dict[str, Any]:
    """Bind the approved PDF geometry before any client artifact is rendered."""

    from nico.comprehensive_pdf_layout_polish_v1 import (
        install_comprehensive_pdf_layout_polish_v1,
    )

    layout = install_comprehensive_pdf_layout_polish_v1()
    if layout.get("toc_rows_per_page") != 35:
        raise ValueError("localized report 35-row TOC layout was not installed")
    if float(layout.get("review_small_font_size") or 0) < 6.75:
        raise ValueError("localized report readable review typography was not installed")
    return layout


def _repository_delivery_stage(
    canonical: Mapping[str, Any],
) -> Mapping[str, Any] | None:
    """Return the retained provider-access stage without changing canonical truth."""

    assessment = (
        canonical.get("assessment")
        if isinstance(canonical.get("assessment"), Mapping)
        else {}
    )
    candidates = canonical.get("stage_summaries")
    if not isinstance(candidates, list):
        candidates = assessment.get("stage_summaries")
    for stage in candidates or []:
        if not isinstance(stage, Mapping):
            continue
        stage_id = str(stage.get("stage_id") or "").strip()
        title = " ".join(str(stage.get("title") or "").split()).casefold()
        if stage_id == "repository_and_delivery_evidence" or title in {
            "repository and delivery evidence",
            "evidencia del repositorio y de entrega",
        }:
            return stage
    return None


def _render_repository_delivery_supplement(
    canonical: Mapping[str, Any],
    stage: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    """Render the complete retained provider contract when compact assembly omitted it."""

    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    if spanish:
        from nico.comprehensive_spanish_canonical_report_v87 import (
            _translate_presentation_field,
        )

        def localized(value: Any, key: str) -> str:
            return str(_translate_presentation_field(str(value or ""), key))

    else:

        def localized(value: Any, key: str) -> str:
            del key
            return str(value or "")

    title = (
        "Evidencia del repositorio y de entrega"
        if spanish
        else "Repository and Delivery Evidence"
    )
    boundary = (
        "BORRADOR AUTOMATIZADO | APROBACIÓN HUMANA PENDIENTE | ENTREGA AL CLIENTE BLOQUEADA"
        if spanish
        else "AUTOMATED DRAFT | PENDING HUMAN APPROVAL | CLIENT DELIVERY BLOCKED"
    )
    status = localized(stage.get("status") or "complete", "status").upper()
    summary = localized(stage.get("summary") or "", "summary")
    evidence = [
        localized(item, "evidence")
        for item in stage.get("evidence") or []
        if str(item or "").strip()
    ]
    limitations = [
        localized(item, "unavailable")
        for field in ("unavailable", "limitations")
        for item in stage.get(field) or []
        if str(item or "").strip()
    ]

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "NICOProviderEvidenceHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=17,
        leading=20,
        textColor=colors.HexColor("#0f172a"),
        spaceAfter=7,
        keepWithNext=True,
    )
    subheading = ParagraphStyle(
        "NICOProviderEvidenceSubheading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=colors.HexColor("#075985"),
        spaceBefore=5,
        spaceAfter=3,
        keepWithNext=True,
    )
    body = ParagraphStyle(
        "NICOProviderEvidenceBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=7.2,
        leading=8.8,
        textColor=colors.HexColor("#334155"),
        spaceAfter=2,
    )
    bullet = ParagraphStyle(
        "NICOProviderEvidenceBullet",
        parent=body,
        leftIndent=10,
        firstLineIndent=-7,
    )
    warning = ParagraphStyle(
        "NICOProviderEvidenceBoundary",
        parent=body,
        fontName="Helvetica-Bold",
        textColor=colors.HexColor("#92400e"),
        backColor=colors.HexColor("#fef3c7"),
        borderColor=colors.HexColor("#f59e0b"),
        borderWidth=0.6,
        borderPadding=5,
        spaceAfter=5,
    )

    def paragraph(value: Any, style: ParagraphStyle) -> Paragraph:
        return Paragraph(html.escape(str(value or "")), style)

    def footer(canvas: Any, document: Any) -> None:
        identity = (
            canonical.get("identity")
            if isinstance(canonical.get("identity"), Mapping)
            else {}
        )
        canvas.saveState()
        canvas.setFont("Helvetica", 6.8)
        canvas.setFillColor(colors.HexColor("#64748b"))
        canvas.drawString(
            0.45 * inch,
            0.30 * inch,
            (
                "NICO | evidencia de acceso del proveedor | borrador automatizado"
                if spanish
                else "NICO | provider-access evidence | automated draft"
            ),
        )
        canvas.drawRightString(
            8.05 * inch,
            0.30 * inch,
            f"{str(identity.get('run_id') or '')} · {document.page}",
        )
        canvas.restoreState()

    story: list[Any] = [
        paragraph(title, heading),
        paragraph(boundary, warning),
        paragraph(f"{status} · {summary}" if summary else status, body),
        paragraph("Evidencia conservada" if spanish else "Retained Evidence", subheading),
    ]
    story.extend(paragraph(f"- {item}", bullet) for item in evidence)
    if limitations:
        story.extend(
            (
                Spacer(1, 0.04 * inch),
                paragraph(
                    "Limitaciones de evidencia" if spanish else "Evidence Limitations",
                    subheading,
                ),
            )
        )
        story.extend(paragraph(f"- {item}", bullet) for item in limitations)

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.45 * inch,
        rightMargin=0.45 * inch,
        topMargin=0.42 * inch,
        bottomMargin=0.48 * inch,
        invariant=1,
        title="NICO Repository and Delivery Evidence",
        author="NICO",
    )
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    rendered = buffer.getvalue()

    extracted = " ".join(
        " ".join((page.extract_text() or "").split())
        for page in PdfReader(io.BytesIO(rendered)).pages
    ).casefold()
    required = [title, summary, *evidence, *limitations]
    missing = [
        item
        for item in required
        if item and " ".join(str(item).split()).casefold() not in extracted
    ]
    if missing:
        raise ValueError(
            "repository delivery evidence recovery omitted retained presentation text"
        )
    return rendered


def _ensure_repository_delivery_section(
    pdf_bytes: bytes,
    canonical: Mapping[str, Any],
) -> tuple[bytes, bool]:
    """Recover one missing provider section from the same immutable canonical run."""

    from pypdf import PdfWriter
    from nico import comprehensive_semantic_navigation_v1 as semantic

    reader = PdfReader(io.BytesIO(pdf_bytes))
    source_pages = semantic._remove_existing_toc(reader)
    source_buffer = io.BytesIO()
    source_writer = PdfWriter()
    for page in source_pages:
        source_writer.add_page(page)
    source_writer.write(source_buffer)
    source_reader = PdfReader(io.BytesIO(source_buffer.getvalue()))
    records, spanish = semantic.semantic_entry_records(source_reader)
    if any(
        str(record.get("section_id") or "") == "repository_delivery_evidence"
        for record in records
    ):
        return pdf_bytes, False

    stage = _repository_delivery_stage(canonical)
    if stage is None:
        return pdf_bytes, False
    supplement = PdfReader(
        io.BytesIO(
            _render_repository_delivery_supplement(
                canonical,
                stage,
                spanish=spanish,
            )
        )
    )
    record_by_id = {
        str(record.get("section_id") or ""): int(record["source_page_index"])
        for record in records
    }
    insert_at = next(
        (
            record_by_id[section_id]
            for section_id in (
                "evidence_reconciliation_scoring",
                "executive_risk_register_decision_briefing",
                "authorization_scope",
                "human_review_acceptance_gate",
            )
            if section_id in record_by_id
        ),
        len(source_reader.pages),
    )

    writer = PdfWriter()
    for index, page in enumerate(source_reader.pages):
        if index == insert_at:
            for supplement_page in supplement.pages:
                writer.add_page(supplement_page)
        writer.add_page(page)
    if insert_at >= len(source_reader.pages):
        for supplement_page in supplement.pages:
            writer.add_page(supplement_page)
    output = io.BytesIO()
    writer.write(output)
    recovered = output.getvalue()
    recovered_records, _ = semantic.semantic_entry_records(
        PdfReader(io.BytesIO(recovered))
    )
    if not any(
        str(record.get("section_id") or "") == "repository_delivery_evidence"
        for record in recovered_records
    ):
        raise ValueError("repository delivery evidence recovery was not navigable")
    return recovered, True


def _finalize_artifact_navigation(
    artifacts: Mapping[str, Any],
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    """Rebuild navigation and the four-phase surface after final compaction."""

    output = dict(artifacts)
    encoded = output.get("pdf_base64")
    if not isinstance(encoded, str) or not encoded:
        return output
    try:
        pdf_bytes = base64.b64decode(encoded, validate=True)
    except Exception as exc:
        raise ValueError("localized report contained an invalid PDF payload") from exc
    from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
    from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline

    # The locale endpoint runs in the web process, while the original PDF was produced
    # by the isolated final-report worker. Explicitly bind the same 35-row geometry in
    # this process before rebuilding navigation, then restore the four-phase matrix and
    # bookmarks that lived on the removed stale TOC page.
    _bind_final_pdf_layout()
    recovered, repository_section_recovered = _ensure_repository_delivery_section(
        pdf_bytes,
        canonical,
    )
    navigated = semantic_renumber_and_outline(recovered)
    finalized = apply_four_phase_pdf(navigated, canonical)
    final_pages = len(PdfReader(io.BytesIO(finalized)).pages)
    output["pdf_base64"] = base64.b64encode(finalized).decode("ascii")
    output["pdf_sha256"] = hashlib.sha256(finalized).hexdigest()
    output["pdf_page_count"] = final_pages
    output["pdf_page_count_scope"] = "client_facing_same_run_projection"
    pagination = dict(output.get("pagination_compaction") or {})
    pagination["final_navigation_rebuilt_after_compaction"] = True
    pagination["repository_delivery_section_recovered"] = (
        repository_section_recovered
    )
    pagination["final_pages"] = final_pages
    output["pagination_compaction"] = pagination
    return output


def _source_pdf_requires_integrity_reprojection(
    status: Mapping[str, Any],
    report_language: str,
) -> bool:
    """Repair pending frozen drafts with stale visible navigation or scanner truth."""

    if str(report_language or "") not in {"en", "es-MX"}:
        return False
    if status.get("human_review_required") is not True:
        return False
    if status.get("human_review_completed") is not False:
        return False
    if str(status.get("approval_status") or "") != "pending_human_approval":
        return False
    if status.get("client_delivery_allowed") is not False:
        return False

    reports = status.get("reports")
    reports = reports if isinstance(reports, Mapping) else {}
    manifest = reports.get("artifact_manifest")
    manifest = manifest if isinstance(manifest, Mapping) else {}
    artifacts = [
        item
        for item in manifest.get("artifacts") or []
        if isinstance(item, Mapping)
    ]
    visible_digests = {
        str(item.get("artifact_type") or ""): str(item.get("sha256") or "").lower()
        for item in artifacts
        if str(item.get("artifact_type") or "") in _VISIBLE_MANIFEST_TYPES
    }
    manifest_digests_valid = (
        set(visible_digests) == _VISIBLE_MANIFEST_TYPES
        and all(
            re.fullmatch(r"[0-9a-f]{64}", value)
            for value in visible_digests.values()
        )
    )

    try:
        pdf_bytes = base64.b64decode(str(reports.get("pdf_base64") or ""), validate=True)
        if not pdf_bytes.startswith(b"%PDF"):
            return False
        pages = PdfReader(io.BytesIO(pdf_bytes)).pages
        page_texts = [str(page.extract_text() or "") for page in pages]
        visible_text = "".join(
            "".join(text.split())
            for text in page_texts
        )
    except Exception:
        return False
    footer_only_spill = any(
        pdf_reflow._has_standard_header(text)
        and not pdf_reflow._content_lines(text)
        for text in page_texts
    )
    canonical = reports.get("json")
    canonical = canonical if isinstance(canonical, Mapping) else {}
    visible_surfaces = "\n".join(
        (
            "\n".join(page_texts),
            str(reports.get("markdown") or ""),
            str(reports.get("html") or ""),
        )
    )
    legacy_provider_copy = (
        _LEGACY_GITHUB_TEXT_SAMPLE in visible_surfaces
        or _contains_exact_presentation_literal(
            canonical,
            _LEGACY_GITHUB_TEXT_SAMPLE,
        )
    )
    canonical_stage_ids = {
        str(stage.get("stage_id") or "")
        for stage in canonical.get("stage_summaries") or []
        if isinstance(stage, Mapping)
    }
    candidate_summary = canonical.get("review_candidate_summary")
    candidate_summary = (
        candidate_summary if isinstance(candidate_summary, Mapping) else {}
    )

    def zero_count(key: str) -> bool:
        try:
            return int(candidate_summary.get(key) or 0) == 0
        except (TypeError, ValueError):
            return False

    zero_candidate_register_missing = (
        bool(candidate_summary)
        and "review_required_candidate_register" not in canonical_stage_ids
        and all(
            zero_count(key)
            for key in (
                "raw_total",
                "verified_material_total",
                "review_required_total",
            )
        )
    )
    scanner_applicability_mismatch = False
    if canonical:
        from nico.comprehensive_authoritative_scanner_truth_v62 import (
            reconcile_authoritative_scanner_truth,
        )

        reconciled = reconcile_authoritative_scanner_truth(canonical)
        contract = reconciled.get("client_readiness_contract")
        contract = contract if isinstance(contract, Mapping) else {}
        try:
            expected = (
                int(contract["coverage_numerator"]),
                int(contract["coverage_denominator"]),
            )
        except (KeyError, TypeError, ValueError):
            expected = None
        if expected is not None:
            visible_surfaces = "\n".join(
                (
                    "\n".join(page_texts),
                    str(reports.get("markdown") or ""),
                    re.sub(r"<[^>]+>", " ", str(reports.get("html") or "")),
                )
            )
            claims = [
                (int(match.group(1)), int(match.group(2)))
                for pattern in (
                    r"(\d+)\s+of\s+(\d+)\s+applicable\s+scanner\s+executions\s+completed",
                    r"(\d+)\s+de\s+(\d+)\s+ejecuciones\s+de\s+analizadores\s+aplicables\s+completadas",
                )
                for match in re.finditer(pattern, visible_surfaces, flags=re.IGNORECASE)
            ]
            scanner_applicability_mismatch = any(
                claim != expected for claim in claims
            )
    manifest_integrity_mismatch = manifest_digests_valid and any(
        digest not in visible_text for digest in visible_digests.values()
    )
    from nico.comprehensive_report_semantic_manifest_v1 import (
        CANONICAL_TOC_SECTIONS,
    )

    toc_pages = [
        text
        for text in page_texts
        if any(
            marker in text
            for marker in ("Table of Contents", "Tabla de contenido", "Índice")
        )
    ]
    expected_titles = [
        str(
            section[
                "title_es"
                if str(report_language or "").casefold() in {"es-mx", "es_mx"}
                else "title_en"
            ]
        )
        for section in CANONICAL_TOC_SECTIONS
    ]
    normalized_toc = " ".join(" ".join(toc_pages).split()).casefold()
    canonical_toc_incomplete = not toc_pages or any(
        " ".join(title.split()).casefold() not in normalized_toc
        for title in expected_titles
    )
    return (
        footer_only_spill
        or manifest_integrity_mismatch
        or scanner_applicability_mismatch
        or legacy_provider_copy
        or zero_candidate_register_missing
        or canonical_toc_incomplete
    )


def install_comprehensive_commercial_ship_projection_v3() -> dict[str, Any]:
    """Bind presentation-only ship fixes while preserving valid frozen source PDFs."""

    global _INSTALLED
    if _INSTALLED:
        return {
            "status": "already_installed",
            "version": VERSION,
            "bound": True,
            "final_assembled_source_pdf_preserved": True,
            "sparse_stage_reflow_before_final_navigation": True,
            "localized_sparse_stage_reflow_supported": True,
            "final_pdf_layout_bound_before_render": True,
            "pending_legacy_manifest_integrity_reprojection": True,
            "canonical_toc_integrity_reprojection": True,
            "repository_delivery_section_recovery": True,
            "zero_candidate_register_projection_bound": True,
            "canonical_truth_mutated": False,
            "assessment_rerun": False,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    from nico import comprehensive_final_six_client_report_cleanup_v1 as final_six
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from nico import comprehensive_same_run_locale_report_v1 as locale_report
    from nico import comprehensive_spanish_canonical_report_v87 as spanish_report
    from nico.comprehensive_final_six_client_report_cleanup_v1 import (
        install_final_six_client_report_cleanup_v1,
    )
    from nico.comprehensive_manifest_navigation_v1 import (
        install_comprehensive_manifest_navigation_v1,
    )
    from nico.comprehensive_report_content_render_v66 import (
        install_comprehensive_report_content_render_v66,
    )

    # Ensure the existing mature client composer/navigation layers own the final package,
    # then wrap only their presentation seams.
    install_final_six_client_report_cleanup_v1()
    install_comprehensive_manifest_navigation_v1()
    report_content = install_comprehensive_report_content_render_v66()
    if report_content.get("ci_operational_context_bound") is not True:
        raise RuntimeError(
            "Commercial ship projection could not bind the canonical candidate register"
        )

    current_stage = final_six.sanitize_client_report_stage
    if not getattr(current_stage, _STAGE_MARKER, False):

        @wraps(current_stage)
        def stage_projection(stage: Mapping[str, Any]) -> dict[str, Any]:
            return v1._project_stage(current_stage(stage))

        setattr(stage_projection, _STAGE_MARKER, True)
        setattr(stage_projection, "_nico_previous", current_stage)
        final_six.sanitize_client_report_stage = stage_projection

    current_renumber = navigation._renumber_and_outline
    if not getattr(current_renumber, _NAV_MARKER, False):

        @wraps(current_renumber)
        def renumber_after_compaction(pdf: bytes) -> bytes:
            compacted, _manifest = compact_sparse_limitation_pages(pdf)
            # Rebuild physical page labels, TOC, and bookmarks after both bounded
            # sparse-page passes. Canonical assessment truth is never mutated.
            return current_renumber(compacted)

        setattr(renumber_after_compaction, _NAV_MARKER, True)
        setattr(renumber_after_compaction, "_nico_previous", current_renumber)
        navigation._renumber_and_outline = renumber_after_compaction

    # Cross-locale renders derive from a deep-copied canonical snapshot. The source
    # language continues to use the fully assembled frozen artifact produced by the run.
    for attribute in ("_english_artifacts", "_spanish_artifacts"):
        current = getattr(locale_report, attribute)
        if getattr(current, _LOCALE_MARKER, False):
            continue

        @wraps(current)
        def localized_artifacts(
            canonical: Mapping[str, Any],
            _current: Any = current,
        ) -> dict[str, Any]:
            projected = project_canonical_for_client_presentation(canonical)
            _bind_final_pdf_layout()
            artifacts = _current(projected)
            compacted = v1._compact_artifacts(artifacts)
            return _finalize_artifact_navigation(compacted, projected)

        setattr(localized_artifacts, _LOCALE_MARKER, True)
        setattr(localized_artifacts, "_nico_previous", current)
        setattr(locale_report, attribute, localized_artifacts)

    # The current same-run route assembles both locales through ``_render_target``;
    # the older locale helpers above remain compatibility seams. Bind the actual route
    # boundary as well so final compaction cannot reintroduce a stale partial TOC.
    current_render_target = locale_report._render_target
    if not getattr(current_render_target, _RENDER_TARGET_MARKER, False):

        @wraps(current_render_target)
        def localized_render_target(
            canonical: Mapping[str, Any],
            report_language: str,
        ) -> dict[str, Any]:
            # Review companion pages are embedded by ``current_render_target``. Bind
            # the approved renderer first; installing it during navigation cleanup is
            # too late and leaves the legacy 5.35-point worksheet typography in the
            # client PDF.
            _bind_final_pdf_layout()
            projected = project_canonical_for_client_presentation(canonical)
            artifacts = current_render_target(projected, report_language)
            localized_json = artifacts.get("json")
            navigation_truth = (
                localized_json
                if isinstance(localized_json, Mapping)
                else projected
            )
            # ``rebuild_client_artifacts`` already completed both bounded compaction
            # passes. Repeating compaction here can collapse a legitimate localized
            # stage page; this boundary owns navigation only.
            return _finalize_artifact_navigation(artifacts, navigation_truth)

        setattr(localized_render_target, _RENDER_TARGET_MARKER, True)
        setattr(localized_render_target, "_nico_previous", current_render_target)
        locale_report._render_target = localized_render_target

    current_dynamic = getattr(spanish_report, "_localize_dynamic_sentence", None)
    if current_dynamic is not None and not getattr(current_dynamic, _LOCALE_MARKER, False):
        v1._ORIGINAL_SPANISH_DYNAMIC_TRANSLATOR = current_dynamic
        translated = v1._spanish_dynamic_translation
        setattr(translated, _LOCALE_MARKER, True)
        setattr(translated, "_nico_previous", current_dynamic)
        spanish_report._localize_dynamic_sentence = translated

    current_frozen_source = locale_report._frozen_source_pdf_response
    if not getattr(current_frozen_source, _FROZEN_SOURCE_MARKER, False):

        @wraps(current_frozen_source)
        def frozen_source_with_integrity_gate(
            status: Mapping[str, Any],
            report_language: str,
        ) -> Any:
            if _source_pdf_requires_integrity_reprojection(status, report_language):
                return None
            return current_frozen_source(status, report_language)

        setattr(frozen_source_with_integrity_gate, _FROZEN_SOURCE_MARKER, True)
        setattr(frozen_source_with_integrity_gate, "_nico_previous", current_frozen_source)
        locale_report._frozen_source_pdf_response = frozen_source_with_integrity_gate

    current_report = locale_report.build_same_run_locale_report
    if not getattr(current_report, _REPORT_MARKER, False):

        @wraps(current_report)
        def report_with_integrity_gate(
            status: Mapping[str, Any],
            report_language: str,
        ) -> dict[str, Any]:
            if _source_pdf_requires_integrity_reprojection(
                status,
                report_language,
            ):
                source = dict(status)
                source["_nico_force_pending_draft_artifact_regeneration"] = True
            else:
                source = status
            return current_report(source, report_language)

        setattr(report_with_integrity_gate, _REPORT_MARKER, True)
        setattr(report_with_integrity_gate, "_nico_previous", current_report)
        locale_report.build_same_run_locale_report = report_with_integrity_gate

    current_response = locale_report.build_same_run_locale_pdf_response
    if not getattr(current_response, _RESPONSE_MARKER, False):

        @wraps(current_response)
        def pdf_response(status: Mapping[str, Any], report_language: str) -> Any:
            response = current_response(status, report_language)
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

        setattr(pdf_response, _RESPONSE_MARKER, True)
        setattr(pdf_response, "_nico_previous", current_response)
        locale_report.build_same_run_locale_pdf_response = pdf_response

    _INSTALLED = True
    return {
        "status": "installed",
        "version": VERSION,
        "bound": True,
        "presentation_only_projection": True,
        "processing_complete_distinguished_from_evidence_sufficiency": True,
        "deployment_metric_detection_order_independent": True,
        "deployment_outcomes_mutually_exclusive_when_failure_classification_available": True,
        "intermediate_pdf_page_count_scoped": True,
        "sparse_limitation_compaction_before_final_navigation": True,
        "sparse_stage_reflow_before_final_navigation": True,
        "localized_sparse_stage_reflow_supported": True,
        "pending_legacy_manifest_integrity_reprojection": True,
        "canonical_toc_integrity_reprojection": True,
        "repository_delivery_section_recovery": True,
        "zero_candidate_register_projection_bound": True,
        "toc_page_labels_and_bookmarks_rebuilt_after_compaction": True,
        "final_assembled_source_pdf_preserved": True,
        "cross_locale_projection_from_same_canonical_snapshot": True,
        "same_run_render_target_final_navigation_bound": True,
        "final_pdf_layout_bound_before_render": True,
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
    "_ensure_repository_delivery_section",
    "compact_sparse_limitation_pages",
    "install_comprehensive_commercial_ship_projection_v3",
    "project_canonical_for_client_presentation",
]
