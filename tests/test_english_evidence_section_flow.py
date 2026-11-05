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


def test_score_and_narrative_leadin_stays_with_first_evidence():
    header = 'NICO Comprehensive | AUTOMATED DRAFT'
    leadin = ['Velocity / Complexity', 'GREEN · 87/100',
              'Sustainable delivery capacity uses immutable architecture evidence.',
              'Workflow automation is retained independently of mutable activity.', 'Evidence']
    source = _pdf(
        [header, 'Architecture observations'] + [f'A_{i} retained evidence.' for i in range(12)],
        [header, 'Delivery observations'] + [f'B_{i} retained evidence.' for i in range(18)],
        [header, *leadin] + [f'- VELOCITY_{i} retained evidence.' for i in range(4)],
    )
    result, proof = reflow.compact_sparse_stage_pages(source)
    pages = [page.extract_text() for page in PdfReader(io.BytesIO(result)).pages]
    assert proof['pages_removed'] == 1 and len(pages) == 2
    containing = next(text for text in pages if 'Velocity / Complexity' in text)
    for line in leadin + [f'- VELOCITY_{i} retained evidence.' for i in range(4)]:
        assert line in containing
    before = ' '.join(line for p in PdfReader(io.BytesIO(source)).pages for line in reflow._content_lines(p.extract_text()))
    assert reflow._normal(' '.join(pages)) == reflow._normal(before)


def test_oversized_wrapped_leadin_is_not_made_unbreakable():
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    lines = ['Velocity / Complexity', 'Long retained narrative ' * 100,
             'Evidence', '- First evidence stays retained.']
    style = ParagraphStyle('bounded-test', fontSize=9, leading=12)
    paragraphs = [Paragraph(line, style) for line in lines]
    before = [p.getKeepWithNext() for p in paragraphs]
    assert not reflow._keep_small_evidence_leadin(paragraphs, lines, 516.48, 180)
    assert [p.getKeepWithNext() for p in paragraphs] == before


def test_leadin_grouping_does_not_cross_prior_bullets_or_nonbullet_evidence():
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.platypus import Paragraph
    style = ParagraphStyle('unrelated-test', fontSize=9, leading=12)
    for lines in (['Heading', '- Previous bullet', 'Evidence', '- Next bullet'],
                  ['Heading', 'Evidence', 'Ordinary narrative']):
        paragraphs = [Paragraph(line, style) for line in lines]
        assert not reflow._keep_small_evidence_leadin(paragraphs, lines, 516.48, 180)
        assert not any(p.getKeepWithNext() for p in paragraphs)
