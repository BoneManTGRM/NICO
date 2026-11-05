"""Scorecard cells must wrap inside columns without truncating bilingual evidence."""
import io
import re
import shutil
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter

import pytest
from pypdf import PdfReader
from reportlab.platypus import SimpleDocTemplate

from nico.comprehensive_report_package import _scorecard_pdf_table

WIDTH = 612 - 2 * .55 * 72 - 12


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('long_row', [False, True])
def test_complete_cells_wrap_with_readable_fonts_and_no_column_overflow(tmp_path, spanish, long_row):
    labels = {'Control': 'Control', 'Status': 'Estado', 'Score': 'Puntuación', 'Summary': 'Resumen',
              'NOT SCORED': 'SIN PUNTUACIÓN'} if spanish else {}
    localize = lambda s: labels.get(s, s)
    summary = ' '.join(f'SUMMARY_{i:04d}' for i in range(600 if long_row else 45))
    status = 'PROVISIONAL STRONG — HUMAN REVIEW REQUIRED; ACCEPTANCE REMAINS PENDING'
    if spanish: status = 'PROVISIONAL SÓLIDO — REVISIÓN HUMANA REQUERIDA; ACEPTACIÓN PENDIENTE'
    label = ('Arquitectura y deuda técnica' if spanish else 'Architecture & Technical Debt') + ' <CONTROL_FULL>'
    rows = [dict(label=label, presented_status=status, presented_score=None, summary=summary),
            dict(label='SECOND_CONTROL', status='SECOND_STATUS', score=93, summary='SECOND_SUMMARY')]
    table = _scorecard_pdf_table(rows, width=WIDTH, localized=localize)
    assert sum(table._colWidths) == pytest.approx(WIDTH)
    expected = [label, status.upper(), localize('NOT SCORED'), summary]
    assert [cell.getPlainText() for cell in table._cellvalues[1]] == expected
    for row in table._cellvalues:
        assert all(cell.style.fontSize >= 9 for cell in row)
    stream = io.BytesIO()
    SimpleDocTemplate(stream, pagesize=(612, 792), leftMargin=.55*72, rightMargin=.55*72,
                      topMargin=.58*72, bottomMargin=.62*72).build([table])
    pdf = stream.getvalue(); reader = PdfReader(io.BytesIO(pdf))
    if long_row: assert len(reader.pages) > 1
    words = Counter(' '.join(page.extract_text() for page in reader.pages).split())
    assert all(words[f'SUMMARY_{i:04d}'] == 1 for i in range(600 if long_row else 45))
    assert words['SECOND_CONTROL'] == words['SECOND_STATUS'] == words['SECOND_SUMMARY'] == 1
    assert words['93/100'] == 1
    compact = re.sub(r'\s+', '', ' '.join(page.extract_text() for page in reader.pages))
    for value in expected[:3]: assert re.sub(r'\s+', '', value) in compact
    path = tmp_path / ('scorecard-es.pdf' if spanish else 'scorecard-en.pdf');path.write_bytes(pdf)
    binary = shutil.which('pdftotext')
    assert binary, 'Poppler is required to verify scorecard column geometry'
    xml = subprocess.run([binary, '-bbox-layout', str(path), '-'], capture_output=True, text=True, check=True).stdout
    left = .55*72+6
    boundaries = [left]
    for width in table._colWidths: boundaries.append(boundaries[-1]+width)
    for page in ET.fromstring(xml).findall('.//{*}page'):
        boxes = []
        for word in page.findall('.//{*}word'):
            x1,y1,x2,y2 = (float(word.attrib[k]) for k in ('xMin','yMin','xMax','yMax'))
            assert any(a+4.5 <= x1 <= x2 <= b-4.5 for a,b in zip(boundaries,boundaries[1:]))
            assert 40 <= y1 < y2 <= 748
            for px1,py1,px2,py2 in boxes:
                assert min(x2,px2)-max(x1,px1) <= .1 or min(y2,py2)-max(y1,py1) <= .1
            boxes.append((x1,y1,x2,y2))


def test_unbroken_identifiers_and_empty_scorecard_are_not_clipped(tmp_path):
    token = 'component_' * 80
    table = _scorecard_pdf_table([dict(label=token,status=token,score=100,summary=token)],
                                width=WIDTH,localized=lambda s:s)
    stream=io.BytesIO();SimpleDocTemplate(stream,leftMargin=40,rightMargin=40).build([table])
    text=''.join(page.extract_text() for page in PdfReader(io.BytesIO(stream.getvalue())).pages)
    assert re.sub(r'\s+','',text).count(token) == 2
    assert re.sub(r'\s+','',text).count(token.upper()) == 1
    empty=_scorecard_pdf_table([],width=WIDTH,localized=lambda s:s)
    assert empty._cellvalues[1][2].getPlainText() == 'NOT SCORED'
