"""Production font registration must not detach a short evidence section."""
import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_pdf_reflow_v1 as reflow
from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
from nico.comprehensive_final_worker_pdf_reflow_v1 import install_comprehensive_final_worker_pdf_reflow_v1
from tests.test_sparse_reflow_section_flow import assert_text_geometry


def test_original_heading_evidence_contract_with_production_fonts():
    from tests.test_comprehensive_pdf_layout_polish_v1 import test_sparse_reflow_keeps_velocity_evidence_with_its_heading
    install_comprehensive_pdf_embedded_fonts_v1()
    test_sparse_reflow_keeps_velocity_evidence_with_its_heading()


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('large', [False, True])
def test_evidence_sections_preserve_text_geometry_and_allow_large_sections_to_flow(spanish, large, tmp_path):
    install_comprehensive_pdf_embedded_fonts_v1()
    install_comprehensive_final_worker_pdf_reflow_v1()
    header = 'NICO Comprehensive | ' + ('BORRADOR AUTOMATIZADO' if spanish else 'AUTOMATED DRAFT')
    title = 'Observaciones de entrega' if spanish else 'Delivery observations'
    first = '\n'.join([header, 'Contexto anterior' if spanish else 'Prior context'] +
        [f'CONTEXT_{i:02d} complete retained evidence.' for i in range(28)])
    lines = [title, 'Evidencia' if spanish else 'Evidence'] + [
        f'- ROW_{i:03d} ' + ('Evidencia íntegra.' if spanish else 'Complete evidence.')
        for i in range(40 if large else 5)]
    section = '\n'.join([header] + lines)
    assert reflow._ordinary_sparse_stage(section)
    pdf = reflow._render_group([first, section])
    pages = [p.extract_text() or '' for p in PdfReader(io.BytesIO(pdf)).pages]
    normalized = reflow._normal(' '.join(pages))
    for line in lines:
        assert reflow._normal(line) in normalized
    title_page = next(i for i, text in enumerate(pages) if title in text)
    last_page = next(i for i, text in enumerate(pages) if f'ROW_{39 if large else 4:03d}' in text)
    if large:
        assert last_page > title_page
    else:
        assert last_page == title_page
    assert_text_geometry(pdf, tmp_path / 'evidence.pdf')
