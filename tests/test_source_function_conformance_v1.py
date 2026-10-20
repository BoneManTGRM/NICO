from copy import deepcopy

import pytest

from test_source_function_measurement_report_v1 import collected
from nico.source_function_measurements_v1 import KEY
from nico.source_function_conformance_v1 import build_conformance


def function(name, cc):
    return f'def {name}(x):\n' + '    if x: pass\n' * (cc - 1) + '    return 0\n'


def result(monkeypatch, tmp_path, source=None, files=None):
    context, repo, complexity = collected(monkeypatch, tmp_path, source or function('a', 20)+function('b', 21), files)
    return (context, repo, complexity), build_conformance(context, repo, complexity)


def test_threshold_counts_and_no_authority_or_mutation(monkeypatch, tmp_path):
    inputs, value = result(monkeypatch, tmp_path)
    before = deepcopy(inputs)
    assert build_conformance(*inputs) == value
    assert inputs == before
    assert value['status'] == 'qualified'
    assert value['identity']['snapshot_commit_sha'] == inputs[0]['commit_sha']
    assert value['combined']['cc'] == {'threshold': 20, 'conforming': 1, 'violations': 1, 'measured_functions': 2, 'percentage': 50.0, 'maximum': 21, 'sum_cc_minus_1': 39}
    assert value['combined']['nesting']['threshold'] == 4
    assert value['combined']['nesting']['percentage'] == 100.0
    for flag in ('included_in_overall_maturity', 'architecture_quality_established', 'delivery_velocity_established'):
        assert value[flag] is False
    assert 'complexity_score' not in repr(value)


@pytest.mark.parametrize('key', ['run_id','repository','customer_id','project_id','snapshot_id','snapshot_commit_sha'])
def test_foreign_measurement_identity(monkeypatch, tmp_path, key):
    inputs, _ = result(monkeypatch, tmp_path)
    inputs[2][KEY]['identity'][key] = 'foreign'
    assert build_conformance(*inputs)['status'] == 'unavailable'


@pytest.mark.parametrize('damage', ['row_hash','inventory_hash','inventory_subset','duplicate','aggregate','missing','partial','lexical','missing_parser','observation_hash','envelope','snapshot','acquisition','coverage_count','coverage_paths','coverage_disagreement'])
def test_unqualified_populations_receive_no_percentage(monkeypatch, tmp_path, damage):
    inputs, _ = result(monkeypatch, tmp_path)
    context, repo, complexity = inputs
    value = complexity[KEY]
    if damage == 'row_hash': value['files'][0]['source_text_sha256'] = 'f'*64
    elif damage == 'inventory_hash': value['inventory_sha256'] = 'f'*64
    elif damage == 'inventory_subset': value['inventory'] = []
    elif damage == 'duplicate': value['files'].append(deepcopy(value['files'][0]))
    elif damage == 'aggregate': value['aggregate']['function_count'] += 1
    elif damage == 'missing': del complexity[KEY]
    elif damage == 'partial': value['files'][0]['status'] = 'partial'
    elif damage == 'lexical': value['files'][0]['method'] = 'javascript_lexical'
    elif damage == 'missing_parser': value['files'][0]['parser_version'] = None
    elif damage == 'observation_hash': repo['architecture_evidence']['source_observation']['observation_sha256'] = 'f'*64
    elif damage == 'envelope': complexity['project_id'] = 'foreign'
    elif damage == 'snapshot': context['prior_stage_results']['immutable_repository_snapshot']['snapshot']['customer_id'] = 'foreign'
    elif damage == 'acquisition': complexity['profile_coverage']['inventory_complete'] = False
    elif damage == 'coverage_count': complexity['profile_coverage']['eligible_source_files'] += 1
    elif damage == 'coverage_paths': complexity['profile_coverage']['analyzed_source_paths'] = []
    elif damage == 'coverage_disagreement': repo['file_evidence']['profile_coverage'] = {}
    output = build_conformance(*inputs)
    assert output['status'] == 'unavailable'
    assert output['combined'] is None
    assert output['languages'] == []


@pytest.mark.parametrize('count', [True, -1, 0, 1.5, '2', float('nan'), float('inf')])
def test_malformed_histogram_counts(monkeypatch, tmp_path, count):
    inputs, _ = result(monkeypatch, tmp_path)
    inputs[2][KEY]['files'][0]['metrics']['cc']['histogram']['20'] = count
    assert build_conformance(*inputs)['status'] == 'unavailable'


@pytest.mark.parametrize('bin', ['0','-1','020','1.5','NaN',20])
def test_malformed_histogram_bins(monkeypatch, tmp_path, bin):
    inputs, _ = result(monkeypatch, tmp_path)
    inputs[2][KEY]['files'][0]['metrics']['cc']['histogram'] = {bin: 2}
    assert build_conformance(*inputs)['status'] == 'unavailable'


def test_empty_population_never_100_and_cpp_excluded(monkeypatch, tmp_path):
    from nico import full_assessment_complexity_evidence as base
    monkeypatch.setattr(base, '_analyze_cpp', lambda *args: {'status':'unsupported', 'note':'C++ remains paused'})
    _, value = result(monkeypatch, tmp_path, files={'src/a.py':'x=1', 'src/b.cpp':'int f() {return 0;}'})
    assert value['status'] == 'not_applicable'
    assert value['combined']['function_count'] == 0
    assert value['combined']['cc']['percentage'] is None
    assert 'src/b.cpp' in value['exclusions']['unsupported_observed_paths']


def test_parser_error_and_incomplete_acquisition(monkeypatch, tmp_path):
    _, value = result(monkeypatch, tmp_path, files={'src/a.py':'def ('})
    assert value['status'] == 'unavailable'
    import test_source_architecture_profile_evidence as fixture
    context, repo, complexity, _ = fixture.collect('snapshot',monkeypatch,tmp_path,files={'a.py':function('a',1)},missing=('a.py',))
    assert build_conformance(context,repo,complexity)['status'] == 'unavailable'


def test_counts_beyond_hotspot_limit(monkeypatch, tmp_path):
    inputs, value = result(monkeypatch,tmp_path,source=''.join(function(f'f{i}',21) for i in range(61)))
    assert len(inputs[2]['hotspots']) == 50
    assert value['combined']['cc']['violations'] == 61
    assert value['combined']['function_count'] == 61


def test_ratio_does_not_establish_improvement(monkeypatch,tmp_path):
    variants = [function('base',61), ''.join(function(f'h{i}',11) for i in range(6))+function('wrapper',1), function('base',61)+''.join(function(f't{i}',1) for i in range(99))]
    values = [result(monkeypatch,tmp_path,source=source)[1] for source in variants]
    assert [v['combined']['cc']['sum_cc_minus_1'] for v in values] == [60,60,60]
    assert [v['combined']['cc']['violations'] for v in values] == [1,0,1]
    assert [v['combined']['cc']['percentage'] for v in values] == [0.0,100.0,99.0]
    assert all('ratio alone' in v['limitations'] for v in values)
    assert all(v['architecture_quality_established'] is False for v in values)


def test_mixed_language_collector_populations(monkeypatch, tmp_path):
    _, value = result(monkeypatch,tmp_path,files={'a.py':function('a',21), 'b.ts':'function b(x: boolean) { if (x) { return 1; } return 0; }'})
    assert value['status'] == 'qualified'
    by_language = {row['language']:row for row in value['languages']}
    assert by_language['python']['cc']['conforming'] == 0
    assert by_language['javascript-typescript']['cc']['conforming'] == 1
    assert value['combined']['cc']['percentage'] == 50.0


def test_recovered_counts_are_recomputed_not_fixed(monkeypatch,tmp_path):
    from nico.source_function_measurements_v1 import build_measurements, bind_measurements
    files = {'a.py':function('a',1), 'b.ts':'function b() { return 0; }'}
    inputs, _ = result(monkeypatch,tmp_path,files=files)
    analyses = []
    for path, language, method, conforming, total in (
        ('a.py','python','python_ast',10174,10939),
        ('b.ts','javascript-typescript','typescript_compiler_ast',2027,2090),
    ):
        # Synthetic parser output reproduces recovered counts, never a production constant.
        functions = [{'path':path,'method':method,'cyclomatic_complexity':20 if i<conforming else 21,
                      'max_nesting':4 if i%2 else 5,'loc':10} for i in range(total)]
        analyses.append({'path':path,'language':language,'method':method,'status':'analyzed',
                         'declared_function_count':total,'functions':functions})
    inputs[2][KEY] = build_measurements(files,analyses,{'parser_version':'synthetic-test'})
    bind_measurements(inputs[2])
    value = build_conformance(*inputs)
    assert value['combined']['cc']['conforming'] == 12201
    assert value['combined']['cc']['measured_functions'] == 13029
    assert value['combined']['cc']['violations'] == 828
    assert value['combined']['cc']['percentage'] == 93.64
    analyses[0]['functions'][0]['cyclomatic_complexity'] = 21
    inputs[2][KEY] = build_measurements(files,analyses,{'parser_version':'synthetic-test'})
    bind_measurements(inputs[2])
    assert build_conformance(*inputs)['combined']['cc']['conforming'] == 12200


def test_missing_nesting_is_not_joint_conformance(monkeypatch,tmp_path):
    from nico.source_function_measurements_v1 import build_measurements, bind_measurements
    from nico.full_assessment_complexity_evidence import _analyze_python
    source = function('a',20)
    inputs, _ = result(monkeypatch,tmp_path,source=source)
    analysis = _analyze_python('src/a.py',source)
    analysis['functions'][0]['max_nesting'] = None
    inputs[2][KEY] = build_measurements({'src/a.py':source},[analysis],{})
    bind_measurements(inputs[2])
    value = build_conformance(*inputs)
    assert value['status'] == 'qualified'
    assert value['combined']['cc']['percentage'] == 100.0
    assert value['combined']['nesting']['missing_functions'] == 1
    assert value['combined']['nesting']['percentage'] is None
    assert 'joint CC/nesting conformance cannot be inferred' in value['limitations']


@pytest.mark.parametrize('field', ['eligible_source_files','analyzed_source_files','profiled_text_files'])
@pytest.mark.parametrize('bad', [True, -1, '1', float('nan')])
def test_coverage_counts_are_strict(monkeypatch,tmp_path,field,bad):
    inputs,_ = result(monkeypatch,tmp_path)
    inputs[2]['profile_coverage'][field]=bad
    assert build_conformance(*inputs)['status']=='unavailable'


def test_self_consistent_histogram_rewrite_is_not_independent_evidence(monkeypatch,tmp_path):
    from nico.source_function_measurements_v1 import _aggregate, _dimension
    inputs,original=result(monkeypatch,tmp_path,source=function('a',21))
    assert original['combined']['cc']['percentage']==0.0
    assert original['combined']['cc']['sum_cc_minus_1']==20
    context,repo,complexity=inputs
    independent_before=deepcopy((context['commit_sha'],repo,complexity['profile_coverage']))
    value=complexity[KEY]
    value['files'][0]['metrics']['cc']=_dimension({'1':1},'cc')
    value['aggregate']=_aggregate(value['files'])
    assert (context['commit_sha'],repo,complexity['profile_coverage'])==independent_before
    assert build_conformance(*inputs)['status']=='unavailable'


def test_well_formed_forged_producer_hashes_are_not_authentication(monkeypatch,tmp_path):
    inputs,_=result(monkeypatch,tmp_path)
    producer=inputs[2][KEY]['producer_source_sha256']
    inputs[2][KEY]['producer_source_sha256']={key:'f'*64 for key in producer}
    assert build_conformance(*inputs)['status']=='unavailable'


@pytest.mark.parametrize('field', ['lfs_pointer_entries','submodule_entries'])
@pytest.mark.parametrize('bad', [None, {}, 'malformed', [None], [{}], ['path'], [{'path':'x'}]])
def test_external_coverage_shapes_fail_closed(monkeypatch,tmp_path,field,bad):
    inputs,_=result(monkeypatch,tmp_path)
    for coverage in (inputs[1]['file_evidence']['profile_coverage'],inputs[2]['profile_coverage']):
        coverage[field]=deepcopy(bad)
    assert build_conformance(*inputs)['status']=='unavailable'


@pytest.mark.parametrize('field', ['lfs_pointer_entries','submodule_entries','submodule_contents_acquired','inventory_scope'])
def test_missing_external_coverage_is_not_empty(monkeypatch,tmp_path,field):
    inputs,_=result(monkeypatch,tmp_path)
    inputs[1]['file_evidence']['profile_coverage'].pop(field,None)
    inputs[2]['profile_coverage'].pop(field,None)
    assert build_conformance(*inputs)['status']=='unavailable'


def test_legacy_observation_display_survives_unqualified_coverage(monkeypatch,tmp_path):
    from nico.source_function_measurement_report_v1 import measurement_tables
    inputs,_=result(monkeypatch,tmp_path)
    context,repo,complexity=inputs
    before=measurement_tables(context,repo,complexity)
    complexity['profile_coverage']['submodule_entries']='malformed'
    repo['file_evidence']['profile_coverage']['submodule_entries']='malformed'
    assert build_conformance(*inputs)['status']=='unavailable'
    assert measurement_tables(context,repo,complexity)==before


def test_valid_explicit_external_inventories_are_not_function_credit(monkeypatch,tmp_path):
    inputs,_=result(monkeypatch,tmp_path)
    coverage=inputs[2]['profile_coverage']
    coverage['submodule_entries']=[{'path':'external/library','commit_sha':'b'*40}]
    coverage['lfs_pointer_entries']=[{'path':'assets/data.bin','oid':'sha256:'+'c'*64,'size_bytes':12}]
    inputs[1]['file_evidence']['profile_coverage']=deepcopy(coverage)
    value=build_conformance(*inputs)
    assert value['status']=='qualified'
    assert value['combined']['function_count']==2
    assert value['exclusions']['submodule_contents_acquired'] is False
    coverage['submodule_entries'].append(deepcopy(coverage['submodule_entries'][0]))
    inputs[1]['file_evidence']['profile_coverage']=deepcopy(coverage)
    assert build_conformance(*inputs)['status']=='unavailable'
