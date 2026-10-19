"""Representative reproduction of the English Velocity evidence orphan."""
import io

from pypdf import PdfReader

from nico import comprehensive_pdf_reflow_v1 as reflow
from tests.test_client_pdf_compose_v2 import _pdf


def fixture():
    header = 'NICO Comprehensive | AUTOMATED DRAFT'
    return _pdf(
        [header, 'Architecture observations'] + [f'A_{i} retained evidence.' for i in range(12)],
        [header, 'Delivery observations'] + [f'B_{i} retained evidence.' for i in range(21)],
        [header, 'Velocity / Complexity', 'Evidence'] + [f'- VELOCITY_{i} retained evidence.' for i in range(4)],
    )


def test_heading_evidence_label_and_four_short_bullets_stay_together():
    source = fixture()
    result, proof = reflow.compact_sparse_stage_pages(source)
    pages = [p.extract_text() for p in PdfReader(io.BytesIO(result)).pages]
    assert proof['pages_removed'] == 1 and len(pages) == 2
    containing = next(text for text in pages if 'Velocity / Complexity' in text)
    assert 'Evidence' in containing
    for index in range(4):
        assert f'- VELOCITY_{index} retained evidence.' in containing
    before = ' '.join(line for p in PdfReader(io.BytesIO(source)).pages for line in reflow._content_lines(p.extract_text()))
    assert reflow._normal(' '.join(pages)) == reflow._normal(before)
    assert proof['canonical_truth_mutated'] is False
    assert source == fixture()
