from __future__ import annotations

import base64
import hashlib
import io
from copy import deepcopy
from typing import Any, Mapping

from nico.v2_premium_report_renderer import VERSION as RENDERER_VERSION
from nico.v2_premium_report_renderer import rebuild_premium_client_artifacts

VERSION = "nico.v2.premium-evidence-appendix.v1"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _spanish(canonical: Mapping[str, Any]) -> bool:
    assessment = canonical.get("assessment") if isinstance(canonical.get("assessment"), Mapping) else {}
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    language = _text(
        canonical.get("report_language")
        or canonical.get("locale")
        or assessment.get("report_language")
        or identity.get("report_language")
        or "en"
    ).casefold()
    return language.startswith("es")


def _appendix_markdown(canonical: Mapping[str, Any], *, spanish: bool) -> str:
    identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
    findings = [item for item in canonical.get("canonical_findings") or [] if isinstance(item, Mapping)]
    scanners = [item for item in canonical.get("scanner_execution_records") or [] if isinstance(item, Mapping)]
    heading = "## Apéndice de evidencia" if spanish else "## Evidence Appendix"
    labels = {
        "repo": "Repositorio" if spanish else "Repository",
        "commit": "Commit exacto" if spanish else "Exact commit",
        "run": "ID de ejecución" if spanish else "Run ID",
        "ledger": "ID del libro de evidencia" if spanish else "Evidence ledger ID",
        "findings": "Hallazgos canónicos" if spanish else "Canonical findings",
        "scanners": "Registros canónicos de analizadores" if spanish else "Canonical scanner records",
    }
    lines = [
        heading,
        "",
        f"- {labels['repo']}: {_text(identity.get('repository'))}",
        f"- {labels['commit']}: {_text(identity.get('commit_sha'))}",
        f"- {labels['run']}: {_text(identity.get('run_id'))}",
        f"- {labels['ledger']}: {_text(identity.get('evidence_ledger_id'))}",
        f"- {labels['findings']}: {len(findings)}",
        f"- {labels['scanners']}: {len(scanners)}",
        "",
        "### Scanner provenance" if not spanish else "### Procedencia de analizadores",
        "",
    ]
    if not scanners:
        lines.append("- No scanner records were retained." if not spanish else "- No se conservaron registros de analizadores.")
    for item in scanners:
        name = _text(item.get("scanner_name") or item.get("tool"))
        state = _text(item.get("state") or item.get("status"))
        verified = "yes" if item.get("verified") is True else "no"
        exact = "yes" if item.get("exact_commit_match") is True else "no"
        artifact = _text(item.get("artifact_hash")) or "missing"
        lines.append(f"- {name}: state={state}; verified={verified}; exact_sha={exact}; artifact_hash={artifact}")
    return "\n".join(lines).strip() + "\n"


def _append_pdf_page(pdf: bytes, canonical: Mapping[str, Any], *, spanish: bool) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import inch
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    appendix = _appendix_markdown(canonical, spanish=spanish)
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    heading = ParagraphStyle(
        "EvidenceAppendixHeading",
        parent=styles["Heading1"],
        fontName="Helvetica-Bold",
        fontSize=20,
        leading=24,
        textColor=colors.HexColor("#075985"),
        spaceAfter=12,
    )
    body = ParagraphStyle(
        "EvidenceAppendixBody",
        parent=styles["BodyText"],
        fontName="Helvetica",
        fontSize=8,
        leading=10.5,
        textColor=colors.HexColor("#334155"),
        spaceAfter=4,
    )
    story: list[Any] = [Spacer(1, .25 * inch)]
    for raw in appendix.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("## "):
            story.append(Paragraph(line[3:], heading))
        elif line.startswith("### "):
            story.append(Paragraph(line[4:], styles["Heading2"]))
        elif line.startswith("- "):
            story.append(Paragraph("• " + line[2:], body))
        else:
            story.append(Paragraph(line, body))
    document = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=.6 * inch,
        rightMargin=.6 * inch,
        topMargin=.6 * inch,
        bottomMargin=.6 * inch,
        invariant=1,
    )
    document.build(story)
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(pdf)).pages:
        writer.add_page(page)
    for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
        writer.add_page(page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def rebuild_premium_client_artifacts_with_appendix(package: Mapping[str, Any]) -> dict[str, Any]:
    result = deepcopy(rebuild_premium_client_artifacts(package))
    canonical = result.get("json") if isinstance(result.get("json"), Mapping) else {}
    spanish = _spanish(canonical)
    appendix = _appendix_markdown(canonical, spanish=spanish)
    markdown = str(result.get("markdown") or "").rstrip() + "\n\n" + appendix

    if spanish:
        from nico.comprehensive_spanish_canonical_report_v87 import (
            render_spanish_html,
        )

        rendered_html = render_spanish_html(
            markdown,
            "Evaluación Técnica Integral NICO",
        )
    else:
        from nico.comprehensive_report_package import _semantic_html

        identity = canonical.get("identity") if isinstance(canonical.get("identity"), Mapping) else {}
        title = f"NICO Comprehensive Technical Assessment — {_text(identity.get('repository'))}"
        rendered_html = _semantic_html(markdown, title)

    pdf = base64.b64decode(str(result.get("pdf_base64") or ""))
    if not pdf.startswith(b"%PDF"):
        raise ValueError("premium evidence appendix requires a valid PDF")
    pdf = _append_pdf_page(pdf, canonical, spanish=spanish)
    page_count = int(result.get("pdf_page_count") or 0) + 1

    phase17 = deepcopy(dict(result.get("phase17_artifact_rebuild") or {}))
    phase17.update({
        "version": VERSION,
        "full_evidence_appendix_rendered": True,
        "appendix_uses_canonical_identity_and_scanner_truth": True,
        "renderer_version": RENDERER_VERSION,
        "page_count": page_count,
    })
    contract = deepcopy(dict(result.get("premium_report_renderer") or {}))
    contract.update({
        "full_evidence_appendix": True,
        "evidence_appendix_in_markdown_html_pdf": True,
        "page_count": page_count,
    })
    result.update({
        "markdown": markdown,
        "html": rendered_html,
        "pdf_base64": base64.b64encode(pdf).decode("ascii"),
        "markdown_sha256": hashlib.sha256(markdown.encode("utf-8")).hexdigest(),
        "html_sha256": hashlib.sha256(rendered_html.encode("utf-8")).hexdigest(),
        "pdf_sha256": hashlib.sha256(pdf).hexdigest(),
        "pdf_page_count": page_count,
        "core_report_page_count": page_count,
        "final_package_page_count": page_count,
        "phase17_artifact_rebuild": phase17,
        "premium_report_renderer": contract,
    })
    return result


__all__ = ["VERSION", "rebuild_premium_client_artifacts_with_appendix"]
