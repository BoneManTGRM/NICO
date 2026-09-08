import io
import re

import pytest
from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico.comprehensive_semantic_navigation_v1 import semantic_renumber_and_outline


@pytest.mark.parametrize('spanish', [False, True])
def test_reprojection_replaces_only_generated_page_footer(spanish):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    title = 'NICO Comprehensive | BORRADOR AUTOMATIZADO' if spanish else 'NICO Comprehensive | AUTOMATED DRAFT'
    label = 'Página del documento 1 de 27' if spanish else 'Document page 1 of 27'
    pdf.drawString(48, 744, title)
    # An identical string in report evidence must remain searchable.
    pdf.drawString(48, 600, label)
    pdf.drawCentredString(letter[0] / 2, 16, label)
    pdf.showPage()
    pdf.drawString(48, 744, 'Auditoría de código' if spanish else 'Code Audit')
    pdf.drawString(48, 700, 'Exact source evidence remains unchanged.')
    pdf.showPage()
    pdf.save()
    original = buffer.getvalue()
    first = semantic_renumber_and_outline(original)
    second = semantic_renumber_and_outline(first)
    pages = PdfReader(io.BytesIO(second)).pages
    assert len(pages) == len(PdfReader(io.BytesIO(first)).pages) == 3
    pattern = r'Página del documento \d+ de \d+' if spanish else r'Document page \d+ of \d+'
    for index, page in enumerate(pages, 1):
        text = page.extract_text()
        expected = f'Página del documento {index} de 3' if spanish else f'Document page {index} of 3'
        labels = re.findall(pattern, text)
        assert labels == ([label, expected] if index == 1 else [expected])
    assert 'Exact source evidence remains unchanged.' in pages[-1].extract_text()
    assert original == buffer.getvalue()
