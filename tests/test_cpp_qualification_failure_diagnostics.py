"""Owned diagnostic controls; no native qualification or remote execution."""
from copy import deepcopy
import json
import subprocess
import sys

import pytest

from scripts import qualify_cpp_project_configuration as cli


def test_failure_summary_reports_only_retained_counts_and_known_codes():
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    evidence = {'probe': {
        'error': 'worker_configuration_probe_compiler_incomplete',
        'independent_collection_error': 'worker_configuration_probe_static_incomplete',
        'project_static_stage': {'error': 'worker_project_static_stage_deadline'},
        'project_static': {'required_contexts_count': 3, 'attempted_contexts_count': 1,
            'analyzed_contexts_count': 0, 'header_population_count': 4,
            'header_unvisited_files_count': 3,
            'clang_fallback': {'required_contexts': ['owned'], 'attempted_contexts': [],
                               'analyzed_contexts': []}}}}
    before = deepcopy(evidence)
    result = failure_diagnostic(evidence, ValueError('qualification_collection_invalid'))
    assert evidence == before
    assert result['qualification_error'] == 'qualification_collection_invalid'
    assert result['independent_collection_error'] == 'worker_configuration_probe_static_incomplete'
    assert result['static_stage_error'] == 'worker_project_static_stage_deadline'
    assert result['retained_counts']['static'] == {'required': 3, 'attempted': 1, 'analyzed': 0}
    assert result['retained_counts']['headers'] == {'population': 4, 'unvisited': 3}
    assert result['retained_counts']['clang_fallback'] == {'required': 1, 'attempted': 0, 'analyzed': 0}
    assert all(v is None for v in result['retained_counts']['compiler_collection'].values())


@pytest.mark.parametrize('bad', [None, True, -1, 1.5, '17', 1000001, 10**1000, [], {}])
def test_invalid_counts_stay_unknown(bad):
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    result = failure_diagnostic({'probe': {'project_static': {'required_contexts_count': bad}}},
                                ValueError('qualification_collection_invalid'))
    assert result['retained_counts']['static']['required'] is None


@pytest.mark.parametrize('bad', [None, [], 'secret', 0, True])
def test_missing_or_invalid_nested_fields_do_not_break_diagnostics(bad):
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    result = failure_diagnostic({'probe': {'project_static': bad, 'runtime_evidence': bad,
        'project_static_stage': bad, 'project_compiler_collection': bad}}, RuntimeError('secret'))
    assert result['qualification_error'] == 'unrecognized_error'
    assert result['runtime_error'] is None
    assert all(v is None for group in result['retained_counts'].values() for v in group.values())
    assert failure_diagnostic(bad, KeyboardInterrupt())['qualification_error'] == 'qualification_interrupted'


def test_untrusted_fields_are_excluded_and_output_is_bounded():
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    secret = 'private-source https://example.invalid/?token=SECRET\n::error::injected' * 10000
    result = failure_diagnostic({'source': secret, 'error': secret, 'probe': {
        'error': secret, 'independent_collection_error': 'worker_configuration_probe_secret',
        'operations': [secret], 'runtime_evidence': {'error': [secret], 'output': secret},
        'project_static_stage': {'error': {'secret': secret}},
        'project_static': {'required_contexts_count': 1000000, 'findings': [secret],
            'header_population': {secret: secret}, 'clang_fallback': {
                'required_contexts': [secret], 'attempted_contexts': secret}}}}, ValueError(secret))
    encoded = json.dumps(result)
    assert len(encoded.encode()) < 4096
    for forbidden in ('SECRET', 'private-source', 'https://', '::error::', 'worker_configuration_probe_secret'):
        assert forbidden not in encoded
    assert result['retained_counts']['clang_fallback']['required'] == 1
    assert result['retained_counts']['clang_fallback']['attempted'] is None
    assert result['qualification_error'] == result['independent_collection_error'] == 'unrecognized_error'


def test_original_exception_and_exit_status_survive_diagnostic_failure(monkeypatch, capsys):
    original = ValueError('qualification_collection_invalid')
    def fail(*args):
        raise original
    monkeypatch.setattr(cli, '_qualify_configuration_checkout', fail)
    with pytest.raises(ValueError) as caught:
        cli.qualify_configuration_checkout(None)
    assert caught.value is original
    assert json.loads(capsys.readouterr().out)['qualification_error'] == str(original)
    monkeypatch.setattr(cli, 'failure_diagnostic', fail)
    with pytest.raises(ValueError) as caught:
        cli.qualify_configuration_checkout(None)
    assert caught.value is original
    result = subprocess.run([sys.executable, '-c',
        'from scripts import qualify_cpp_project_configuration as c; '
        'c._qualify_configuration_checkout=lambda *a: (_ for _ in ()).throw(ValueError("qualification_collection_invalid")); '
        'c.qualify_configuration_checkout(None)'], capture_output=True, text=True)
    assert result.returncode == 1
    assert json.loads(result.stdout)['qualification_error'] == 'qualification_collection_invalid'


@pytest.mark.parametrize('exception', [
    'ValueError("https://example.invalid/?token=PRIVATE_SOURCE")',
    'RuntimeError("PRIVATE_SOURCE")', 'KeyboardInterrupt("PRIVATE_SOURCE")',
])
def test_executable_cli_suppresses_raw_tracebacks_without_changing_exit_status(exception):
    baseline = subprocess.run([sys.executable, '-c', 'raise '+exception], capture_output=True)
    # Fail during owned output preparation, before any source or tool runs.
    harness = '''
import argparse, runpy, types
class Output:
    def mkdir(self, **kwargs):
        raise EXCEPTION
argparse.ArgumentParser.parse_args = lambda self: types.SimpleNamespace(output=Output())
runpy.run_module('scripts.qualify_cpp_project_configuration', run_name='__main__')
'''.replace('EXCEPTION', exception)
    result = subprocess.run([sys.executable, '-c', harness], capture_output=True, text=True)
    assert result.returncode == baseline.returncode != 0
    assert result.stderr == ''
    assert 'PRIVATE_SOURCE' not in result.stdout and 'https://' not in result.stdout
    summary = json.loads(result.stdout)
    assert summary['qualification_error'] == (
        'qualification_interrupted' if exception.startswith('KeyboardInterrupt') else 'unrecognized_error')
    assert all(value is None for group in summary['retained_counts'].values() for value in group.values())


def test_embedded_cli_hook_delegates_unrelated_exceptions():
    harness = '''
import argparse, runpy, sys, types
seen = []
sys.excepthook = lambda kind, value, trace: seen.append(value)
class Output:
    def mkdir(self, **kwargs):
        raise ValueError('PRIVATE_SOURCE')
argparse.ArgumentParser.parse_args = lambda self: types.SimpleNamespace(output=Output())
try:
    runpy.run_module('scripts.qualify_cpp_project_configuration', run_name='__main__')
except ValueError as failure:
    sys.excepthook(type(failure), failure, failure.__traceback__)
    assert not seen
unrelated = RuntimeError('unrelated')
sys.excepthook(type(unrelated), unrelated, None)
assert seen == [unrelated]
'''
    result = subprocess.run([sys.executable, '-c', harness], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stderr == '' and 'PRIVATE_SOURCE' not in result.stdout


@pytest.mark.parametrize('rejected', [False, True])
@pytest.mark.parametrize('diagnostic_fault', [False, True])
def test_real_cli_collection_gate_retains_failure_and_reports_safe_counts(tmp_path, monkeypatch, capsys, rejected, diagnostic_fault):
    from nico import assessment_cpp_configuration_probe as probe_module
    from nico import assessment_cpp_runtime_scope as runtime_module
    from nico.assessment_cpp_collection import validate_project_collection
    from tests.test_cpp_completed_collection_projection import qualification_bundle

    receipt, read, kwargs, artifacts = qualification_bundle(tmp_path)
    if diagnostic_fault:
        monkeypatch.setattr(cli, 'public_paths_after_freeze',
                            lambda *a: (_ for _ in ()).throw(RuntimeError('SECRET')))
    assert validate_project_collection(receipt, read, **kwargs)['collection_complete'] is True
    runtime = json.loads(read(receipt['runtime']['artifact']))
    probe = deepcopy(receipt['probe'])
    probe['runtime_evidence'] = runtime['evidence']
    # Already-projected nested collections must not be projected twice by the
    # replay. Source/native operations are substituted; final gate stays real.
    def replay_projection(value):
        projected = deepcopy(value)
        projected['runtime_evidence'] = deepcopy(receipt['probe']['runtime_evidence'])
        return projected
    monkeypatch.setattr(cli, 'qualification_probe_receipt', replay_projection)
    if rejected:
        probe['independent_collection_error'] = 'worker_configuration_probe_static_incomplete'
    def replay(*args, **options):
        options['retain'](deepcopy(probe))
        return deepcopy(probe)
    monkeypatch.setattr(cli, 'freeze_configuration_checkout', lambda *a: deepcopy(receipt['source']))
    monkeypatch.setattr(runtime_module, 'capture_runtime_interfaces', lambda *a: deepcopy(runtime['interfaces']))
    monkeypatch.setattr(probe_module, 'probe_project_configuration', replay)
    output = tmp_path/'retained'
    for name, raw in artifacts.items():
        path = output/name; path.parent.mkdir(parents=True, exist_ok=True); path.write_bytes(raw)
    argv = ['qualify', '--image', kwargs['image'], '--qualification-source', 'unused-owned-source',
        '--output', str(output), '--accept-completed-collection', '--producer-source-sha', kwargs['producer_source_sha']]
    for flag in ('capture-generated-context', 'project-compiler-evidence', 'project-static-analysis',
                 'extended-compiler-budget', 'compiler-environment', 'capture-enabled-targets',
                 'capture-native-commands', 'materialize-generated-inputs', 'collect-completed-compiler-failures'):
        argv.append('--'+flag)
    for option, key in [('qualification-manifest', 'manifest_raw'),
                        ('baseline-execution-contract', 'baseline_raw'), ('runtime-scope-contract', 'scope_raw')]:
        path = tmp_path/(option+'.json'); path.write_bytes(kwargs[key]); argv += ['--'+option, str(path)]
    monkeypatch.setattr(sys, 'argv', argv)
    if rejected:
        with pytest.raises(ValueError, match='^qualification_collection_invalid$'):
            cli.main()
    else:
        cli.main()
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    summaries = [line for line in lines if line.get('schema') == 'nico.cpp-qualification-failure-diagnostic.v1']
    assert (output/'collection-acceptance.json').exists() is (not rejected)
    saved = json.loads((output/'receipt.json').read_bytes())
    assert saved['probe']['error'] == 'worker_configuration_probe_compiler_incomplete'
    assert saved['probe']['project_compiler_collection']['failed_contexts_count'] == 1
    assert saved['production_qualified'] is False
    if rejected:
        assert len(summaries) == 1
        diagnostic = summaries[0]
        assert diagnostic['independent_collection_error'] == 'worker_configuration_probe_static_incomplete'
        assert diagnostic['retained_counts']['static'] == {'required': 2, 'attempted': 2, 'analyzed': 1}
        assert diagnostic['retained_counts']['compiler_collection']['failed'] == 1
        assert len(json.dumps(diagnostic)) < 4096
    else:
        assert not summaries


def test_primary_diagnostics_and_sanitizer_operation_are_bounded_observations():
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    probe = {'project_static': {'primary_diagnostics': {
        'wall_duration_ms': 540001, 'execution_duration_ms': 1079999,
        'max_execution_duration_ms': 90001, 'executions': 13, 'analyzed': 1,
        'missing_execution': 564, 'timed_out': 2, 'nonzero_exit': 3,
        'output_truncated': 0, 'record_error': 564, 'syntax_error': 1,
        'internal_ast_error': 2, 'path': '/private/secret'}},
        'runtime_summary': {'first_failure_operation': 'runtime-address-tests',
                            'failure_operation': 'runtime-undefined-build'}}
    result = failure_diagnostic({'probe': probe}, ValueError('qualification_collection_invalid'))
    assert result['primary_diagnostics'] == {k: v for k, v in probe['project_static']['primary_diagnostics'].items() if k != 'path'}
    assert result['sanitizer_failure'] == {
        'first_failure_operation': {'kind': 'address', 'phase': 'tests'},
        'failure_operation': {'kind': 'undefined', 'phase': 'build'}}
    assert '/private' not in json.dumps(result)
    assert len(json.dumps(result)) < 4096


@pytest.mark.parametrize('bad', [True, -1, 'secret', [], {}, 100000001, float('nan'), float('inf')])
def test_primary_timings_and_runtime_operations_reject_invalid_scalars(bad):
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    result = failure_diagnostic({'probe': {
        'project_static': {'primary_diagnostics': {'wall_duration_ms': bad}},
        'runtime_summary': {'first_failure_operation': bad, 'failure_operation': bad}}},
        ValueError('qualification_collection_invalid'))
    assert result['primary_diagnostics']['wall_duration_ms'] is None
    assert set(result['sanitizer_failure'].values()) == {None}


def test_generic_sanitizer_failure_does_not_invent_kind_or_phase():
    from scripts.cpp_qualification_diagnostics import failure_diagnostic
    result = failure_diagnostic({'probe': {'runtime_evidence': {
        'error': 'worker_runtime_sanitizer_failed'}}}, ValueError('qualification_collection_invalid'))
    assert set(result['sanitizer_failure'].values()) == {None}


def _diagnostic_execution(raw, **changes):
    import base64
    import hashlib
    return {'exit_code': 1, 'timed_out': False, 'output_truncated': False,
            'duration_ms': 1, 'output': base64.b64encode(raw).decode(),
            'output_sha256': hashlib.sha256(raw).hexdigest(), **changes}


def _diagnostic_compiler(records):
    import hashlib
    raw = json.dumps({'schema': 'nico.cpp-project-compiler-evidence.v2', 'records': records}).encode()
    sha = hashlib.sha256(raw).hexdigest()
    proof = {'native_evidence_sha256': sha, 'required_contexts': [r['context_id'] for r in records],
             'artifact': {'path': 'artifacts/project-compiler-evidence-' + sha + '.json',
                          'sha256': sha, 'bytes': len(raw)}}
    return proof, lambda path, limit: raw


def test_public_authority_requires_exact_manifest_and_live_freeze_identity():
    from scripts import cpp_qualification_diagnostic_details as d
    source = {'repository': 'bitcoin/bitcoin', 'commit_sha': d.PUBLIC_COMMIT,
              'tree_sha': d.PUBLIC_TREE, 'inventory_complete': True,
              'targets': {'src/test/a.cpp': 'digest', 'src/../SECRET.cpp': 'digest',
                          '/src/private.cpp': 'digest'}}
    assert d.public_paths_after_freeze(d.PUBLIC_MANIFEST_SHA256, source) == {'src/test/a.cpp'}
    assert not d.public_paths_after_freeze('0' * 64, source)
    for key, wrong in [('repository', 'private/SECRET'), ('commit_sha', '0' * 40),
                       ('tree_sha', '0' * 40), ('inventory_complete', False)]:
        assert not d.public_paths_after_freeze(d.PUBLIC_MANIFEST_SHA256, {**source, key: wrong})
    # A retained receipt-shaped object cannot populate the live context.
    summary = d.add_failure_details({'source': 'fixed aggregate placeholder'}, {}, lambda *a: b'')
    assert summary['details']['compiler']['state'] == 'unavailable'


@pytest.mark.parametrize('line', [
    '/private/src/test/a.cpp:1:2: error: SECRET',
    '/work/source/src/../test/a.cpp:1:2: error: SECRET',
    '/work/source/src/test/SECRET.cpp:1:2: error: SECRET',
    'message /work/source/src/test/a.cpp:1:2: error: SECRET',
    '/work/source/src/test/a.cpp:123456789:2: error: SECRET',
    '/work/source/src/test/a.cpp:1:2: error: \x1b[31mSECRET',
    '/work/source/src/test/a.cpp:1:2: error: ' + 'SECRET' * 1000,
    'src/test/a.cpp:1:2: unexpected: SECRET',
])
def test_detail_locations_reject_hostile_or_unbound_lines(line):
    from scripts.cpp_qualification_diagnostic_details import locations
    assert locations(line.encode(), {'src/test/a.cpp'}) == {'locations': [], 'locations_omitted': 0}


def test_detail_locations_strip_messages_and_bound_selection():
    from scripts.cpp_qualification_diagnostic_details import locations
    raw = b'/work/source/src/test/a.cpp:12:7: runtime error: signed integer overflow: SECRET\n' * 20
    result = locations(raw, {'src/test/a.cpp'})
    assert len(result['locations']) == 8 and result['locations_omitted'] == 12
    assert result['locations'][0] == {'path': 'src/test/a.cpp', 'line': 12, 'column': 7,
                                      'observed_category': 'signed_integer_overflow'}
    assert 'SECRET' not in json.dumps(result)
    assert locations(raw, frozenset())['locations'] == []


def test_compiler_details_keep_failed_record_indexes_and_omissions():
    from scripts.cpp_qualification_diagnostic_details import compiler_details
    records = [{'context_id': str(i), 'error': 'SECRET',
                'execution': _diagnostic_execution(b'src/test/a.cpp:2:3: error: SECRET')}
               for i in range(20)]
    records.insert(0, {'context_id': 'ok', 'error': None,
                      'execution': _diagnostic_execution(b'', exit_code=0)})
    proof, read = _diagnostic_compiler(records)
    result = compiler_details(proof, read, {'src/test/a.cpp'})
    assert result['failed_records'] == 20 and result['omitted'] == 4
    assert result['records'][0]['context_index'] == 1
    assert 'SECRET' not in json.dumps(result)
    assert result['records'][0]['locations'][0]['path'] == 'src/test/a.cpp'


@pytest.mark.parametrize('fault', ['hash', 'size', 'path', 'population', 'duplicate_json',
                                 'oversize', 'base64', 'output_hash', 'non_utf8'])
def test_compiler_corrupt_details_fail_closed(fault):
    from scripts.cpp_qualification_diagnostic_details import add_failure_details, MAX_ARTIFACT_BYTES
    row = {'context_id': 'a', 'error': 'SECRET', 'execution': _diagnostic_execution(b'SECRET')}
    if fault == 'base64': row['execution']['output'] = 'SECRET%'
    if fault == 'output_hash': row['execution']['output_sha256'] = '0' * 64
    if fault == 'non_utf8': row['execution'] = _diagnostic_execution(b'\xffSECRET')
    proof, read = _diagnostic_compiler([row])
    if fault == 'hash': proof['native_evidence_sha256'] = '0' * 64
    if fault == 'size': proof['artifact']['bytes'] += 1
    if fault == 'path': proof['artifact']['path'] = '../SECRET'
    if fault == 'population': proof['required_contexts'] = ['wrong']
    if fault == 'oversize': proof['artifact']['bytes'] = MAX_ARTIFACT_BYTES + 1
    if fault == 'duplicate_json':
        import hashlib
        raw = b'{"records":[],"records":[],"SECRET":true}'
        sha = hashlib.sha256(raw).hexdigest()
        proof.update(native_evidence_sha256=sha, artifact={
            'path': 'artifacts/project-compiler-evidence-' + sha + '.json', 'bytes': len(raw), 'sha256': sha})
        read = lambda *a: raw
    result = add_failure_details({'qualification_error': 'qualification_collection_invalid'},
                                 {'compiler': proof}, read)
    assert result['details']['compiler']['state'] == 'unavailable'
    assert result['qualification_error'] == 'qualification_collection_invalid'
    assert 'SECRET' not in json.dumps(result)


def test_validated_runtime_details_keep_opaque_failed_test_identity(tmp_path):
    import hashlib
    from scripts.cpp_qualification_diagnostic_details import runtime_details
    from tests.test_cpp_runtime_collection import fixture
    from nico.assessment_cpp_runtime_scope import validate_retained_runtime
    retained, targets, options, scope = fixture(tmp_path)
    runtime = retained['evidence']
    log = next(row for row in runtime['failure_diagnostics'] if row['kind'] == 'undefined')
    from tests.test_cpp_completed_sanitizer_failure_collection import envelope
    execution = _diagnostic_execution(envelope(b'src/test/a.cpp:3:4: runtime error: load of null pointer SECRET'), exit_code=0)
    log['log_read'].update(execution)
    # All plan, discovery, JUnit, log and operation bindings remain real validators.
    validated = validate_retained_runtime(json.dumps(retained).encode(), targets, options, scope)
    assert validated['summary']['complete'] is False
    result = runtime_details(runtime, {'src/test/a.cpp'})
    row = result['sanitizers'][0]
    assert row['kind'] == 'undefined' and row['phase'] == 'tests'
    assert row['tests'] == [{'population_index': 0, 'name_sha256': hashlib.sha256(b'unit_a').hexdigest()}]
    assert row['locations'][0]['observed_category'] == 'null_pointer'
    assert 'unit_a' not in json.dumps(result) and 'SECRET' not in json.dumps(result)
    assert runtime_details(runtime, frozenset())['sanitizers'][0]['locations'] == []


def test_complete_diagnostic_record_budget_and_original_failure(monkeypatch, capsys):
    from scripts import cpp_qualification_diagnostic_details as d
    # Final cap applies to aggregates plus details, including future additions.
    result = d.add_failure_details({'fixed': 'x' * (d.MAX_RECORD_BYTES - 100)}, {}, lambda *a: b'')
    assert result['details']['state'] == 'output_budget_exceeded'
    assert len(json.dumps(result, separators=(',', ':')).encode()) <= d.MAX_RECORD_BYTES
    original = ValueError('qualification_collection_invalid')
    def fail(args, evidence, context):
        context['public_paths'] = frozenset()
        raise original
    monkeypatch.setattr(cli, '_qualify_configuration_checkout', fail)
    monkeypatch.setattr(cli, 'add_failure_details', lambda *a: (_ for _ in ()).throw(RuntimeError('SECRET')))
    with pytest.raises(ValueError) as caught:
        cli.qualify_configuration_checkout(None)
    assert caught.value is original
    result = json.loads(capsys.readouterr().out)
    assert result['qualification_error'] == str(original)
    assert result['details'] == {'state': 'unavailable'}
    assert 'SECRET' not in json.dumps(result)


def test_forged_receipt_public_identity_does_not_enable_details(monkeypatch, capsys):
    from scripts import cpp_qualification_diagnostic_details as d
    def fail(args, evidence, context):
        evidence.update(benchmark_sha256=d.PUBLIC_MANIFEST_SHA256, source={
            'repository': 'bitcoin/bitcoin', 'commit_sha': d.PUBLIC_COMMIT,
            'tree_sha': d.PUBLIC_TREE, 'inventory_complete': True,
            'targets': {'src/SECRET.cpp': '0' * 64}})
        raise ValueError('qualification_collection_invalid')
    monkeypatch.setattr(cli, '_qualify_configuration_checkout', fail)
    with pytest.raises(ValueError): cli.qualify_configuration_checkout(None)
    result = json.loads(capsys.readouterr().out)
    assert 'details' not in result and 'SECRET' not in json.dumps(result)


def test_runtime_private_names_are_digest_only_and_selection_is_bounded():
    import hashlib
    from scripts.cpp_qualification_diagnostic_details import runtime_details
    names = ['SECRET\n::error::injected' + str(i) for i in range(20)]
    runtime = {'sanitizers': [{'kind': 'undefined', 'tests': _diagnostic_execution(b''),
                              'results': {'required': names, 'executed': names, 'passed': []}}]}
    result = runtime_details(runtime, frozenset())['sanitizers'][0]
    assert result['failed_tests'] == 20 and result['omitted'] == 4
    assert result['tests'][0] == {'population_index': 0,
                                 'name_sha256': hashlib.sha256(names[0].encode()).hexdigest()}
    assert 'SECRET' not in json.dumps(result) and '::error::' not in json.dumps(result)


@pytest.mark.parametrize('raw', [b'\xff', b'x' * (1024 * 1024 + 1)])
def test_unparseable_logs_do_not_emit_partial_locations(raw):
    from scripts.cpp_qualification_diagnostic_details import locations
    with pytest.raises((ValueError, UnicodeError)):
        locations(raw, {'src/test/a.cpp'})


@pytest.mark.parametrize('fault', ['missing', 'failed', 'truncated', 'inner_truncated', 'corrupt'])
def test_runtime_missing_log_preserves_test_identity_and_unknown_results(fault):
    import base64
    from scripts.cpp_qualification_diagnostic_details import runtime_details
    read = _diagnostic_execution(b'', exit_code=0)
    if fault == 'failed': read['exit_code'] = 1
    if fault == 'truncated': read['output_truncated'] = True
    if fault == 'inner_truncated':
        read = _diagnostic_execution(json.dumps({'data': '', 'truncated': True}).encode(), exit_code=0)
    if fault == 'corrupt': read['output'] = base64.b64encode(b'SECRET').decode()
    runtime = {'sanitizers': [{'kind': 'undefined', 'tests': _diagnostic_execution(b'', timed_out=True),
                'results': None}], 'failure_diagnostics': [{'kind': 'undefined',
                'log_read': None if fault == 'missing' else read}]}
    row = runtime_details(runtime, frozenset())['sanitizers'][0]
    assert row['outcome'] == 'timed_out' and row['results_state'] == 'unavailable'
    assert row['failed_tests'] is None and row['omitted'] is None
    assert row['locations_state'] == ('truncated' if 'truncated' in fault else 'unavailable')
    runtime['sanitizers'][0]['results'] = {'required': ['SECRET'], 'executed': ['SECRET'], 'passed': []}
    row = runtime_details(runtime, frozenset())['sanitizers'][0]
    assert row['failed_tests'] == 1 and len(row['tests']) == 1
    assert 'SECRET' not in json.dumps(row)


def test_public_manifest_pin_matches_owned_fixture_and_warnings_do_not_hide_errors():
    import hashlib
    from pathlib import Path
    from scripts import cpp_qualification_diagnostic_details as d
    raw = (Path(__file__).parent/'fixtures/cpp/bitcoin-configuration-benchmark.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == d.PUBLIC_MANIFEST_SHA256
    raw = b'src/test/a.cpp:1:1: warning: SECRET\n' * 20 + b'src/test/a.cpp:9:2: fatal error: SECRET\n'
    result = d.locations(raw, {'src/test/a.cpp'})
    assert result['locations'] == [{'path': 'src/test/a.cpp', 'line': 9, 'column': 2,
                                    'observed_category': 'compiler_fatal_error'}]
    assert result['locations_omitted'] == 0
