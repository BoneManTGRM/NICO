from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import re
import threading
from copy import deepcopy
from typing import Any, Mapping

from nico import client_finding_remediation_register_v1 as legacy_register_renderer
from nico.client_finding_remediation_register_v5 import (
    build_finding_remediation_register,
    finding_register_markdown,
    normalize_finding_remediation_register,
    render_finding_register_pdf,
    synchronize_canonical_finding_surfaces,
)
from nico.comprehensive_spanish_canonical_report_v87 import (
    render_spanish_html as _spanish_html,
    render_spanish_markdown as _spanish_markdown,
    render_spanish_pdf as _spanish_pdf,
)

VERSION = "nico.comprehensive-spanish-authoritative-publication.v68"
LANGUAGE = "es-MX"
_LEGACY_REGISTER_HEADING = "## Registro detallado de hallazgos"
_AUTHORITATIVE_REGISTER_HEADING = "## Registro de hallazgos y remediación"
_HUMAN_GATE_HEADING = "## Puerta de revisión y aceptación humana"
_PDF_REGISTER_LOCK = threading.RLock()


def _text(value: Any, limit: int = 12000) -> str:
    normalized = " ".join(str(value or "").replace("\x7f", "-").split()).strip()
    return normalized if len(normalized) <= limit else normalized[: limit - 3].rstrip() + "..."


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _set_existing_language_fields(value: Any) -> Any:
    if isinstance(value, Mapping):
        output = {key: _set_existing_language_fields(item) for key, item in value.items()}
        if "report_language" in output:
            output["report_language"] = LANGUAGE
        if "locale" in output:
            output["locale"] = LANGUAGE
        return output
    if isinstance(value, list):
        return [_set_existing_language_fields(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_set_existing_language_fields(item) for item in value)
    return deepcopy(value)


def _propagate_report_language(canonical: Mapping[str, Any]) -> dict[str, Any]:
    output = _set_existing_language_fields(canonical)
    output["report_language"] = LANGUAGE
    output["locale"] = LANGUAGE
    for key in (
        "identity",
        "assessment",
        "report_contract",
        "v2_pipeline_contract",
        "v2_prepublication_contract",
        "artifact_manifest",
    ):
        if isinstance(output.get(key), Mapping):
            section = _mapping(output[key])
            section["report_language"] = LANGUAGE
            section["locale"] = LANGUAGE
            output[key] = section
    return output


def _strip_h2_section(markdown: str, heading: str) -> str:
    lines = str(markdown or "").splitlines()
    output: list[str] = []
    skipping = False
    for line in lines:
        if line.strip() == heading:
            skipping = True
            continue
        if skipping and line.startswith("## "):
            skipping = False
        if not skipping:
            output.append(line)
    return "\n".join(output).strip() + "\n"


def _insert_before_heading(markdown: str, content: str, heading: str) -> str:
    marker = f"\n{heading}\n"
    normalized = str(markdown or "").strip()
    addition = str(content or "").strip()
    if marker in f"\n{normalized}\n":
        index = normalized.find(heading)
        return (
            normalized[:index].rstrip()
            + "\n\n"
            + addition
            + "\n\n"
            + normalized[index:].lstrip()
            + "\n"
        )
    return normalized + "\n\n" + addition + "\n"


def _review_summary(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    summary = canonical.get("review_candidate_summary")
    if not isinstance(summary, Mapping):
        summary = assessment.get("review_candidate_summary")
    return _mapping(summary)


def _ci_context(canonical: Mapping[str, Any]) -> dict[str, Any]:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    context = canonical.get("ci_operational_context")
    if not isinstance(context, Mapping):
        context = assessment.get("ci_operational_context")
    return _mapping(context)


def _integer(value: Any) -> int:
    if isinstance(value, bool):
        return 0
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _publication_truth_markdown(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> str:
    summary = _mapping(register.get("summary"))
    review = _review_summary(canonical)
    ci_context = _ci_context(canonical)
    review_total = _integer(review.get("review_required_total"))
    material_total = _integer(review.get("verified_material_total"))
    lines = [
        "## Verdad de publicación, disposición y evidencia",
        "",
        f"- Idioma autoritativo del informe: {LANGUAGE}.",
        f"- Observaciones brutas: {_integer(summary.get('raw_observation_count'))}.",
        f"- Candidatos normalizados: {_integer(summary.get('normalized_candidate_count'))}.",
        f"- Hallazgos de decisión: {_integer(summary.get('decision_finding_count'))}.",
        "- La disposición humana sigue pendiente y la entrega al cliente permanece bloqueada.",
    ]
    if review_total:
        lines.extend(
            [
                "",
                "## Registro de candidatos que requieren revisión",
                "",
                f"- Candidatos que requieren revisión: {review_total}",
                f"- Hallazgos materiales confirmados: {material_total}",
                "- Efecto en la puntuación: solo aseguramiento mientras la disposición humana siga pendiente; el triaje técnico de NICO está completo.",
            ]
        )
    if ci_context:
        lines.extend(
            [
                "",
                "## Preparación operativa y salud histórica de CI/CD",
                "",
                "La preparación operativa y la salud histórica de CI/CD permanecen separadas de la madurez de configuración.",
            ]
        )
        for key in (
            "successful_workflow_runs",
            "non_successful_workflow_runs",
            "observed_job_success_rate",
            "summary",
        ):
            if key in ci_context and ci_context.get(key) not in (None, "", [], {}):
                lines.append(f"- `{key}`: {_text(ci_context.get(key))}")
    return "\n".join(lines).strip() + "\n"


def _render_complete_register_pdf(register: Mapping[str, Any]) -> bytes:
    code_count = len(
        [item for item in register.get("code_findings") or [] if isinstance(item, Mapping)]
    )
    with _PDF_REGISTER_LOCK:
        previous = legacy_register_renderer.MAX_PDF_CODE_FINDINGS
        legacy_register_renderer.MAX_PDF_CODE_FINDINGS = max(previous, code_count)
        try:
            return render_finding_register_pdf(register, spanish=True)
        finally:
            legacy_register_renderer.MAX_PDF_CODE_FINDINGS = previous


def _truth_supplement_pdf(
    canonical: Mapping[str, Any],
    register: Mapping[str, Any],
) -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "SpanishTruthHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=19,
        leading=23,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "SpanishTruthBody",
        parent=styles["BodyText"],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor("#334155"),
        spaceAfter=6,
    )
    review = _review_summary(canonical)
    ci_context = _ci_context(canonical)
    summary = _mapping(register.get("summary"))
    rows = [
        ["Idioma del informe", LANGUAGE],
        ["Observaciones brutas", str(_integer(summary.get("raw_observation_count")))],
        ["Candidatos normalizados", str(_integer(summary.get("normalized_candidate_count")))],
        ["Hallazgos de decisión", str(_integer(summary.get("decision_finding_count")))],
        ["Candidatos que requieren revisión", str(_integer(review.get("review_required_total")))],
        ["Hallazgos materiales confirmados", str(_integer(review.get("verified_material_total")))],
        ["Disposición humana", "PENDIENTE"],
        ["Entrega al cliente", "BLOQUEADA"],
    ]
    table = Table(
        [[Paragraph(html.escape(cell), body) for cell in row] for row in rows],
        colWidths=[3.35 * inch, 3.45 * inch],
    )
    table.setStyle(
        TableStyle(
            [
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#e0f2fe")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story: list[Any] = [
        Paragraph("Verdad de publicación, disposición y evidencia", heading),
        Paragraph(
            "Esta página conserva los conteos autoritativos y separa la finalización técnica, la garantía de evidencia, la disposición humana y la autorización de entrega.",
            body,
        ),
        Spacer(1, 0.12 * inch),
        table,
    ]
    if ci_context:
        story.extend(
            [
                Spacer(1, 0.2 * inch),
                Paragraph("Preparación operativa y salud histórica de CI/CD", heading),
                Paragraph(
                    "La salud operativa histórica de CI/CD permanece separada de la madurez de configuración y conserva los valores estructurados del paquete canónico.",
                    body,
                ),
                Paragraph(html.escape(json.dumps(ci_context, ensure_ascii=False, sort_keys=True, default=str)), body),
            ]
        )
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=0.65 * inch,
        rightMargin=0.65 * inch,
        topMargin=0.65 * inch,
        bottomMargin=0.65 * inch,
        title="Verdad de publicación NICO",
        author="NICO",
        invariant=1,
    )
    document.build(story)
    return buffer.getvalue()


def _combine_pdfs(base_pdf: bytes, register_pdf: bytes, supplement_pdf: bytes) -> tuple[bytes, int]:
    from pypdf import PdfReader, PdfWriter

    base = PdfReader(io.BytesIO(base_pdf))
    register = PdfReader(io.BytesIO(register_pdf))
    supplement = PdfReader(io.BytesIO(supplement_pdf))
    writer = PdfWriter()
    base_pages = list(base.pages)
    body_pages = base_pages[:-1] if len(base_pages) > 1 else base_pages
    approval_pages = base_pages[-1:] if len(base_pages) > 1 else []
    for page in body_pages:
        writer.add_page(page)
    for page in register.pages:
        writer.add_page(page)
    for page in supplement.pages:
        writer.add_page(page)
    for page in approval_pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue(), len(writer.pages)


def _pdf_text(pdf: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(pdf))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _safe_token(value: Any, fallback: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", _text(value)).strip("-") or fallback


def _finding_records(register: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        item
        for item in [
            *(register.get("code_findings") or []),
            *(register.get("operational_findings") or []),
        ]
        if isinstance(item, Mapping)
    ]


def _validate_complete_spanish_artifacts(
    markdown: str,
    rendered_html: str,
    pdf: bytes,
    register: Mapping[str, Any],
) -> None:
    if _AUTHORITATIVE_REGISTER_HEADING not in markdown:
        raise ValueError("Spanish Markdown omitted the authoritative finding and remediation register")
    if _LEGACY_REGISTER_HEADING in markdown:
        raise ValueError("Spanish Markdown retained the abbreviated legacy finding register")
    if "Registro de hallazgos y remediación" not in rendered_html:
        raise ValueError("Spanish HTML omitted the authoritative finding and remediation register")
    if "lang='es-MX'" not in rendered_html and 'lang="es-MX"' not in rendered_html:
        raise ValueError("Spanish HTML lost the es-MX document language")
    pdf_text = _pdf_text(pdf)
    if "Registro de hallazgos y remediación" not in pdf_text:
        raise ValueError("Spanish PDF omitted the authoritative finding and remediation register")
    lowered_markdown = markdown.casefold()
    lowered_pdf = pdf_text.casefold()
    missing: list[str] = []
    for item in _finding_records(register):
        identifier = _text(item.get("finding_id") or item.get("id"))
        location = _text(item.get("location"))
        if identifier and (
            identifier.casefold() not in lowered_markdown
            or identifier.casefold() not in lowered_pdf
        ):
            missing.append(identifier)
        if location and location.casefold() not in lowered_markdown:
            missing.append(location)
    if missing:
        raise ValueError(
            "Spanish authoritative register omitted retained technical identifiers: "
            + ", ".join(missing[:20])
        )


def finalize_spanish_authoritative_package(result: Mapping[str, Any]) -> dict[str, Any]:
    """Rebuild Spanish client formats from the complete authoritative register.

    English packages never enter this function. Scores, scanner evidence, candidate
    populations, human-disposition state, and delivery blocking are copied from the
    canonical package without recalculation or weakening of publication gates.
    """

    output = _set_existing_language_fields(result)
    package = _mapping(output.get("report_package"))
    if not package:
        return output
    canonical = _propagate_report_language(_mapping(package.get("json")))
    existing_register = canonical.get("client_finding_remediation_register")
    if isinstance(existing_register, Mapping):
        register = normalize_finding_remediation_register(existing_register, canonical)
    else:
        register = build_finding_remediation_register(canonical)
    canonical = synchronize_canonical_finding_surfaces(canonical, register)
    canonical = _propagate_report_language(canonical)
    register = _mapping(canonical.get("client_finding_remediation_register") or register)

    base_canonical = deepcopy(canonical)
    base_canonical["findings_register"] = []
    base_markdown = _strip_h2_section(
        _spanish_markdown(base_canonical),
        _LEGACY_REGISTER_HEADING,
    )
    register_markdown = finding_register_markdown(register, spanish=True)
    truth_markdown = _publication_truth_markdown(canonical, register)
    complete_markdown = _insert_before_heading(
        base_markdown,
        register_markdown.rstrip() + "\n\n" + truth_markdown.rstrip(),
        _HUMAN_GATE_HEADING,
    )
    rendered_html = _spanish_html(
        complete_markdown,
        "Evaluación Técnica Integral NICO",
    )

    base_pdf, _ = _spanish_pdf(base_canonical)
    register_pdf = _render_complete_register_pdf(register)
    supplement_pdf = _truth_supplement_pdf(canonical, register)
    pdf, page_count = _combine_pdfs(base_pdf, register_pdf, supplement_pdf)
    _validate_complete_spanish_artifacts(
        complete_markdown,
        rendered_html,
        pdf,
        register,
    )

    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    safe_repo = _safe_token(identity.get("repository"), "repositorio")
    run_id = _safe_token(identity.get("run_id"), "run")
    stem = f"nico-evaluacion-tecnica-integral-{safe_repo}-{run_id}-es-MX-BORRADOR"
    truth_sha = hashlib.sha256(
        json.dumps(
            canonical,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    quality = _mapping(package.get("report_quality_contract"))
    quality.update(
        {
            "report_language": LANGUAGE,
            "authoritative_spanish_register_complete": True,
            "authoritative_spanish_register_markdown_complete": True,
            "authoritative_spanish_register_html_complete": True,
            "authoritative_spanish_register_pdf_complete": True,
            "legacy_abbreviated_spanish_register_absent": True,
            "technical_identifiers_preserved_verbatim": True,
            "candidate_counts_preserved": True,
            "scanner_evidence_preserved": True,
            "human_disposition_preserved": True,
            "client_delivery_blocking_preserved": True,
        }
    )
    package.update(
        {
            "json": canonical,
            "markdown": complete_markdown,
            "html": rendered_html,
            "pdf_base64": base64.b64encode(pdf).decode("ascii"),
            "pdf_error": None,
            "markdown_filename": f"{stem}.md",
            "html_filename": f"{stem}.html",
            "pdf_filename": f"{stem}.pdf",
            "canonical_truth_sha256": truth_sha,
            "markdown_sha256": hashlib.sha256(complete_markdown.encode("utf-8")).hexdigest(),
            "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
            "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
            "markdown_byte_count": len(complete_markdown.encode("utf-8")),
            "html_byte_count": len(rendered_html.encode("utf-8")),
            "pdf_byte_count": len(pdf),
            "pdf_page_count": page_count,
            "core_report_page_count": page_count,
            "final_package_page_count": page_count,
            "client_finding_remediation_register": register,
            "finding_population": _mapping(register.get("summary")),
            "report_language": LANGUAGE,
            "locale": LANGUAGE,
            "report_quality_contract": quality,
        }
    )
    output.update(
        {
            "report_package": package,
            "report_language": LANGUAGE,
            "locale": LANGUAGE,
            "canonical_truth_sha256": truth_sha,
            "spanish_authoritative_publication_version": VERSION,
        }
    )
    return output


__all__ = [
    "LANGUAGE",
    "VERSION",
    "finalize_spanish_authoritative_package",
]
