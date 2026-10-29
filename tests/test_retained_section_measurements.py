from copy import deepcopy
import base64
import io
import pytest
from pypdf import PdfReader
from nico.retained_section_measurements_v1 import build_section_measurements, project_measurements, report_tables, score_reason
from nico.comprehensive_api_controller import _project_assessment
from tests.test_source_function_measurement_report_v1 import collected


def values(envelope):
    return {r['metric']: r['value'] for r in envelope['records']}


def sections():
    return [{'id': 'architecture_debt', 'score': None, 'presented_score': None, 'exclude_from_maturity': True,
             'score_input_provenance': {'reason': 'measured_score_missing', 'private': 'do not transport'}},
            {'id': 'ci_cd', 'configuration_maturity_score': 100},
            {'id': 'velocity_complexity', 'score': None, 'presented_score': None, 'exclude_from_maturity': True}]


def test_collected_measurements_project_without_changing_scores(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path)
    before = deepcopy((context, repo, complexity))
    output = build_section_measurements(context, repo, complexity, sections())
    architecture = values(output['architecture_debt'])
    assert architecture['files_analyzed'] == 1
    assert architecture['function_count'] == 1
    assert architecture['cc_maximum'] == 2
    assert architecture['retained_hotspots'] == len(complexity['hotspots'])
    assert values(output['velocity_complexity'])['ci_configuration_score'] == 100
    assert output['velocity_complexity']['delivery_performance_measured'] is False
    assert (context, repo, complexity) == before
    retained = sections()
    for section in retained:
        if section['id'] in output:
            section['retained_measurements'] = output[section['id']]
    projected = _project_assessment({'sections': retained}, context)
    arch = projected['sections'][0]
    assert arch['score'] is None and arch['presented_score'] is None
    assert arch['score_input_provenance'] == {'reason': 'measured_score_missing', 'source_field': 'complexity_evidence.complexity_score'}
    assert 'private' not in str(projected)
    assert values(arch['retained_measurements']) == architecture


@pytest.mark.parametrize('damage', ['scope', 'missing', 'coverage', 'function_hash'])
def test_conflicting_evidence_withholds_affected_aggregates_only(monkeypatch, tmp_path, damage):
    context, repo, complexity = collected(monkeypatch, tmp_path)
    if damage == 'scope': complexity['project_id'] = 'different'
    elif damage == 'missing': complexity.pop('maximum_fan_out')
    elif damage == 'coverage': complexity['profile_coverage']['eligible_source_files'] = -1
    else: complexity['source_function_measurements']['files'][0]['source_text_sha256'] = 'f'*64
    output = build_section_measurements(context, repo, complexity, sections())
    architecture = values(output['architecture_debt'])
    assert values(output['velocity_complexity'])['ci_configuration_score'] == 100
    if damage == 'scope':
        assert all(v is None for v in architecture.values())
    elif damage == 'missing':
        assert architecture['maximum_fan_out'] is None and architecture['cc_maximum'] == 2
    elif damage == 'coverage':
        assert architecture['eligible_source_files'] is None and architecture['cc_maximum'] == 2
    else:
        assert architecture['cc_maximum'] is None and architecture['files_analyzed'] == 1


def test_partial_complete_and_empty_populations_remain_distinct(monkeypatch, tmp_path):
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py': 'x=1', 'src/b.ts': 'function broken( { if (x) {'})
    output = build_section_measurements(context, repo, complexity, sections())['architecture_debt']
    records = output['records']
    assert any(r['metric'] == 'function_count' and r['value'] == 0 and r['validation'] == 'measured' for r in records)
    assert any(r['validation'] == 'partial' for r in records)
    assert any(r['metric'] == 'cc_maximum' and r['value'] is None for r in records)
    assert values(output)['observed_source_files'] >= values(output)['eligible_source_files']


@pytest.mark.parametrize('bad', [None, [], {'reason': 'arbitrary'}, {'reason': []}])
def test_score_reason_is_closed_allowlist(bad):
    assert score_reason(bad) == {}


@pytest.mark.parametrize('spanish', [False, True])
def test_bilingual_measurement_table_renders_with_pending_review_and_no_velocity(monkeypatch, tmp_path, spanish):
    from nico.comprehensive_report_package import _pdf, _markdown
    context, repo, complexity = collected(monkeypatch, tmp_path)
    output = build_section_measurements(context, repo, complexity, sections())
    assessment = {'sections': sections()}
    for section in assessment['sections']:
        if section['id'] in output: section['retained_measurements'] = output[section['id']]
    before = deepcopy(assessment)
    tables = report_tables(assessment, spanish=spanish, expected_identity=context)
    stage = {'stage_id': 'ci_cd_architecture_complexity_velocity', 'title': 'Measured evidence',
             'summary': 'Review required', 'status': 'review_required', 'findings': [], 'evidence': [], 'unavailable': [], 'structured_tables': tables}
    identity = {**context, 'generated_at': '2026-10-29'}
    md = _markdown(identity, assessment, [stage], '2026-10-29')
    pdf, error, _ = _pdf(identity, assessment, [stage], '2026-10-29')
    assert not error
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(pdf))).pages)
    for rendered in (md, text):
        assert ('revisión pendiente' if spanish else 'pending review') in rendered
        assert ('rendimiento de entrega no está medido' if spanish else 'Delivery performance is not measured') in rendered
        assert ('puntuacióncalibradadearquitectura' if spanish else 'calibratedarchitecture-scoreinput') in ''.join(rendered.split())
        assert context['commit_sha'] in rendered
    assert assessment == before


@pytest.mark.parametrize('target', ['complexity_snapshot', 'immutable_snapshot'])
def test_snapshot_conflict_cannot_credit_foreign_measurements(monkeypatch, tmp_path, target):
    context, repo, complexity = collected(monkeypatch, tmp_path)
    if target == 'complexity_snapshot':
        complexity['snapshot_id'] = 'foreign'
    else:
        context['prior_stage_results']['immutable_repository_snapshot']['snapshot']['project_id'] = 'foreign'
    output = build_section_measurements(context, repo, complexity, sections())
    assert all(v is None for v in values(output['architecture_debt']).values())
    assert values(output['velocity_complexity'])['ci_configuration_score'] == (100 if target == 'complexity_snapshot' else None)


def test_dimension_missingness_does_not_look_complete(monkeypatch, tmp_path):
    from nico.full_assessment_complexity_evidence import _analyze_python
    from nico.source_function_measurements_v1 import KEY, build_measurements, bind_measurements
    text = 'def f(): pass\ndef g(): pass\n'
    context, repo, complexity = collected(monkeypatch, tmp_path, files={'src/a.py': text})
    analysis = _analyze_python('src/a.py', text)
    analysis['functions'][0]['max_nesting'] = None
    complexity[KEY] = build_measurements({'src/a.py': text}, [analysis], {})
    bind_measurements(complexity)
    result = build_section_measurements(context, repo, complexity, sections())['architecture_debt']
    assert values(result)['nesting_measured_functions'] == 1
    assert values(result)['nesting_missing_functions'] == 1
    assert next(row for row in result['records'] if row['metric'] == 'nesting_maximum')['validation'] == 'partial'
    assert values(result)['function_count'] == 2


def _installed_measurement_worker(language, directory, placeholder='no'):
    from pathlib import Path
    from nico.api import final_report_worker_bootstrap
    from tests.test_roadmap_pdf_detail_completeness import _five_gap_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from nico import v2_premium_report_renderer as renderer
    from tests import test_v2_premium_report_renderer as base_fixture
    original_fixture = base_fixture._package
    def bound_fixture(locale):
        value = original_fixture(locale)
        if placeholder == 'yes':
            value['json']['identity'].update(customer_id='default_customer', project_id='default_project')
        return value
    with pytest.MonkeyPatch.context() as fixture_patch:
        fixture_patch.setattr(base_fixture, '_package', bound_fixture)
        package = _five_gap_package(language)
    canonical = package['json']
    with pytest.MonkeyPatch.context() as mp:
        import test_source_architecture_profile_evidence as fixture
        identity = deepcopy(canonical['identity'])
        snapshot = {**identity, 'status': 'attached', 'snapshot_id': 'snapshot_display', 'tree_sha': 'b'*40, 'captured_at': '2026-10-29T00:00:00Z'}
        mp.setattr(fixture, 'identities', lambda: (deepcopy(identity), deepcopy(snapshot)))
        fixture_files = {'src/a.py':'def f(x):\n    if x: return 1\n    return 0\n',
                         'src/b.ts':'function g(x: boolean) { if (x) return 1; return 0; }'} if placeholder == 'yes' else None
        context, repo, complexity = collected(mp, Path(directory), files=fixture_files)
    output = build_section_measurements(context, repo, complexity, sections())
    if placeholder == 'yes':
        assert len(output['architecture_debt']['records']) == 23
        for envelope in output.values():
            for record in envelope['records']:
                if record['metric'] in {'files_analyzed', 'import_edges', 'maximum_fan_out', 'duplicate_line_ratio', 'ci_configuration_score'}:
                    record['value'] = {'files_analyzed':1285, 'import_edges':9924, 'maximum_fan_out':103, 'duplicate_line_ratio':0.0857, 'ci_configuration_score':100}[record['metric']]
    canonical['assessment']['sections'] = sections()
    for section in canonical['assessment']['sections']:
        if section['id'] in output:
            section['score'] = section['presented_score'] = None
            section['exclude_from_maturity'] = True
            section['retained_measurements'] = output[section['id']]
    canonical['stage_summaries'].append({'stage_id': 'ci_cd_architecture_complexity_velocity',
        'title': 'Technical analysis', 'status': 'review_required', 'evidence': [], 'findings': [], 'unavailable': []})
    before = deepcopy(package)
    stages = renderer._canonical_stages(canonical)
    repeated = renderer._canonical_stages({**canonical, 'stage_summaries': stages})
    for value in (stages, repeated):
        technical = next(s for s in value if s['stage_id'] == 'ci_cd_architecture_complexity_velocity')
        assert sum(('puntuación calibrada de arquitectura' if language == 'es-MX' else 'calibrated architecture-score input') in line for line in technical['evidence']) == 1
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    for name, data in [('text', text), ('markdown', result['markdown']), ('html', result['html'])]:
        Path(directory, 'measurement.' + name).write_text(data)
    for content in (text, result['markdown'], result['html']):
        normalized = ''.join(content.split())
        assert ('Medicionesdearquitecturaconservadas' if language == 'es-MX' else 'Retainedarchitecturemeasurements') in normalized
        assert ('rendimientodeentreganoestámedido' if language == 'es-MX' else 'Deliveryperformanceisnotmeasured') in normalized
        assert ('puntuacióncalibradadearquitectura' if language == 'es-MX' else 'calibratedarchitecture-scoreinput') in normalized
        assert ('Funcionesconanidamientomedido' if language == 'es-MX' else 'Functionswithmeasurednesting') in normalized
        assert ('complejidadciclomáticamáxima' if language == 'es-MX' else 'Maximumcyclomaticcomplexity').casefold() in normalized.casefold()
        assert canonical['identity']['commit_sha'] in normalized
        if placeholder == 'yes':
            for expected in ('1285files', '9924edges', '103edges', '0.0857ratio', '100/100'):
                assert expected in normalized, (name if 'name' in locals() else '', expected)
            assert ('Archivosanalizadosparacomplejidad:Nodisponible' if language == 'es-MX' else 'Filesanalyzedforcomplexity:Unavailable') not in normalized
            from nico.retained_section_measurements_v1 import LABELS
            for metric, expected in [('files_analyzed','1285files'), ('import_edges','9924edges'), ('maximum_fan_out','103edges'), ('duplicate_line_ratio','0.0857ratio'), ('ci_configuration_score','100/100')]:
                label = ''.join(LABELS[metric][1 if language == 'es-MX' else 0].split())
                position = normalized.find(label + ':' + expected)
                assert position >= 0, (metric, expected)
                assert canonical['identity']['commit_sha'] in normalized[position:position+500]

    for original_section in canonical['assessment']['sections']:
        if 'retained_measurements' in original_section:
            final_section = next(s for s in result['json']['assessment']['sections'] if s['id'] == original_section['id'])
            assert final_section['retained_measurements'] == original_section['retained_measurements']
            assert final_section['score'] is None and final_section['exclude_from_maturity'] is True
    assert package == before
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_final_measurements(language, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    code = 'import sys; sys.path.insert(0, "tests"); from tests.test_retained_section_measurements import _installed_measurement_worker; _installed_measurement_worker(*sys.argv[1:])'
    result = subprocess.run([sys.executable, '-c', code, language, str(tmp_path)], cwd=root,
        env=owned_worker_environment(root, tmp_path, os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def test_projection_rejects_untrusted_fields_and_bounds_population():
    from nico.retained_section_measurements_v1 import VERSION
    row = {'metric': 'cc_maximum', 'value': 2, 'unit': 'secret', 'label_en': 'private',
           'population': 'measured:python:python_ast', 'validation': 'measured',
           'provenance': 'source_function_measurements', 'commit_sha': 'a'*40, 'private': 'secret'}
    identity = {'run_id': 'run', 'repository': 'owner/repo', 'commit_sha': 'a'*40, 'customer_id': 'customer', 'project_id': 'project'}
    for field, value in [('population', 'private'), ('provenance', 'secret'), ('commit_sha', 'stale'),
                         ('validation', []), ('value', True), ('value', float('nan'))]:
        damaged = {**row, field: value}
        projected = project_measurements({'artifact_schema': VERSION, 'identity': identity, 'records': [damaged]*100}, identity)
        assert len(projected['records']) == 64
        assert all(r['value'] is None for r in projected['records'])
        assert 'private' not in str(projected) and 'secret' not in str(projected)


@pytest.mark.parametrize('key', ['run_id', 'repository', 'commit_sha', 'customer_id', 'project_id'])
def test_display_boundary_rejects_foreign_scope(monkeypatch, tmp_path, key):
    context, repo, complexity = collected(monkeypatch, tmp_path)
    envelope = build_section_measurements(context, repo, complexity, sections())['architecture_debt']
    expected = {**context, key: 'f'*40 if key == 'commit_sha' else 'foreign'}
    assert any(r['value'] is not None for r in project_measurements(envelope, context)['records'])
    assert all(r['value'] is None for r in project_measurements(envelope, expected)['records'])
    assert all(r['value'] is None for r in project_measurements(envelope)['records'])
    assessment = {'sections': [{'id': 'architecture_debt', 'retained_measurements': envelope}]}
    assert all(r['value'] is None for r in _project_assessment(assessment, expected)['sections'][0]['retained_measurements']['records'])
    assert 'Unavailable' in str(report_tables(assessment, expected_identity=expected))


@pytest.mark.parametrize('change', ['value', 'missing', 'foreign'])
def test_repeated_display_replaces_only_owned_measurements(monkeypatch, tmp_path, change):
    from nico import v2_premium_report_renderer as renderer
    context, repo, complexity = collected(monkeypatch, tmp_path)
    envelope = build_section_measurements(context, repo, complexity, sections())['architecture_debt']
    canonical = {'identity': context, 'assessment': {'sections': [
        {'id': 'architecture_debt', 'score': None, 'retained_measurements': envelope}]},
        'stage_summaries': [{'stage_id': 'ci_cd_architecture_complexity_velocity', 'title': 'Technical evidence',
                            'evidence': ['Owner supplied statement'], 'findings': [], 'unavailable': []}]}
    canonical['stage_summaries'] = renderer._canonical_stages(canonical)
    original = next(s for s in canonical['stage_summaries'] if s['stage_id'] == 'ci_cd_architecture_complexity_velocity')
    old = next(line for line in original['_retained_measurement_lines'] if 'Files analyzed for complexity:' in line)
    if change == 'value': envelope['records'][0]['value'] = 42
    elif change == 'foreign': envelope['identity']['run_id'] = 'different'
    else: canonical['assessment']['sections'][0].pop('retained_measurements')
    after = next(s for s in renderer._canonical_stages(canonical) if s['stage_id'] == 'ci_cd_architecture_complexity_velocity')
    assert old not in after['evidence']
    assert 'Owner supplied statement' in after['evidence']
    if change == 'value': assert any('42 files' in line for line in after['evidence'])
    elif change == 'foreign': assert any('Unavailable' in line for line in after['evidence'])
    else: assert after['_retained_measurement_lines'] == []


def test_production_provider_attaches_measurements_without_rescoring(monkeypatch, tmp_path):
    from nico import comprehensive_native_providers_v5 as provider
    context, repo, complexity = collected(monkeypatch, tmp_path)
    from tests.test_comprehensive_native_providers_v5 import _baseline
    baseline = _baseline()
    for section in baseline['assessment']['sections']:
        if section['id'] in {'architecture_debt', 'velocity_complexity'}:
            section.update(score=None, presented_score=None, exclude_from_maturity=True)
    monkeypatch.setattr(provider.v4, 'canonical_scoring_provider', lambda _: deepcopy(baseline))
    result = provider.canonical_scoring_provider(context)['assessment']
    architecture = next(s for s in result['sections'] if s['id'] == 'architecture_debt')
    delivery = next(s for s in result['sections'] if s['id'] == 'velocity_complexity')
    assert architecture['score'] is None and delivery['score'] is None
    assert architecture['exclude_from_maturity'] and delivery['exclude_from_maturity']
    assert values(architecture['retained_measurements'])['cc_maximum'] == 2
    assert delivery['retained_measurements']['delivery_performance_measured'] is False


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_bound_measurements_survive_placeholder_identity_cleanup(language, tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    code = 'import sys; sys.path.insert(0, "tests"); from tests.test_retained_section_measurements import _installed_measurement_worker; _installed_measurement_worker(*sys.argv[1:])'
    result = subprocess.run([sys.executable, '-c', code, language, str(tmp_path), 'yes'], cwd=root,
        env=owned_worker_environment(root, tmp_path, os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


def _measurement_scope_fixture():
    from nico.retained_section_measurements_v1 import VERSION
    identity = {'run_id':'run', 'repository':'owner/repo', 'commit_sha':'a'*40,
                'customer_id':'default_customer', 'project_id':'default_project'}
    envelope = {'artifact_schema': VERSION, 'identity': deepcopy(identity), 'records':[
        {'metric':'files_analyzed', 'value':1285, 'unit':'files', 'population':'analyzed_source',
         'validation':'scope_bound', 'commit_sha':'a'*40, 'provenance':'complexity_evidence'}]}
    return {'identity':identity, 'assessment':{'sections':[{'id':'architecture_debt', 'score':None,
        'exclude_from_maturity':True, 'retained_measurements':envelope}]}}


def test_display_scope_is_idempotent_and_keeps_original_measurements():
    from nico.comprehensive_human_review_package_cleanup_v1 import sanitize_client_identity
    from nico.retained_section_measurements_v1 import report_measurement_identity
    original = _measurement_scope_fixture()
    before = deepcopy(original)
    cleaned = sanitize_client_identity(original)
    assert cleaned['identity']['customer_id'] == cleaned['identity']['project_id'] == 'Not supplied'
    assert report_measurement_identity(cleaned) == original['identity']
    assert sanitize_client_identity(cleaned) == cleaned
    assert cleaned['assessment'] == original['assessment']
    assert original == before


@pytest.mark.parametrize('field', ['run_id','repository','commit_sha','customer_id','project_id'])
@pytest.mark.parametrize('target', ['report', 'context', 'envelope'])
def test_foreign_measurement_scope_remains_unavailable(field, target):
    from nico.comprehensive_human_review_package_cleanup_v1 import sanitize_client_identity
    from nico.retained_section_measurements_v1 import report_measurement_identity, REPORT_SCOPE_KEY
    cleaned = sanitize_client_identity(_measurement_scope_fixture())
    if target == 'report':
        cleaned['identity'][field] = 'foreign'
    elif target == 'context':
        cleaned[REPORT_SCOPE_KEY]['identity'][field] = 'foreign'
    else:
        cleaned['assessment']['sections'][0]['retained_measurements']['identity'][field] = 'foreign'
    again = sanitize_client_identity(cleaned)
    table = report_tables(again['assessment'], expected_identity=report_measurement_identity(again))[0]
    assert table['rows'][0][1] == 'Unavailable'
    assert table['rows'][0][2].endswith('SHA -')


@pytest.mark.parametrize('bad', [None, [], {}, {'artifact_schema':'foreign'}, {'artifact_schema':'nico.retained-measurement-report-scope.v1','identity':[]}])
def test_bad_existing_scope_is_not_rebound(bad):
    from nico.comprehensive_human_review_package_cleanup_v1 import sanitize_client_identity
    from nico.retained_section_measurements_v1 import report_measurement_identity, REPORT_SCOPE_KEY
    original = _measurement_scope_fixture()
    original[REPORT_SCOPE_KEY] = bad
    cleaned = sanitize_client_identity(original)
    assert cleaned[REPORT_SCOPE_KEY] == bad
    assert report_measurement_identity(cleaned) is None


def test_historical_report_cannot_recover_identity_from_measurement_envelope():
    from nico.retained_section_measurements_v1 import report_measurement_identity
    original = _measurement_scope_fixture()
    original['identity'].update(customer_id='Not supplied', project_id='Not supplied')
    table = report_tables(original['assessment'], expected_identity=report_measurement_identity(original))[0]
    assert table['rows'][0][1] == 'Unavailable'


def test_reports_without_measurements_do_not_gain_scope_context():
    from nico.comprehensive_human_review_package_cleanup_v1 import sanitize_client_identity
    from nico.retained_section_measurements_v1 import REPORT_SCOPE_KEY
    original = _measurement_scope_fixture()
    original['assessment']['sections'][0].pop('retained_measurements')
    assert REPORT_SCOPE_KEY not in sanitize_client_identity(original)
