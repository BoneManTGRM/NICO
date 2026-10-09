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
def test_real_cli_collection_gate_retains_failure_and_reports_safe_counts(tmp_path, monkeypatch, capsys, rejected):
    from nico import assessment_cpp_configuration_probe as probe_module
    from nico import assessment_cpp_runtime_scope as runtime_module
    from nico.assessment_cpp_collection import validate_project_collection
    from tests.test_cpp_completed_collection_projection import qualification_bundle

    receipt, read, kwargs, artifacts = qualification_bundle(tmp_path)
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
