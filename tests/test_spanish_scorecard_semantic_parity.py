"""Actual localized replacement must retain the English scorecard's semantics."""
import copy
import io
import re

import pytest
from pypdf import PdfReader
from nico.v2_localized_report_quality_repairs import _spanish_scorecard_page, _validate_spanish_scorecard


@pytest.mark.parametrize('count', [2, 32])
def test_spanish_scorecard_retains_every_summary_status_and_score(count):
    sections = [dict(id=f'control{i}', label=f'CONTROL_{i}', presented_status='gray',
                     presented_score=None, summary=f'SUMMARY_{i}_START ' + ' '.join(f'WORD{i}_{j}' for j in range(35)) + f' SUMMARY_{i}_END')
                for i in range(count)]
    canonical = {'report_language': 'es-MX', 'assessment': {'sections': sections}}
    before = copy.deepcopy(canonical)
    pdf = _spanish_scorecard_page(canonical)
    _validate_spanish_scorecard(pdf, sections, canonical)
    reader = PdfReader(io.BytesIO(pdf))
    text = ' '.join(page.extract_text() for page in reader.pages)
    compact = re.sub(r'\s+', '', text)
    for label in ('Control', 'Estado', 'Puntuación', 'Resumen', 'GRIS', 'SIN PUNTUACIÓN'):
        assert re.sub(r'\s+', '', label) in compact
    for row in sections:
        for word in row['summary'].split():
            assert word in compact
    assert 'Gray' not in text and 'GRAY' not in text
    assert [compact.index(f'SUMMARY_{i}_START') for i in range(count)] == sorted(compact.index(f'SUMMARY_{i}_START') for i in range(count))
    assert canonical == before
    if count > 2:
        assert len(reader.pages) > 1


def test_spanish_scorecard_validation_rejects_missing_summary_and_wrong_score_alias():
    section = dict(label="Control retenido", status="gray", score=95.8, score_value=12,
                   summary="Evidencia completa conservada")
    canonical = {"assessment": {"sections": [section]}}
    pdf = _spanish_scorecard_page(canonical)
    from nico.v2_report_quality_repairs import _scorecard_page
    english_pdf = _scorecard_page(canonical)
    for rendered in (english_pdf, pdf):
        assert "96/100" in PdfReader(io.BytesIO(rendered)).pages[0].extract_text()
    assert section["score"] == 95.8
    _validate_spanish_scorecard(pdf, [section], canonical)
    missing = copy.deepcopy(canonical)
    missing["assessment"]["sections"][0]["summary"] = ""
    with pytest.raises(ValueError, match="omitted canonical presentation"):
        _validate_spanish_scorecard(_spanish_scorecard_page(missing), [section], canonical)


def test_repeated_multpage_replacement_preserves_body_and_has_no_duplicate_rows():
    from pypdf import PdfWriter
    from nico.v2_localized_report_quality_repairs import _replace_spanish_scorecard
    sections = [dict(label=f"CONTROL_{i}", status="gray", score=None,
                     summary=(f"SUMMARY_{i} " * 25)) for i in range(35)]
    canonical = {"assessment": {"sections": sections}}
    pdf = _spanish_scorecard_page(canonical)
    reader = PdfReader(io.BytesIO(pdf))
    assert len(reader.pages) > 1
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.append(reader)
    writer.add_blank_page(width=612, height=792)
    out = io.BytesIO(); writer.write(out)
    first, _, _ = _replace_spanish_scorecard(out.getvalue(), canonical)
    second, _, _ = _replace_spanish_scorecard(first, canonical)
    pages1 = [p.extract_text() for p in PdfReader(io.BytesIO(first)).pages]
    pages2 = [p.extract_text() for p in PdfReader(io.BytesIO(second)).pages]
    assert pages1 == pages2
    assert len(pages1) == len(reader.pages) + 2
    _validate_spanish_scorecard(second, sections, canonical)


def test_unmarked_multpage_scorecard_fails_closed_instead_of_retaining_old_rows():
    from pypdf import PdfWriter
    from nico.v2_localized_report_quality_repairs import _replace_spanish_scorecard
    sections = [dict(label=f"CONTROL_{i}", status="gray", score=None,
                     summary=f"SUMMARY_{i} " * 25) for i in range(35)]
    canonical = {"assessment": {"sections": sections}}
    reader = PdfReader(io.BytesIO(_spanish_scorecard_page(canonical)))
    writer = PdfWriter()
    for page in reader.pages:
        del page["/NICOScorecardPage"]
        del page["/NICOScorecardPages"]
        writer.add_page(page)
    output = io.BytesIO(); writer.write(output)
    with pytest.raises(ValueError, match="continuation ownership unavailable"):
        _replace_spanish_scorecard(output.getvalue(), canonical)


def test_scorecard_localizes_authored_summary_without_mutating_source_literals():
    phrase = "Decision-oriented summary for Architecture & Technical Debt."
    canonical = {"identity": {"customer_name": phrase}, "assessment": {"sections": [
        {"label": "Architecture & Technical Debt", "status": "gray", "score": None, "summary": phrase},
        {"label": "Delivery", "status": "gray", "score": None,
         "summary": "Decision-oriented summary for delivery."},
    ]}}
    before = copy.deepcopy(canonical)
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(_spanish_scorecard_page(canonical))).pages)
    compact = re.sub(r'\s+', '', text)
    # A section summary is authored presentation even when its text coincides
    # with a separate client identity field. Canonical client data stays intact.
    assert re.sub(r'\s+', '', phrase) not in compact
    assert 'Decision-orientedsummaryfordelivery.' not in compact
    assert canonical == before


@pytest.mark.parametrize('status, expected', [
    ('NOT_SCORED', 'SIN PUNTUACIÓN'), ('PENDING', 'PENDIENTE'),
    ('UNKNOWN', 'DESCONOCIDO'), ('EXCEPTIONAL', 'EXCEPCIONAL'),
    ('PROVISIONAL STRONG', 'FUERTE PROVISIONAL'),
    ('PROVISIONAL MODERATE', 'MODERADO PROVISIONAL'),
])
def test_generated_status_cells_are_localized_without_changing_canonical(status, expected):
    canonical = {'assessment': {'sections': [dict(label='CONTROL', status=status, score=None, summary='RESUMEN')]}}
    before = copy.deepcopy(canonical)
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(_spanish_scorecard_page(canonical))).pages)
    assert re.sub(r'\s+', '', expected) in re.sub(r'\s+', '', text)
    assert canonical == before
