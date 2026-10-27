"""Compaction must not normalize submitted display literals in either locale."""
import io

import pytest
from reportlab.pdfgen.canvas import Canvas

from nico.comprehensive_pdf_reflow_v1 import _preserves_text


def _pdf(text):
    output = io.BytesIO()
    canvas = Canvas(output, invariant=1)
    canvas.drawString(30, 700, text)
    canvas.save()
    return output.getvalue()


@pytest.mark.parametrize('label', ['Client name', 'Nombre del cliente'])
def test_reflow_rejects_collapsed_display_literal(label):
    original = f'{label}: Compañía  Águila'
    collapsed = original.replace('  ', ' ')
    assert not _preserves_text([original], _pdf(collapsed))
    assert _preserves_text([original], _pdf(original))


def test_ordinary_single_space_reflow_preservation_remains_available():
    assert _preserves_text(['Evidence remains available'], _pdf('Evidence remains available'))
