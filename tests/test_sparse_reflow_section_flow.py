"""Lossless page-budget regression for installed sparse prose reflow."""
import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_pdf_reflow_v1 as reflow
from nico.comprehensive_final_worker_pdf_reflow_v1 import install_comprehensive_final_worker_pdf_reflow_v1
from tests.test_client_pdf_compose_v2 import _pdf


def sparse_pages(spanish):
    header = 'NICO Comprehensive | BORRADOR AUTOMATIZADO' if spanish else 'NICO Comprehensive | AUTOMATED DRAFT'
    title = 'Observaciones de arquitectura' if spanish else 'Architecture observations'
    return [[header, f'{title} {section}'] +
            [f'S{section}_ROW_{row:02d} evidencia íntegra conservada.' if spanish
             else f'S{section}_ROW_{row:02d} complete retained evidence.' for row in range(25)]
            for section in range(4)]


@pytest.mark.parametrize('spanish', [False, True])
def test_sparse_prose_flows_without_losing_or_reordering_lines(spanish):
    install_comprehensive_final_worker_pdf_reflow_v1()
    source = _pdf(*sparse_pages(spanish))
    original = PdfReader(io.BytesIO(source))
    assert all(reflow._ordinary_sparse_stage(page.extract_text()) for page in original.pages)
    result, proof = reflow.compact_sparse_stage_pages(source)
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 3
    assert proof['original_pages'] == 4 and proof['pages_removed'] == 1
    assert proof['truth_preserved'] is True
    assert proof['canonical_truth_mutated'] is False
    original_text = reflow._normal(' '.join(line for page in original.pages for line in reflow._content_lines(page.extract_text())))
    result_text = reflow._normal(' '.join(page.extract_text() for page in reader.pages))
    assert result_text == original_text
    # Every section heading stays with its first evidence line.
    for section in range(4):
        title = ('Observaciones de arquitectura' if spanish else 'Architecture observations') + f' {section}'
        containing = next(page.extract_text() for page in reader.pages if title in page.extract_text())
        assert f'S{section}_ROW_00' in containing


@pytest.mark.parametrize('spanish', [False, True])
def test_lossless_reflow_recovers_sixty_page_budget_and_still_rejects_sixty_one(spanish):
    from nico.client_pdf_compose_v2 import compose_compact_client_pdf
    install_comprehensive_final_worker_pdf_reflow_v1()
    protected = [['Executive Decision Brief', f'PRIMARY_{index:02d} retained decision'] for index in range(55)]
    base = _pdf(*protected, *sparse_pages(spanish))
    register, gate = _pdf(['REGISTER_REQUIRED']), _pdf(['GATE_REQUIRED'])
    result = compose_compact_client_pdf(base, register, gate, page_limit=60)
    reader = PdfReader(io.BytesIO(result))
    assert len(reader.pages) == 60
    text = '\n'.join(page.extract_text() for page in reader.pages)
    for index in range(55): assert text.count(f'PRIMARY_{index:02d} ') == 1
    for section in range(4):
        for row in range(25): assert text.count(f'S{section}_ROW_{row:02d} ') == 1
    assert text.count('REGISTER_REQUIRED') == text.count('GATE_REQUIRED') == 1
    # Protected pages must remain byte-for-byte content streams, not prose reflow.
    source = PdfReader(io.BytesIO(base))
    for before, after in zip(source.pages[:55], reader.pages[:55]):
        assert before.get_contents().get_data() == after.get_contents().get_data()
    two_page_gate = _pdf(['GATE_REQUIRED'], ['SECOND_GATE_REQUIRED'])
    with pytest.raises(ValueError, match='cannot preserve every primary and required page'):
        compose_compact_client_pdf(base, register, two_page_gate, page_limit=60)
    # Ordinary reports have no implicit cap; retain the same evidence at 61 pages.
    unlimited = PdfReader(io.BytesIO(compose_compact_client_pdf(base, register, two_page_gate)))
    assert len(unlimited.pages) == 61
    unlimited_text = '\n'.join(page.extract_text() for page in unlimited.pages)
    for index in range(55):
        assert unlimited_text.count(f'PRIMARY_{index:02d} ') == 1
    for section in range(4):
        for row in range(25):
            assert unlimited_text.count(f'S{section}_ROW_{row:02d} ') == 1
    assert unlimited_text.count('REGISTER_REQUIRED') == 1
    assert unlimited_text.count('SECOND_GATE_REQUIRED') == 1
    assert [line.strip() for line in unlimited_text.splitlines()].count('GATE_REQUIRED') == 1
    for before, after in zip(source.pages[:55], unlimited.pages[:55]):
        assert before.get_contents().get_data() == after.get_contents().get_data()


def assert_text_geometry(pdf, path):
    import shutil
    import subprocess
    import xml.etree.ElementTree as ET
    binary = shutil.which('pdftotext')
    if binary is None: pytest.skip('Poppler geometry diagnostic unavailable')
    path.write_bytes(pdf)
    result = subprocess.run([binary, '-bbox-layout', str(path), '-'], capture_output=True, text=True, check=True)
    for page in ET.fromstring(result.stdout).findall('.//{*}page'):
        boxes = []
        for line in page.findall('.//{*}line'):
            box = tuple(float(line.attrib[k]) for k in ('xMin', 'yMin', 'xMax', 'yMax'))
            assert 41 <= box[0] < box[2] <= 571
            assert 35 <= box[1] < box[3] <= 751
            for prior in boxes:
                assert (min(box[2], prior[2]) - max(box[0], prior[0]) <= .1 or
                        min(box[3], prior[3]) - max(box[1], prior[1]) <= .1)
            boxes.append(box)


@pytest.mark.parametrize('spanish', [False, True])
def test_flow_geometry_and_effective_font_size(spanish, tmp_path):
    import math
    install_comprehensive_final_worker_pdf_reflow_v1()
    pdf, _ = reflow.compact_sparse_stage_pages(_pdf(*sparse_pages(spanish)))
    assert_text_geometry(pdf, tmp_path / 'flow.pdf')
    sizes = []
    for page in PdfReader(io.BytesIO(pdf)).pages:
        def visitor(text, cm, tm, font, size):
            if text.strip():
                a,b=tm[0]*cm[0]+tm[1]*cm[2],tm[0]*cm[1]+tm[1]*cm[3]
                c,d=tm[2]*cm[0]+tm[3]*cm[2],tm[2]*cm[1]+tm[3]*cm[3]
                sizes.append(size * min(math.hypot(a,b), math.hypot(c,d)))
        page.extract_text(visitor_text=visitor)
    assert min(sizes) >= 9


def test_geometry_oracle_rejects_overlap(tmp_path):
    from reportlab.pdfgen.canvas import Canvas
    out = io.BytesIO(); canvas = Canvas(out, pagesize=(612,792), invariant=1)
    canvas.drawString(45, 700, 'First independent line')
    canvas.drawString(45, 695, 'Second overlapping line')
    canvas.save()
    with pytest.raises(AssertionError): assert_text_geometry(out.getvalue(), tmp_path / 'bad.pdf')


@pytest.mark.parametrize('spanish', [False, True])
def test_final_navigation_follows_reflowed_physical_pages(spanish):
    from pypdf import PdfWriter
    from nico.comprehensive_report_semantic_manifest_v1 import CANONICAL_TOC_SECTIONS
    from nico import comprehensive_manifest_navigation_v1 as navigation
    from tests.test_comprehensive_pdf_layout_polish_v1 import _semantic_fixture
    install_comprehensive_final_worker_pdf_reflow_v1()
    original = PdfReader(io.BytesIO(_semantic_fixture(spanish=spanish)))
    writer = PdfWriter(); writer.add_page(original.pages[0])
    writer.append(PdfReader(io.BytesIO(_pdf(*sparse_pages(spanish)))), import_outline=False)
    for page in original.pages[1:]: writer.add_page(page)
    out = io.BytesIO(); writer.write(out)
    reader = PdfReader(io.BytesIO(navigation._renumber_and_outline(out.getvalue())))
    destinations = {}
    def visit(items):
        for item in items:
            if isinstance(item, list): visit(item)
            else: destinations[item.title] = reader.get_destination_page_number(item)
    visit(reader.outline)
    for section in CANONICAL_TOC_SECTIONS:
        title = section['title_es' if spanish else 'title_en']
        assert title in reader.pages[destinations[title]].extract_text()
    for index, page in enumerate(reader.pages, 1):
        label = f'Página del documento {index} de {len(reader.pages)}' if spanish else f'Document page {index} of {len(reader.pages)}'
        assert label in page.extract_text()


@pytest.mark.parametrize('kind', ['protected', 'rectangle', 'chart_lines'])
def test_protected_and_structured_page_eligibility_is_unchanged(kind):
    from reportlab.pdfgen.canvas import Canvas
    install_comprehensive_final_worker_pdf_reflow_v1()
    out = io.BytesIO(); canvas = Canvas(out, pagesize=(612,792), invariant=1)
    for section in range(2):
        canvas.drawString(45, 750, 'NICO Comprehensive | AUTOMATED DRAFT')
        canvas.drawString(45, 720, 'Executive Decision Brief' if kind == 'protected' else 'Architecture observations')
        canvas.drawString(45, 690, 'Complete retained evidence remains review required and delivery blocked.')
        if kind == 'rectangle': canvas.rect(45, 600, 400, 60)
        if kind == 'chart_lines':
            path = canvas.beginPath(); path.moveTo(45, 600)
            for i in range(4): path.lineTo(45 + i * 30, 600 + i * 10)
            canvas.drawPath(path)
        canvas.showPage()
    canvas.save(); source = out.getvalue()
    result, proof = reflow.compact_sparse_stage_pages(source)
    assert result == source
    assert proof['pages_removed'] == 0
