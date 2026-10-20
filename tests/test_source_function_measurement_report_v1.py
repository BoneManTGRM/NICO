from copy import deepcopy
import base64
import io
import html
import json
import os
import re
from pathlib import Path

import pytest
from pypdf import PdfReader

import test_source_architecture_profile_evidence as fixture
from nico.source_function_measurement_report_v1 import measurement_tables, UNAVAILABLE
from nico.source_function_measurements_v1 import KEY, bind_measurements, build_measurements
from nico import typescript_ast_complexity_v1 as collector
from nico import comprehensive_report_package as report
from nico.comprehensive_native_providers import architecture_data_flow_provider


def collected(monkeypatch, tmp_path, text='def f(x):\n    if x: return 1\n    return 0\n', files=None):
    collector.install_typescript_ast_complexity_v1()
    return fixture.collect('snapshot', monkeypatch, tmp_path, files=files or {'src/a.py': text})[:3]


def rows(tables):
    return {key: value for table in tables if table['columns'] == ['Measure', 'Value'] for key, value in table['rows']}


def test_independent_binding_and_complete_population(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path)
    tables = measurement_tables(context, repo, complexity)
    values = rows(tables)
    assert values['Enumerated functions'] == 1
    assert values['CC maximum'] == 2
    assert values['Sum(CC-1) in enumerated functions'] == 1
    assert values['Complete observed files'] == 1
    assert values['Partial observed files'] == 0
    assert 'scoped conformance reported separately' in values['Status']
    from nico.source_function_conformance_report_v1 import integrate_conformance
    from nico.source_function_conformance_v1 import build_conformance
    integrated = integrate_conformance(tables, build_conformance(context, repo, complexity))
    assert integrated == architecture_data_flow_provider(context)['evidence']['structured_tables'][-len(integrated):]


@pytest.mark.parametrize('mutation', ['absent', 'malformed', 'unbound', 'run_id', 'repository', 'customer_id', 'project_id', 'snapshot_id', 'snapshot_commit_sha', 'foreign_envelope', 'foreign_snapshot', 'foreign_repository', 'hash', 'inventory_subset', 'inventory_observation', 'missing_dimension', 'unavailable'])
def test_unqualified_measurements_are_unavailable(monkeypatch, tmp_path, mutation):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py':'def f(): pass', 'src/b.py':'def g(): pass'})
    value = complexity[KEY]
    if mutation == 'absent': complexity.pop(KEY)
    elif mutation == 'malformed': complexity[KEY] = []
    elif mutation == 'unbound': value['identity'] = None
    elif mutation in value['identity']: value['identity'][mutation] = 'foreign'
    elif mutation == 'foreign_envelope': complexity['customer_id'] = 'foreign'
    elif mutation == 'foreign_repository': repo['project_id'] = 'foreign'
    elif mutation == 'foreign_snapshot': context['prior_stage_results']['immutable_repository_snapshot']['snapshot']['customer_id'] = 'foreign'
    elif mutation == 'hash': value['files'][0]['source_text_sha256'] = 'f'*64
    elif mutation == 'inventory_subset':
        # Internally valid, same identity, but omits independently observed source.
        replacement = collector._build_complexity({'src/a.py':'def f(): pass'})[KEY]
        replacement['identity'] = deepcopy(value['identity'])
        complexity[KEY] = replacement
    elif mutation == 'inventory_observation': repo['architecture_evidence']['source_observation']['input_inventory'][0]['observed_text_sha256'] = 'f'*64
    elif mutation == 'missing_dimension': del value['files'][0]['metrics']['nesting']
    elif mutation == 'unavailable': complexity[KEY] = {'status': 'unavailable'}
    assert rows(measurement_tables(context, repo, complexity))['Status'] == UNAVAILABLE


def test_filtered_membership_cannot_be_guessed(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py':'def f(): pass', 'locale.ts':'<?xml version="1.0"?><TS version="2.1" language="en"><context><name>X</name><message><source>Hello</source><translation>Hello</translation></message></context></TS>'})
    assert complexity['qt_translation_files_excluded'] == 1
    assert rows(measurement_tables(context, repo, complexity))['Status'] == UNAVAILABLE


def test_empty_and_missing_measurements_are_distinct(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py':'x=1', 'src/b.py':'def ('})
    values = rows(measurement_tables(context, repo, complexity))
    assert values['Enumerated functions'] == 0
    assert values['CC maximum'] is None
    assert values['Missing files'] == 1
    assert values['Complete observed files'] == 1


def test_partial_and_missing_dimension_populations(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py':'def f(): pass', 'src/b.ts':'function broken( { if (x) {'})
    tables = measurement_tables(context, repo, complexity)
    assert rows(tables)['Partial observed files'] == 1
    assert any('Partial observed population (parser incomplete)' in table['title'] for table in tables)
    assert any('Complete observed population' in table['title'] for table in tables)
    from nico.full_assessment_complexity_evidence import _analyze_python
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py':'def f(): pass'})
    analysis = _analyze_python('src/a.py', 'def f(): pass')
    analysis['functions'][0]['max_nesting'] = None
    complexity[KEY] = build_measurements({'src/a.py':'def f(): pass'}, [analysis], {})
    bind_measurements(complexity)
    values = rows(measurement_tables(context, repo, complexity))
    assert values['NESTING maximum'] is None
    assert values['NESTING measured functions'] == 0
    assert values['NESTING missing functions'] == 1


def test_extraction_is_not_decision_reduction(monkeypatch, tmp_path):
    def function(name, count):
        return f'def {name}(x):\n' + '    if x: pass\n'*count + '    return 0\n'
    variants = [function('base',60), ''.join(function(f'helper{i}',10) for i in range(6))+function('wrapper',0), function('reduced',30)]
    values = []
    for source in variants:
        context, repo, complexity = collected(monkeypatch, tmp_path, source)
        values.append(rows(measurement_tables(context, repo, complexity)))
    assert [v['Sum(CC-1) in enumerated functions'] for v in values] == [60,60,30]
    assert [v['Enumerated functions'] for v in values] == [1,7,1]
    assert [v['CC maximum'] for v in values] == [61,11,31]
    assert [v['CC at least 21: functions'] for v in values] == [1,0,1]


@pytest.mark.parametrize("bins", [1, 40, 60])
def test_english_final_crossformat_and_artifacts(monkeypatch, tmp_path, bins):
    from test_source_profile_final_rendering import collected_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_pdf_embedded_fonts_v1 import install_comprehensive_pdf_embedded_fonts_v1
    from nico.comprehensive_pdf_layout_polish_v1 import install_comprehensive_pdf_layout_polish_v1
    collector.install_typescript_ast_complexity_v1()
    install_comprehensive_pdf_embedded_fonts_v1()
    install_comprehensive_pdf_layout_polish_v1()
    decisions = [22] if bins == 1 else range(bins)
    source = ''.join(f'def f{i}(x):\n' + '    if x: pass\n'*count + '    return 0\n' for i,count in enumerate(decisions))
    monkeypatch.setattr(fixture, 'FILES', {'src/a.py': source})
    package, _ = collected_package(monkeypatch, tmp_path)
    canonical = package['json']
    tables = deepcopy(canonical['stage_summaries'][1]['structured_tables'])
    package['markdown'] = report._markdown(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
    encoded, error, _ = report._pdf(canonical['identity'],canonical['assessment'],canonical['stage_summaries'],package['generated_at'])
    assert not error
    package['pdf_base64'] = encoded
    baseline = deepcopy(package)
    baseline['json']['stage_summaries'][1]['structured_tables'] = tables[:3]
    baseline_result = rebuild_client_artifacts(baseline)
    result = rebuild_client_artifacts(package)
    pdf = base64.b64decode(result['pdf_base64'])
    reader = PdfReader(io.BytesIO(pdf))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert result['json']['stage_summaries'][1]['structured_tables'] == tables
    for output in (result['markdown'],result['html'],text):
        for phrase in ('Function measurement scope', 'Complete observed population', 'CC maximum', 'CC at least 21: functions', 'scoped conformance reported separately', 'Sum(CC-1)'):
            assert phrase in output
    assert rows(tables)['CC maximum'] == (23 if bins == 1 else bins)
    assert rows(tables)['CC at least 21: functions'] == (1 if bins == 1 else bins - 20)
    summary = next(table for table in tables if table['title'].startswith('Complete observed population'))
    assert len(summary['rows']) == 14
    html_text = html.unescape(re.sub(r'<[^>]+>', ' ', result['html']))
    for label, value in summary['rows']:
        if re.fullmatch(r'CC [0-9]+: functions', label):
            continue
        assert f'| {label} | {value} |' in html.unescape(result['markdown'])
        for rendered_text in (text, html_text):
            assert re.search(re.escape(label) + r'\s+' + re.escape(str(value)) + r'(?!\w)', ' '.join(rendered_text.split())), (label, value)
    if bins > 1:
        distribution = next(table for table in tables if table['title'].startswith('CC distribution'))
        assert len(distribution['rows']) == bins
        for label, value in distribution['rows']:
            assert label in result['markdown'] and label in result['html']
        if bins > 48:
            assert 'Remaining rows are omitted from the PDF' in text
            assert 'Complete retained rows: 60' in text
            assert 'CC 60: functions' not in text
        else:
            assert 'CC 40: functions' in text
    assert {k:v for k,v in result['json']['assessment'].items() if k != 'stage_summaries'} == {k:v for k,v in baseline_result['json']['assessment'].items() if k != 'stage_summaries'}
    assert len(reader.pages) <= result['client_report_completion']['client_pdf_page_boundary']
    target = Path(os.environ.get('MEASUREMENT_ARTIFACT_DIR',str(tmp_path))) / f'bins-{bins}'
    target.mkdir(parents=True,exist_ok=True)
    for name, data in [('report.pdf',pdf),('report.json',json.dumps(result['json'],sort_keys=True,indent=2).encode()),('report.md',result['markdown'].encode()),('report.html',result['html'].encode()),('pdf-text.txt',text.encode())]:
        (target/name).write_bytes(data)


def test_counts_exceed_retained_locations_without_inventing_locations(monkeypatch, tmp_path):
    source = ''.join(f'def f{i}(x):\n' + '    if x: pass\n'*22 + '    return 0\n' for i in range(61))
    context, repo, complexity = collected(monkeypatch, tmp_path, source)
    tables = measurement_tables(context, repo, complexity)
    assert len(complexity['hotspots']) == 50
    assert rows(tables)['CC at least 21: functions'] == 61
    assert rows(tables)['Enumerated functions'] == 61
    assert all(table['columns'] == ['Measure', 'Value'] for table in tables)


def test_empty_eligible_inventory_is_not_missing(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'README.md':'# Docs'})
    tables = measurement_tables(context, repo, complexity)
    assert rows(tables)['Supplied eligible source files'] == 0
    assert rows(tables)['Status'] != UNAVAILABLE
    assert len(tables) == 1
