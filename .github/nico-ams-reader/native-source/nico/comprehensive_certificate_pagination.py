"""Number the composed edition without modifying reviewed report pages."""
import io

from pypdf import PdfReader
from reportlab.pdfgen import canvas


def annotate_composed_pagination(writer, *, spanish=False):
    total = len(writer.pages)
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=(float(writer.pages[0].mediabox.width), float(writer.pages[0].mediabox.height)), invariant=1)
    page.setFont('Helvetica', 8)
    page.drawString(54, 42, (f'PDF: {total} páginas físicas, incluido el certificado.' if spanish else
                             f'PDF: {total} physical pages, including the certificate.'))
    page.drawString(54, 30, ('Contenido: páginas del informe; sumar 1 para la página del visor.' if spanish else
                            'Contents: report-page numbers; add 1 for the physical viewer page.'))
    page.save()
    writer.pages[0].merge_page(PdfReader(io.BytesIO(buffer.getvalue())).pages[0])


def project_current_phase_pdf(pdf, canonical, *, authorized):
    from copy import deepcopy
    from nico.comprehensive_four_phase_model_v1 import apply_four_phase_program
    from nico.comprehensive_four_phase_pdf_v1 import apply_four_phase_pdf
    source = deepcopy(canonical)
    source['operator_approval_status'] = 'approved'
    source['client_delivery_allowed'] = authorized
    return apply_four_phase_pdf(pdf, apply_four_phase_program(source))
