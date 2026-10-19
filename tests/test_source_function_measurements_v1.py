from copy import deepcopy
import json

import pytest

from nico import typescript_ast_complexity_v1 as collector
from nico.source_function_measurements_v1 import (
    KEY, IDENTITY_KEYS, bind_measurements, build_measurements, validate_measurements,
)


def measured(files):
    return collector._build_complexity(files)[KEY]


def valid(value, identity=None):
    return validate_measurements(value, expected_identity=identity, expected_inventory=value['inventory'])


@pytest.mark.parametrize('language', ['py', 'ts'])
def test_actual_collectors_retain_all_hotspots(language):
    if language == 'py':
        text = ''.join(f'def f{i}(x):\n' + ''.join('    if x: pass\n' for _ in range(45)) for i in range(61))
    else:
        text = ''.join(f'function f{i}(x: boolean) {{' + 'if(x) {}' * 45 + '}\n' for i in range(61))
    result = collector._build_complexity({f'src/module.{language}': text})
    value = result[KEY]
    assert valid(value)
    assert len(result['hotspots']) == 50
    assert value['aggregate']['function_count'] == 61
    assert value['aggregate']['cc'] == {
        'histogram': {'46': 61}, 'maximum': 46, 'measured_functions': 61,
        'sum_cc_minus_1': 2745, 'absolute_counts_at_least': {'11': 61, '21': 61}}
    assert value['aggregate']['loc']['measured_functions'] == 61
    assert value['aggregate']['nesting']['measured_functions'] == 61
    assert value['files'][0]['status'] == 'measured'
    assert value['files'][0]['parser_version']


@pytest.mark.parametrize('language', ['py', 'ts'])
def test_extraction_reduction_and_population_addition(language):
    def function(name, n):
        if language == 'py':
            return f'def {name}(x):\n' + '    if x: pass\n' * n + '    return 0\n'
        return f'function {name}(x: boolean) {{' + 'if(x) {}' * n + 'return 0;}\n'
    variants = [function('base', 60), ''.join(function(f'helper{i}', 10) for i in range(6)) + function('wrapper', 0),
                function('reduced', 30), function('base', 60) + ''.join(function(f'trivial{i}', 0) for i in range(100))]
    values = [measured({f'src/module.{language}': text})['aggregate'] for text in variants]
    assert [v['cc']['sum_cc_minus_1'] for v in values] == [60, 60, 30, 60]
    assert [v['function_count'] for v in values] == [1, 7, 1, 101]
    assert [v['cc']['maximum'] for v in values] == [61, 11, 31, 61]


def test_scope_gaps_and_language_semantics(monkeypatch):
    value = measured({'src/a.py': 'x = lambda y: 1 if y else 0\nif flag: x = 1\n',
                      'src/b.ts': 'const f = (x: boolean) => x ? 1 : 0;', 'src/bad.py': 'def (',
                      'tests/ignored.py': 'def ignored(): pass'})
    assert valid(value)
    assert len(value['files']) == 3
    assert value['files'][0]['metrics']['function_count'] == 0
    assert value['files'][1]['metrics']['function_count'] == 1
    assert value['files'][2]['status'] == 'missing'
    assert value['files'][2]['metrics'] is None
    assert value['limitations']['module_and_class_initializer_residual'] == 'unavailable'
    monkeypatch.setattr(collector, '_run_typescript_ast', lambda files: {'status': 'unavailable'})
    fallback = measured({'src/a.ts': 'function f() {if(x) return 0;}'})
    assert fallback['files'][0]['status'] == 'unsupported'
    assert fallback['files'][0]['metrics'] is None
    assert valid(fallback)


def test_diagnostics_and_missing_dimensions():
    value = measured({'src/bad.ts': 'function broken( { if (x) {'})
    assert value['files'][0]['status'] == 'partial'
    assert valid(value)
    from nico.full_assessment_complexity_evidence import _analyze_python
    source = 'def f(x):\n    return x\n'
    analysis = _analyze_python('src/a.py', source)
    analysis['functions'][0]['max_nesting'] = None
    value = build_measurements({'src/a.py': source}, [analysis], {})
    assert valid(value)
    assert value['aggregate']['nesting']['maximum'] is None
    assert value['aggregate']['nesting']['measured_functions'] == 0


@pytest.fixture
def sample():
    return measured({'src/a.py': 'def f(x):\n    if x: return 1\n    return 0\n', 'src/b.py': 'def g(): return 0'})


def test_binding_and_legacy_missing(sample):
    identity = {key: 'fixture-' + key for key in IDENTITY_KEYS}
    identity['snapshot_commit_sha'] = 'a' * 40
    envelope = {**identity, KEY: sample}
    bind_measurements(envelope)
    assert valid(envelope[KEY], identity)
    assert sample['identity'] is None
    assert not validate_measurements(None, expected_identity=identity, expected_inventory=[])
    for key in IDENTITY_KEYS:
        changed = {**identity, key: 'b' * 40}
        with pytest.raises(ValueError):
            validate_measurements(envelope[KEY], expected_identity=changed, expected_inventory=sample['inventory'])
    with pytest.raises(ValueError):
        validate_measurements(envelope[KEY], expected_identity=identity, expected_inventory=[])


@pytest.mark.parametrize('bad', [True, -1, 1.5, '2', None, float('nan')])
def test_malformed_counts(sample, bad):
    sample['files'][0]['metrics']['cc']['histogram']['2'] = bad
    with pytest.raises(ValueError):
        valid(sample)


@pytest.mark.parametrize('target', ['function_count', 'maximum', 'sum_cc_minus_1', 'absolute_counts_at_least', 'aggregate', 'identity', 'file_hash', 'producer'])
def test_tampered_reconciliation(sample, target):
    metrics = sample['files'][0]['metrics']
    if target == 'function_count': metrics[target] = 999
    elif target in ('maximum', 'sum_cc_minus_1'): metrics['cc'][target] = 999
    elif target == 'absolute_counts_at_least': metrics['cc'][target]['11'] = 999
    elif target == 'aggregate': sample['aggregate']['cc']['histogram']['2'] = 999
    elif target == 'identity': sample['identity'] = {'snapshot_commit_sha': 'b' * 40}
    elif target == 'file_hash': sample['files'][0]['source_text_sha256'] = 'b' * 64
    elif target == 'producer': sample['producer_source_sha256'] = {}
    with pytest.raises(ValueError): valid(sample)


def test_duplicate_paths_and_analysis_scope(sample):
    sample['files'][1] = deepcopy(sample['files'][0])
    with pytest.raises(ValueError): valid(sample)
    from nico.full_assessment_complexity_evidence import _analyze_python
    analysis = _analyze_python('src/a.py', 'def f(): pass')
    with pytest.raises(ValueError): build_measurements({'src/a.py': 'def f(): pass'}, [analysis, analysis], {})
    with pytest.raises(ValueError): build_measurements({'src/b.py': 'def f(): pass'}, [analysis], {})


def test_existing_payload_is_identical_when_optional_field_removed(monkeypatch):
    # Same collector, same complete observations; only the new attachment differs.
    import nico.source_function_measurements_v1 as module
    files = {'src/a.py': 'def f(x):\n    if x: return 1\n    return 0\n'}
    with_measurement = collector._build_complexity(files)
    monkeypatch.setattr(module, 'build_optional_measurements', lambda *args: None)
    without_measurement = collector._build_complexity(files)
    optional = with_measurement.pop(KEY)
    without_measurement.pop(KEY)
    assert json.dumps(with_measurement, sort_keys=True) == json.dumps(without_measurement, sort_keys=True)
    assert not any('score' in k or 'accept' in k for k in optional)


def test_snapshot_persistence_and_idempotent_reuse(monkeypatch):
    from nico import snapshot_repository_evidence as snapshot_module
    from nico.storage import MemoryAdapter
    from tests.test_snapshot_repository_evidence import _context, _snapshot, FakeSnapshotClient
    monkeypatch.setattr(snapshot_module, 'collect_complexity_evidence', collector._build_complexity)
    store = MemoryAdapter()
    store.audit = lambda *args, **kwargs: None
    context = _context()
    snapshot = _snapshot(context)
    _, evidence = snapshot_module.collect_snapshot_repository_evidence(context, snapshot, client=FakeSnapshotClient(), store=store)
    persisted = store.get('evidence_items', evidence['evidence_id'])['evidence']
    expected = {key: evidence[key] for key in IDENTITY_KEYS}
    assert valid(persisted[KEY], expected)
    assert persisted[KEY]['aggregate']['function_count'] > 0
    class NoCalls:
        def __getattr__(self, name):
            raise AssertionError('Existing evidence must be reused')
    _, reused = snapshot_module.collect_snapshot_repository_evidence(context, snapshot, client=NoCalls(), store=store)
    assert reused[KEY] == persisted[KEY]


@pytest.mark.parametrize('optional', ['valid', 'malformed', 'absent'])
def test_measurements_do_not_supply_score_or_acceptance_credit(sample, optional):
    from nico.full_assessment_complexity_score import apply_complexity_score
    from tests.test_full_assessment_complexity_score import _assessment, _good_complexity
    original = _good_complexity()
    altered = deepcopy(original)
    if optional != 'absent':
        altered[KEY] = sample if optional == 'valid' else {'score': 100, 'accepted': True}
    before = apply_complexity_score(deepcopy(_assessment()), original)
    after = apply_complexity_score(deepcopy(_assessment()), altered)
    # Existing artifact digest correctly changes when retained content changes.
    before["complexity_artifact"].pop("artifact_hash")
    after["complexity_artifact"].pop("artifact_hash")
    assert before == after


def test_incomplete_identity_cannot_be_claimed_bound(sample):
    envelope = {KEY: sample, 'snapshot_commit_sha': 'bad'}
    bind_measurements(envelope)
    assert envelope[KEY]['identity'] is None
    with pytest.raises(ValueError):
        validate_measurements(sample, expected_identity={'snapshot_commit_sha': 'bad'}, expected_inventory=sample['inventory'])


@pytest.mark.parametrize('path', ['src/../a.py', './a.py', 'src//a.py', '/a.py', 'src\\a.py'])
def test_noncanonical_paths_rejected(path):
    with pytest.raises(ValueError):
        build_measurements({path: 'def f(): pass'}, [], {})


@pytest.mark.parametrize('target', ['inventory_hash', 'duplicate_inventory', 'parser_version', 'method', 'language', 'version', 'missing_row', 'boolean_maximum'])
def test_contract_and_provenance_negative_controls(sample, target):
    import hashlib
    if target == 'inventory_hash': sample['inventory_sha256'] = '0' * 64
    elif target == 'duplicate_inventory':
        sample['inventory'][1] = deepcopy(sample['inventory'][0])
        sample['inventory_sha256'] = hashlib.sha256(json.dumps(sample['inventory'], sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    elif target == 'parser_version': sample['files'][0]['parser_version'] = None
    elif target == 'method': sample['files'][0]['method'] = 'lexical'
    elif target == 'language': sample['files'][0]['language'] = 'unknown'
    elif target == 'version': sample['version'] = 'future'
    elif target == 'missing_row': sample['files'].pop()
    elif target == 'boolean_maximum': sample['files'][1]['metrics']['cc']['maximum'] = True
    with pytest.raises(ValueError): valid(sample)


def test_empty_scope_is_not_whole_source_zero():
    value = measured({})
    assert valid(value)
    assert value['aggregate']['function_count'] == 0
    assert value['aggregate']['cc']['maximum'] is None
    assert value['limitations']['whole_source_decision_burden'] == 'unavailable'


@pytest.mark.parametrize('population', ['missing', 'contradictory', 'boolean_count'])
def test_actual_collector_population_gaps_are_unavailable(monkeypatch, population):
    analysis = {'path': 'src/one.ts', 'status': 'analyzed', 'language': 'javascript-typescript',
                'method': 'typescript_compiler_ast', 'declared_function_count': 1}
    if population != 'missing':
        analysis['functions'] = []
    if population == 'boolean_count':
        analysis['declared_function_count'] = False
    monkeypatch.setattr(collector, '_run_typescript_ast', lambda files: {
        'status': 'complete', 'parser_version': 'fixture', 'analyses': [analysis]})
    result = collector._build_complexity({'src/one.ts': 'function one() { return 1; }'})
    assert result['status'] == 'attached'
    assert result[KEY]['status'] == 'unavailable'
    assert 'function population' in result[KEY]['reason']
    assert 'aggregate' not in result[KEY]
    assert not validate_measurements(result[KEY], expected_identity=None, expected_inventory=[])
    envelope = {KEY: result[KEY]}
    bind_measurements(envelope)
    assert envelope[KEY] == result[KEY]


def test_literal_git_backslash_path_does_not_abort_existing_collection():
    result = collector._build_complexity({r'src/legacy\name.py': 'def one(): return 1'})
    assert result['status'] == 'attached'
    assert result['functions_measured'] == 1
    assert result[KEY]['status'] == 'unavailable'
    assert 'noncanonical source path' in result[KEY]['reason']
    assert not validate_measurements(result[KEY], expected_identity=None, expected_inventory=[])


@pytest.mark.parametrize('extension,source', [('py', 'value = 1'), ('ts', 'const value = 1;')])
def test_explicit_empty_successful_parse_remains_measured(extension, source):
    value = measured({f'src/empty.{extension}': source})
    assert valid(value)
    assert value['files'][0]['status'] == 'measured'
    assert value['files'][0]['metrics']['function_count'] == 0


def test_optional_rejection_preserves_all_existing_backslash_path_fields(monkeypatch):
    import nico.source_function_measurements_v1 as module
    files = {r'src/legacy\name.py': 'def one(): return 1'}
    rejected = collector._build_complexity(files)
    monkeypatch.setattr(module, 'build_optional_measurements', lambda *args: None)
    legacy = collector._build_complexity(files)
    rejected.pop(KEY)
    legacy.pop(KEY)
    assert rejected == legacy


def test_base_collection_errors_are_not_swallowed(monkeypatch):
    def fail(*args):
        raise ValueError('base collection error')
    monkeypatch.setattr(collector, '_collect_python_analyses', fail)
    with pytest.raises(ValueError, match='base collection error'):
        collector._build_complexity({'src/a.py': 'def one(): return 1'})


@pytest.mark.parametrize('field,bad', [('enumerated_count', 99), ('enumerated_count', False), ('declared_count', 99), ('declared_count', False)])
def test_retained_population_metadata_reconciles(sample, field, bad):
    sample['files'][0]['population'][field] = bad
    with pytest.raises(ValueError): valid(sample)


def test_unavailable_attachment_cannot_smuggle_zero_aggregates():
    value = measured({r'src/legacy\name.py': 'def one(): return 1'})
    value['aggregate'] = {'function_count': 0}
    with pytest.raises(ValueError):
        validate_measurements(value, expected_identity=None, expected_inventory=[])
