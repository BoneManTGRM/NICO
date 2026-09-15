"""Client-readable projection of the digest-verified, retained input payload."""
from collections.abc import Mapping
from html import escape
import io

from nico.comprehensive_human_evidence_report_v1 import (
    _FIELD_LABELS, _MODULE_LABEL_ES, _flatten_scalars, _field_path_label,
)
from nico.strategic_human_evidence_v1 import verify_strategic_human_evidence


def is_literal_evidence_page(page) -> bool:
    # Page metadata is assigned by this renderer, never parsed from supplied text.
    marker = page.get('/NICOSuppliedEvidence')
    return getattr(marker, 'value', None) is True


def render_human_evidence_appendix(canonical: Mapping, *, spanish: bool) -> bytes | None:
    package = canonical.get('supplied_human_evidence')
    if not package or not verify_strategic_human_evidence(package):
        return None
    provided = package.get('provided_module_ids') or []
    if not provided:
        return None
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, CondPageBreak
    styles = getSampleStyleSheet()
    body = ParagraphStyle('HumanEvidence', parent=styles['BodyText'], fontSize=9,
                          leading=12, spaceAfter=5, splitLongWords=True)
    def paragraph(value, style=body):
        return Paragraph(escape(str(value)).replace('\n', '<br/>'), style)
    story = [paragraph('Evidencia humana aportada' if spanish else 'Supplied Human Evidence', styles['Title']),
             paragraph('Aportado sin verificar — No establece pruebas de ejecución ni revisión especializada.' if spanish
                       else 'Supplied, unverified — Supplied statements do not establish runtime testing or specialist review.')]
    for module_id in provided:
        module = package['modules'][module_id]
        label = _MODULE_LABEL_ES.get(module_id, module['label']) if spanish else module['label']
        story += [CondPageBreak(100), Spacer(1, 8), paragraph(label, styles['Heading2'])]
        story.append(paragraph(f"{'Módulo' if spanish else 'Module'}: {module_id} · SHA-256: {module['module_sha256']}"))
        story.append(paragraph(('Estado de recopilación: ' if spanish else 'Input collection status: ') + module['status']))
        if module.get('excluded'):
            story.append(paragraph(('Excluido: ' if spanish else 'Excluded: ') + module.get('exclusion_rationale', '')))
        for field in ('reviewer', 'observed_at', 'source_reference'):
            story.append(paragraph(_FIELD_LABELS[field][int(spanish)] + ': ' +
                                   (module.get(field) or ('No proporcionado' if spanish else 'Not supplied'))))
        for path, value in _flatten_scalars(module.get('evidence', {})):
            story.append(paragraph(_field_path_label(path, spanish=spanish) + ': ' + value))
    buffer = io.BytesIO()
    def page_header(canvas, document):
        canvas.saveState()
        canvas.setFont('Helvetica', 8)
        canvas.drawString(40, document.pagesize[1] - 26,
                          ('Evidencia humana aportada | Aportado sin verificar' if spanish else 'Supplied Human Evidence | Supplied, unverified'))
        canvas.restoreState()
    SimpleDocTemplate(buffer, leftMargin=40, rightMargin=40, topMargin=42,
                      bottomMargin=65, invariant=1).build(story, onFirstPage=page_header, onLaterPages=page_header)
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject, BooleanObject
    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
        writer.add_page(page)
        writer.pages[-1][NameObject('/NICOSuppliedEvidence')] = BooleanObject(True)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()
