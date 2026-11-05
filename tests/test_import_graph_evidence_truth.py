from copy import deepcopy

import pytest

from nico import typescript_ast_complexity_v1 as collector


def parsed(paths=()):
    return {'status': 'complete', 'parse_failures': [],
            'analyses': [{'path': p, 'status': 'analyzed', 'method': 'typescript_compiler_ast',
                          'parser_diagnostic_count': 0} for p in paths],
            'import_graph': {'nodes': len(paths), 'edges': 0,
                             'strongly_connected_components': len(paths),
                             'cyclic_components': [], 'files_in_cycles': []}}


@pytest.mark.parametrize('payload', [{}, {'status': 'unavailable'},
    {'status': 'complete', 'import_graph': {}}, {'status': 'complete', 'import_graph': None},
    {'status': 'partial', **{'import_graph': parsed()['import_graph']}}])
def test_unknown_graph_is_not_empty(payload):
    value = collector._import_graph_evidence(payload, set())
    assert value['import_graph_status'] == 'unavailable'
    assert all(value[k] is None for k in ('strongly_connected_components', 'cyclic_components', 'files_in_import_cycles'))


@pytest.mark.parametrize('damage', ['diagnostics', 'omitted', 'parse_failures', 'status'])
def test_partial_graph_receives_no_zero_credit(damage):
    payload = parsed(['a.ts'])
    if damage == 'diagnostics': payload['analyses'][0]['parser_diagnostic_count'] = 1
    if damage == 'omitted': payload['analyses'] = []
    if damage == 'parse_failures': payload['parse_failures'] = [{'path': 'a.ts', 'count': 1}]
    if damage == 'status': payload['analyses'][0]['status'] = 'analyzed_with_diagnostics'
    value = collector._import_graph_evidence(payload, {'a.ts'})
    assert value['import_graph_status'] == 'partial'
    assert value['cyclic_components'] is None


@pytest.mark.parametrize('paths', [[], ['a.ts']])
def test_explicit_complete_empty_or_acyclic_graph(paths):
    value = collector._import_graph_evidence(parsed(paths), set(paths))
    assert value['import_graph_status'] == 'measured'
    assert value['strongly_connected_components'] == len(paths)
    assert value['cyclic_components'] == value['files_in_import_cycles'] == []


def test_nonempty_cycle_and_nonmutation():
    payload = parsed(['a.ts', 'b.ts'])
    payload['import_graph'].update(edges=2, strongly_connected_components=1,
                                   cyclic_components=[['a.ts', 'b.ts']], files_in_cycles=['a.ts', 'b.ts'])
    before = deepcopy(payload)
    value = collector._import_graph_evidence(payload, {'a.ts', 'b.ts'})
    assert value['import_graph_status'] == 'measured'
    assert value['files_in_import_cycles'] == ['a.ts', 'b.ts']
    assert payload == before


@pytest.mark.parametrize('field,bad', [('nodes', True), ('nodes', 2), ('edges', -1),
    ('strongly_connected_components', 0), ('cyclic_components', [['foreign.ts', 'a.ts']]),
    ('files_in_cycles', ['a.ts'])])
def test_malformed_or_inconsistent_graph_unavailable(field, bad):
    payload = parsed(['a.ts']); payload['import_graph'][field] = bad
    assert collector._import_graph_evidence(payload, {'a.ts'})['import_graph_status'] == 'unavailable'


def test_actual_collector_unavailable_and_no_js_scope(monkeypatch):
    monkeypatch.setattr(collector, '_run_typescript_ast', lambda files: {'status': 'unavailable'})
    result = collector._build_complexity({'src/a.ts': 'function f() {return 0;}'})
    assert result['strongly_connected_components'] is None
    assert result['import_graph_status'] == 'unavailable'
    assert 'complexity_score' not in result


def test_actual_parser_cycles_and_diagnostics():
    value = collector._build_complexity({'src/a.ts': 'import "./b";', 'src/b.ts': 'import "./a";'})
    assert value['import_graph_status'] == 'measured'
    assert value['strongly_connected_components'] == 1
    assert sorted(value['files_in_import_cycles']) == ['src/a.ts', 'src/b.ts']
    partial = collector._build_complexity({'src/broken.ts': 'function broken( {'})
    assert partial['import_graph_status'] == 'partial'
    assert partial['cyclic_components'] is None
    assert collector._build_complexity({'src/a.py': 'x = 1'})['import_graph_status'] == 'unavailable'


def test_unknown_graph_preserves_unscored_rendering(monkeypatch):
    import io
    from pypdf import PdfReader
    from nico import comprehensive_native_providers as legacy, comprehensive_native_providers_v5 as v5
    from nico.comprehensive_decision_grade_markdown_v5 import _scorecard_and_risk_lines
    from nico.comprehensive_decision_grade_html_v6 import _scorecard_html
    from nico.comprehensive_premium_pdf_v6 import _build_pdf
    from nico.comprehensive_premium_synthesis_v6 import polish_assessment
    from tests.test_comprehensive_native_providers_v2 import _context, _repo, _scan
    evidence = collector._build_complexity({'src/a.py': 'def f(): return 0'})
    assert evidence['cyclic_components'] is None
    monkeypatch.setattr(legacy, '_repo', lambda _: _repo())
    monkeypatch.setattr(legacy, '_scan', lambda _: _scan())
    monkeypatch.setattr(legacy, '_complexity', lambda _: evidence)
    assessment = v5.canonical_scoring_provider(_context())['assessment']
    assessment['sections'] = [s for s in assessment['sections'] if s['id'] in ('architecture_debt', 'velocity_complexity')]
    assert all(s['presented_score'] is None for s in assessment['sections'])
    assessment = polish_assessment(assessment)
    limits = {k: 0 for k in ('stages_with_limitations', 'individual_limitation_records', 'score_affecting_records', 'informational_records')}
    pdf = _build_pdf(_context(), assessment, [], [], [], limits, '2026-11-02T00:00:00Z')
    surfaces = ['\n'.join(_scorecard_and_risk_lines({'sections': assessment['sections'], 'executive': []})), _scorecard_html(assessment['sections']),
                '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)]
    for surface in surfaces:
        assert 'NOT SCORED' in ' '.join(surface.split())
