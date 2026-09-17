"""Bounded R1/R2 controls; synthetic input is not production acceptance proof."""
from collections import Counter
from copy import deepcopy
import io
import re

import pytest
from pypdf import PdfReader
from reportlab.platypus import SimpleDocTemplate

from nico.comprehensive_human_evidence_appendix import render_human_evidence_appendix
from nico.comprehensive_report_package import _source_markdown, _source_pdf_tables
from nico.phase3_engagement_intake_v1 import validate_and_enrich_intake
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


def _human(objectives=None, constraints=None):
    raw = validate_and_enrich_intake({
        'repository': 'synthetic/report-fixture', 'authorization_confirmed': True,
        'human_evidence': {'stakeholder_context': {'evidence': {
            **({'objectives': objectives} if objectives is not None else {}),
            **({'constraints': constraints} if constraints is not None else {}),
        }}},
    })
    return normalize_strategic_human_evidence(raw['human_evidence'])


def _pdf_text(data):
    return '\n'.join(p.extract_text() or '' for p in PdfReader(io.BytesIO(data)).pages)


@pytest.mark.parametrize('spanish', [False, True])
def test_metadata_only_is_not_presented_as_supplied_objectives(spanish):
    human = _human()
    before = deepcopy(human)
    data = render_human_evidence_appendix({'supplied_human_evidence': human}, spanish=spanish)
    text = ' '.join(_pdf_text(data).split())
    assert ('Contexto de partes interesadas y metadatos del encargo' if spanish else
            'Stakeholder context and engagement metadata') in text
    for label in (('Objetivos: No proporcionado', 'Restricciones: No proporcionado') if spanish else
                  ('Objectives: Not supplied', 'Constraints: Not supplied')):
        assert label in text
    assert ('destino del repositorio' if spanish else 'intake repository target') in text
    assert 'synthetic/report-fixture' in text and 'internal' in text and 'confirmed' in text
    assert human == before  # Preserve the hash-bound raw input, including its module label.


@pytest.mark.parametrize('spanish', [False, True])
def test_genuine_objectives_and_constraints_remain_literal(spanish):
    human = _human(['SYNTHETIC Objective 01: preserve <literal> values.'], ['SYNTHETIC Constraint 01.'])
    before = deepcopy(human)
    text = ' '.join(_pdf_text(render_human_evidence_appendix(
        {'supplied_human_evidence': human}, spanish=spanish)).split())
    assert 'SYNTHETIC Objective 01: preserve <literal> values.' in text
    assert 'SYNTHETIC Constraint 01.' in text
    assert ('Objetivos: No proporcionado' if spanish else 'Objectives: Not supplied') not in text
    assert human == before


def _table(rows):
    return {'structured_tables': [{'title': 'Source interactions and potential boundaries',
        'columns': ['Source', 'Operation', 'Target'], 'rows': rows}]}


@pytest.mark.parametrize('count', [24, 25, 26])
@pytest.mark.parametrize('spanish', [False, True])
def test_complete_table_preserves_rows_cells_and_multiplicity(count, spanish):
    # All row identities and column-specific values are independent of the renderer.
    rows = [[f'ROW{i:03d}_SOURCE', f'ROW{i:03d}_OP', f'ROW{i:03d}_TARGET'] for i in range(count)]
    rows[-2] = list(rows[0])  # A legitimate identical row must appear twice.
    stage = _table(rows)
    before = deepcopy(stage)
    expected = Counter(cell for row in rows for cell in row)
    markdown = '\n'.join(_source_markdown(stage, spanish=spanish))
    buffer = io.BytesIO()
    SimpleDocTemplate(buffer).build(_source_pdf_tables(stage, spanish=spanish, width=430))
    for text in (markdown, _pdf_text(buffer.getvalue())):
        actual = Counter(re.findall(r'ROW\d{3}_(?:SOURCE|OP|TARGET)', text))
        assert actual == expected
    # Text multiplicity alone could pass after swapping cells between rows. Check
    # each visible row's column order using PDF text positions as a separate oracle.
    actual_rows = []
    for page in PdfReader(io.BytesIO(buffer.getvalue())).pages:
        positioned = {}
        def visit(text, cm, tm, font, size):
            value = text.strip()
            if re.fullmatch(r'ROW\d{3}_(?:SOURCE|OP|TARGET)', value):
                x, y = cm[4] + tm[4], cm[5] + tm[5]
                positioned.setdefault(round(y, 2), []).append((x, value))
        page.extract_text(visitor_text=visit)
        actual_rows.extend(tuple(value for _, value in sorted(row)) for row in positioned.values())
    assert Counter(actual_rows) == Counter(tuple(row) for row in rows)
    assert stage == before


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('objectives,constraints', [(None, None), (['OBJECTIVE-TRUE'], None),
                                                  (None, ['CONSTRAINT-TRUE']),
                                                  (['OBJECTIVE-TRUE'], ['CONSTRAINT-TRUE'])])
def test_canonical_and_export_projection_preserve_objective_presence(spanish, objectives, constraints):
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    from nico.comprehensive_report_package import _markdown
    from nico.comprehensive_human_evidence_report_v1 import _localize_retained_stage
    from tests.test_comprehensive_human_evidence_report_v1 import _context
    context = _context('es-MX' if spanish else 'en')
    context['human_evidence'] = _human(objectives, constraints)
    context['prior_stage_results'] = {'authorization_and_scope': {
        'status': 'complete', 'authorization_confirmed': True}}
    before = deepcopy(context)
    canonical = build_canonical_report_source(context)['canonical_report']
    stages = [s for s in canonical['stage_summaries']
              if s['stage_id'].startswith('client_human_evidence_stakeholder_context')]
    markdown = _markdown(canonical['identity'], canonical['assessment'], stages, canonical['generated_at'])
    expected_absent = ('Objetivos: No proporcionado' if spanish else 'Objectives: Not supplied')
    assert (expected_absent in markdown) is (objectives is None)
    expected_absent = ('Restricciones: No proporcionado' if spanish else 'Constraints: Not supplied')
    assert (expected_absent in markdown) is (constraints is None)
    assert 'OBJECTIVE-TRUE' in markdown if objectives else 'OBJECTIVE-TRUE' not in markdown
    assert 'CONSTRAINT-TRUE' in markdown if constraints else 'CONSTRAINT-TRUE' not in markdown
    assert ('Contexto de partes interesadas y metadatos del encargo' if spanish else
            'Stakeholder context and engagement metadata') in markdown
    assert 'explicitly supplied by people' not in ' '.join(s['summary'] for s in stages)
    for stage in stages:
        for line in stage['evidence']:
            if 'synthetic/report-fixture' in line or 'internal' in line or 'confirmed' in line:
                assert line.startswith('Metadatos de ingreso · ' if spanish else 'Intake metadata · ')
    # Repeated selected-locale projection is idempotent; no source mutation or new assessment.
    once = [_localize_retained_stage(s, spanish=spanish) for s in stages]
    twice = [_localize_retained_stage(s, spanish=spanish) for s in once]
    assert once == twice
    assert context == before
    assert canonical['supplied_human_evidence'] == context['human_evidence']


@pytest.mark.parametrize('spanish', [False, True])
def test_reordered_boundary_and_long_cell_remain_readable(spanish, tmp_path):
    tokens = [f'LONGCELL{i:04d}' for i in range(160)]
    rows = [[f'ROW{i:03d}_SOURCE', 'OP', f'ROW{i:03d}_TARGET'] for i in range(26)]
    rows[24][1] = ' '.join(tokens)
    for order, values in [('forward', rows), ('reversed', list(reversed(rows)))]:
        stage = _table(values)
        buffer = io.BytesIO()
        SimpleDocTemplate(buffer).build(_source_pdf_tables(stage, spanish=spanish, width=430))
        data = buffer.getvalue()
        text = _pdf_text(data)
        assert Counter(re.findall(r'LONGCELL\d{4}', text)) == Counter(tokens)
        assert Counter(re.findall(r'ROW\d{3}_(?:SOURCE|TARGET)', text)) == Counter(
            cell for row in rows for cell in [row[0], row[2]])
        (tmp_path / f'table-{order}-{"es-MX" if spanish else "en"}.pdf').write_bytes(data)


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('objectives', [None, ['TRUE RETAINED OBJECTIVE']])
def test_retained_draft_refreshes_stakeholder_classification_only(spanish, objectives):
    from nico.comprehensive_human_evidence_report_v2 import refresh_stakeholder_classification
    from nico.comprehensive_report_package import _markdown
    human = _human(objectives)
    old = {'stage_id': 'client_human_evidence_stakeholder_context', 'status': 'partial',
           'title': 'Client Human Evidence — Stakeholder objectives and constraints',
           'summary': 'These statements were explicitly supplied by people.',
           'evidence': ['Client-supplied data · Authorization Confirmation[1]: confirmed'],
           'findings': [], 'unavailable': []}
    unrelated = {'stage_id': 'functional_qa', 'status': 'not_assessed', 'evidence': ['UNCHANGED QA LIMIT']}
    canonical = {'report_language': 'es-MX' if spanish else 'en', 'report_finality': 'automated_draft',
                 'supplied_human_evidence': human, 'assessment': {'stage_summaries': [old, unrelated]},
                 'stage_summaries': [old, unrelated]}
    before = deepcopy(canonical)
    result = refresh_stakeholder_classification(canonical)
    stage = result['stage_summaries'][0]
    evidence = '\n'.join(stage['evidence'])
    assert ('Objetivos: No proporcionado' if spanish else 'Objectives: Not supplied') in evidence if objectives is None else 'TRUE RETAINED OBJECTIVE' in evidence
    assert ('Contexto de partes interesadas' if spanish else 'Stakeholder context and engagement metadata') in stage['title']
    assert ('Metadatos de ingreso · ' if spanish else 'Intake metadata · ') in evidence
    assert result['stage_summaries'][1] == unrelated
    assert result['assessment']['stage_summaries'] == result['stage_summaries']
    assert result['supplied_human_evidence'] == human
    assert canonical == before
    assert refresh_stakeholder_classification(result) == result
    canonical['client_delivery_allowed'] = True
    assert refresh_stakeholder_classification(canonical) == canonical


def test_canonical_truth_normalizer_preserves_metadata_attribution():
    from nico.comprehensive_client_truth_canonical_v2 import _normalize_stage_truth
    from nico.comprehensive_human_evidence_report_v2 import refresh_stakeholder_classification
    from nico.comprehensive_human_evidence_report_v1 import _STAKEHOLDER_METADATA_SUMMARY
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    stage = {'stage_id': 'client_human_evidence_stakeholder_context', 'status': 'partial',
             'title': 'Client Human Evidence — Stakeholder objectives and constraints',
             'evidence': ['Authorization confirmation: confirmed']}
    raw = {'report_finality': 'automated_draft', 'report_language': 'en',
           'supplied_human_evidence': _human(None), 'stage_summaries': [stage]}
    refreshed = refresh_stakeholder_classification(raw)
    result = _normalize_stage_truth(refreshed)
    assert result['stage_summaries'][0]['summary'] == _STAKEHOLDER_METADATA_SUMMARY[0]
    assert result['stage_summaries'][0]['evidence'] == refreshed['stage_summaries'][0]['evidence']
    assert _translate_presentation(_STAKEHOLDER_METADATA_SUMMARY[0]) == _STAKEHOLDER_METADATA_SUMMARY[1]
