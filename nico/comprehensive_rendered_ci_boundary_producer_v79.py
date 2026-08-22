from __future__ import annotations

import base64
import hashlib
import html
import io
import re
from collections.abc import Mapping, MutableMapping
from copy import deepcopy
from functools import wraps
from typing import Any, Callable

from pypdf import PdfReader, PdfWriter

from nico import comprehensive_ci_boundary_compat_v74 as ci_v74
from nico import comprehensive_report_language_truth_v77 as language_truth

VERSION = "nico.comprehensive-rendered-ci-boundary-producer.v79"
_PRODUCER_MARKER = "_nico_rendered_ci_boundary_producer_v79"

_EN_BOUNDARY_MARKERS = (
    "A. CI/CD configuration maturity:",
    "B. Current operational readiness:",
    "C. Required-check health:",
    "D. Historical workflow outcomes",
)
_ES_BOUNDARY_MARKERS = (
    "A. Madurez de configuración de CI/CD:",
    "B. Preparación operativa actual:",
    "C. Estado de las verificaciones requeridas:",
    "D. Resultados históricos de los flujos de trabajo",
)
_ALL_BOUNDARY_MARKERS = (*_EN_BOUNDARY_MARKERS, *_ES_BOUNDARY_MARKERS)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _normalize_text(value: Any) -> str:
    text = html.unescape(str(value or "")).replace("\u00a0", " ")
    return " ".join(text.split())


def _html_text(value: Any) -> str:
    return _normalize_text(re.sub(r"<[^>]+>", " ", str(value or "")))


def _pdf_text(pdf: bytes) -> str:
    try:
        return _normalize_text(
            "\n".join(
                page.extract_text() or ""
                for page in PdfReader(io.BytesIO(pdf)).pages
            )
        )
    except Exception as exc:
        raise ValueError("rendered CI/CD producer could not read the final PDF") from exc


def _markers(*, spanish: bool) -> tuple[str, ...]:
    return _ES_BOUNDARY_MARKERS if spanish else _EN_BOUNDARY_MARKERS


def _opposite_markers(*, spanish: bool) -> tuple[str, ...]:
    return _EN_BOUNDARY_MARKERS if spanish else _ES_BOUNDARY_MARKERS


def _coverage(text: str, markers: tuple[str, ...]) -> bool:
    normalized = _normalize_text(text)
    return all(_normalize_text(marker) in normalized for marker in markers)


def _resolved_language(
    canonical: Mapping[str, Any],
    *,
    rendered_hint: str = "",
) -> str:
    """Resolve request truth without trusting a synthesized root ``en``."""

    language, source = language_truth._resolve_report_language(canonical)
    normalized = str(language or "").strip()
    if str(source or "").startswith("request:"):
        return "es-MX" if normalized.casefold().startswith("es") else "en"
    if normalized.casefold().startswith("es"):
        return "es-MX"

    # Some upstream canonical normalizers synthesize report_language="en" even
    # when the retained assessment and rendered report are Spanish. Do not let
    # that default force a bilingual or English-only client artifact.
    probe = "\n".join(
        (
            language_truth._language_probe(canonical),
            str(rendered_hint or ""),
        )
    )
    if language_truth._looks_spanish(probe):
        return "es-MX"
    return "en"


def _set_render_language(canonical: MutableMapping[str, Any], language: str) -> None:
    canonical["report_language"] = language

    identity = deepcopy(dict(_mapping(canonical.get("identity"))))
    identity["report_language"] = language
    canonical["identity"] = identity

    assessment = deepcopy(dict(_mapping(canonical.get("assessment"))))
    assessment["report_language"] = language
    canonical["assessment"] = assessment


def _strip_boundary_lines(markdown: str) -> str:
    """Remove stale or duplicated A-D rows before inserting one canonical section."""

    cleaned: list[str] = []
    for raw in str(markdown or "").splitlines():
        candidate = raw.strip()
        if candidate.startswith("- "):
            candidate = candidate[2:].strip()
        if any(candidate.startswith(marker) for marker in _ALL_BOUNDARY_MARKERS):
            continue
        cleaned.append(raw)
    return "\n".join(cleaned).strip() + "\n"


def _render_html(
    markdown: str,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> str:
    identity = _mapping(canonical.get("identity"))
    if spanish:
        from nico.comprehensive_spanish_canonical_report_v87 import (
            render_spanish_html,
        )

        return render_spanish_html(
            markdown,
            "Evaluación Técnica Integral NICO",
        )

    from nico.comprehensive_report_package import _semantic_html

    repository = " ".join(str(identity.get("repository") or "").split()).strip()
    title = f"NICO Comprehensive Technical Assessment — {repository}"
    return _semantic_html(markdown, title)


def _boundary_pdf_page(
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    section = ci_v74.ci_operational_truth_markdown(
        canonical,
        spanish=spanish,
        force=True,
    )
    if not section:
        raise ValueError("rendered CI/CD producer could not build the canonical boundary")

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "RenderedCIBoundaryHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    subheading = ParagraphStyle(
        "RenderedCIBoundarySubheading",
        parent=styles["Heading2"],
        fontName="Helvetica-Bold",
        fontSize=12,
        leading=15,
        textColor=colors.HexColor("#0f172a"),
        spaceBefore=8,
        spaceAfter=6,
    )
    body = ParagraphStyle(
        "RenderedCIBoundaryBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8.5,
        leading=12.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    bullet = ParagraphStyle(
        "RenderedCIBoundaryBullet",
        parent=body,
        leftIndent=12,
        firstLineIndent=-8,
        spaceAfter=7,
    )

    story: list[Any] = [Spacer(1, 0.2 * inch)]
    for raw in section.splitlines():
        line = raw.strip()
        if not line:
            continue
        escaped = html.escape(line)
        if line.startswith("## "):
            story.append(Paragraph(html.escape(line[3:]), heading))
        elif line.startswith("### "):
            story.append(Paragraph(html.escape(line[4:]), subheading))
        elif line.startswith("- "):
            story.append(Paragraph("- " + html.escape(line[2:]), bullet))
        else:
            story.append(Paragraph(escaped, body))

    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=(
            "Preparación operativa y salud histórica de CI/CD"
            if spanish
            else "CI/CD Operational Readiness and Historical Health"
        ),
        author="NICO",
        invariant=1,
    )
    document.build(story)
    return buffer.getvalue()


def _append_boundary_pdf(
    pdf: bytes,
    canonical: Mapping[str, Any],
    *,
    spanish: bool,
) -> tuple[bytes, bool]:
    if not pdf.startswith(b"%PDF"):
        raise ValueError("rendered CI/CD producer requires a valid final PDF")

    existing_text = _pdf_text(pdf)
    desired = _markers(spanish=spanish)
    opposite = _opposite_markers(spanish=spanish)
    if _coverage(existing_text, desired):
        return pdf, False
    if _coverage(existing_text, opposite):
        raise ValueError(
            "final PDF retained a complete opposite-language CI/CD boundary"
        )

    boundary_pdf = _boundary_pdf_page(canonical, spanish=spanish)
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(boundary_pdf)).pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    repaired = output.getvalue()

    if not _coverage(_pdf_text(repaired), desired):
        raise ValueError("final PDF omitted the repaired CI/CD boundary")
    return repaired, True


def _normalize_renderer_input(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Promote the authoritative language before the v2 renderer branches."""

    normalized = deepcopy(dict(package))
    canonical = deepcopy(dict(_mapping(normalized.get("json"))))
    rendered_hint = "\n".join(
        (
            str(normalized.get("markdown") or ""),
            _html_text(normalized.get("html")),
        )
    )
    _set_render_language(
        canonical,
        _resolved_language(canonical, rendered_hint=rendered_hint),
    )
    normalized["json"] = canonical
    return normalized


def repair_rendered_ci_boundary(
    package: Mapping[str, Any],
) -> dict[str, Any]:
    """Repair the actual v2 Markdown, HTML, and PDF before final publication."""

    result = deepcopy(dict(package))
    canonical = deepcopy(dict(_mapping(result.get("json"))))
    rendered_hint = "\n".join(
        (
            str(result.get("markdown") or ""),
            _html_text(result.get("html")),
        )
    )
    language = _resolved_language(canonical, rendered_hint=rendered_hint)
    spanish = language == "es-MX"
    _set_render_language(canonical, language)

    markdown = ci_v74.repair_ci_operational_markdown(
        _strip_boundary_lines(str(result.get("markdown") or "")),
        canonical,
        spanish=spanish,
    )
    rendered_html = _render_html(markdown, canonical, spanish=spanish)

    try:
        pdf = base64.b64decode(str(result.get("pdf_base64") or ""), validate=True)
    except Exception as exc:
        raise ValueError(
            "rendered CI/CD producer requires a decodable final PDF"
        ) from exc
    pdf, appended = _append_boundary_pdf(pdf, canonical, spanish=spanish)
    pdf_base64 = base64.b64encode(pdf).decode("ascii")
    page_count = len(PdfReader(io.BytesIO(pdf)).pages)

    desired = _markers(spanish=spanish)
    opposite = _opposite_markers(spanish=spanish)
    surfaces = {
        "markdown": _normalize_text(markdown),
        "html": _html_text(rendered_html),
        "pdf": _pdf_text(pdf),
    }
    for name, text in surfaces.items():
        if not _coverage(text, desired):
            missing = next(
                marker for marker in desired
                if _normalize_text(marker) not in _normalize_text(text)
            )
            raise ValueError(
                f"rendered CI/CD producer omitted {name} boundary: {missing}"
            )
        if _coverage(text, opposite):
            raise ValueError(
                f"rendered CI/CD producer retained a bilingual conflict in {name}"
            )

    phase17 = deepcopy(dict(_mapping(result.get("phase17_artifact_rebuild"))))
    phase17.update(
        {
            "rendered_ci_boundary_producer_version": VERSION,
            "rendered_ci_boundary_language": language,
            "rendered_ci_boundary_markdown_complete": True,
            "rendered_ci_boundary_html_complete": True,
            "rendered_ci_boundary_pdf_complete": True,
            "rendered_ci_boundary_pdf_page_appended": appended,
            "page_count": page_count,
        }
    )
    renderer_contract = deepcopy(
        dict(_mapping(result.get("premium_report_renderer")))
    )
    renderer_contract.update(
        {
            "rendered_ci_boundary_producer_version": VERSION,
            "four_part_ci_cd_boundary_in_all_formats": True,
            "request_scoped_language_used_by_renderer": True,
            "page_count": page_count,
        }
    )

    result.update(
        {
            "json": canonical,
            "markdown": markdown,
            "html": rendered_html,
            "pdf_base64": pdf_base64,
            "pdf_error": None,
            "pdf_available": True,
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_sha256": hashlib.sha256(
                markdown.encode("utf-8")
            ).hexdigest(),
            "html_sha256": hashlib.sha256(
                rendered_html.encode("utf-8")
            ).hexdigest(),
            "phase17_artifact_rebuild": phase17,
            "premium_report_renderer": renderer_contract,
            "rendered_ci_boundary_producer": {
                "version": VERSION,
                "report_language": language,
                "request_scoped_language_used": True,
                "markdown_complete": True,
                "html_complete": True,
                "pdf_complete": True,
                "pdf_page_appended": appended,
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
    )
    return result


def _chain_has_marker(function: Any) -> bool:
    seen: set[int] = set()
    current = function
    while callable(current) and id(current) not in seen:
        if getattr(current, _PRODUCER_MARKER, False):
            return True
        seen.add(id(current))
        current = getattr(current, "_nico_previous", None)
    return False


def install_comprehensive_rendered_ci_boundary_producer_v79() -> dict[str, Any]:
    """Bind the repair to the direct v2 renderer and every static alias."""

    from nico import v2_premium_evidence_appendix as appendix
    from nico import v2_premium_report_renderer as renderer

    current: Callable[[Mapping[str, Any]], dict[str, Any]] = (
        renderer.rebuild_premium_client_artifacts
    )
    if _chain_has_marker(current):
        wrapped = current
        status = "rebound"
    else:

        @wraps(current)
        def wrapped(package: Mapping[str, Any]) -> dict[str, Any]:
            normalized = _normalize_renderer_input(package)
            return repair_rendered_ci_boundary(current(normalized))

        setattr(wrapped, _PRODUCER_MARKER, True)
        setattr(wrapped, "_nico_previous", current)
        renderer.rebuild_premium_client_artifacts = wrapped
        status = "installed"

    # v2_premium_evidence_appendix imports the renderer by value. Rebind its
    # static alias so the real single-pass production chain cannot bypass v79.
    appendix.rebuild_premium_client_artifacts = wrapped

    bound = (
        renderer.rebuild_premium_client_artifacts is wrapped
        and appendix.rebuild_premium_client_artifacts is wrapped
    )
    return {
        "status": status,
        "version": VERSION,
        "bound": bound,
        "direct_renderer_bound": (
            renderer.rebuild_premium_client_artifacts is wrapped
        ),
        "evidence_appendix_static_alias_bound": (
            appendix.rebuild_premium_client_artifacts is wrapped
        ),
        "request_scoped_language_used_by_renderer": True,
        "markdown_html_pdf_boundary_repaired_before_validation": True,
        "opposite_language_boundary_fails_closed": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "install_comprehensive_rendered_ci_boundary_producer_v79",
    "repair_rendered_ci_boundary",
]
