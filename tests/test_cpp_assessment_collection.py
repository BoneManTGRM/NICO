"""Collection decisions from owned retained bytes, never native qualification."""
from copy import deepcopy
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from nico.assessment_cpp_collection import validate_baseline_collection, validate_project_collection
from nico.assessment_worker_receipts import canonical_bytes
from tests.test_cpp_baseline_execution import Native, contract, execute


def no_artifacts(ref):
    raise AssertionError('the baseline fixture has no external artifacts')


def replace_output(row, raw):
    row.update(output=base64.b64encode(raw).decode(), output_sha256=hashlib.sha256(raw).hexdigest())


def envelope(raw):
    return canonical_bytes({'data': base64.b64encode(raw).decode(), 'truncated': False})


def test_baseline_acceptance_reconstructs_actual_probe_membership_without_mutation(tmp_path):
    probe, _, _ = execute(tmp_path)
    before = deepcopy(probe)
    result = validate_baseline_collection(probe, contract(), no_artifacts)
    assert result == {'required': ['owned_suite'], 'executed': ['owned_suite'], 'passed': ['owned_suite'], 'skipped': []}
    assert probe == before


@pytest.mark.parametrize('fault', ['drop_membership', 'filter_argv', 'timeout', 'truncated_transport',
    'truncated_junit', 'missing_test', 'skip', 'failed_exit', 'digest', 'junit_mismatch', 'contract',
    'post_build_database', 'raw_boundary', 'build_deadline'])
def test_baseline_rejects_incomplete_or_unbound_native_results(tmp_path, fault):
    probe, _, _ = execute(tmp_path)
    spec = contract()
    ops = {row['id']: row for row in probe['operations']}
    if fault == 'drop_membership': probe['tests_result']['executed'] = []
    elif fault == 'filter_argv': ops['baseline-tests']['invocation'] += ['-R', 'passing_only']
    elif fault == 'timeout': ops['baseline-tests']['timed_out'] = True
    elif fault == 'truncated_transport': ops['baseline-junit']['output_truncated'] = True
    elif fault == 'truncated_junit':
        v = json.loads(base64.b64decode(ops['baseline-junit']['output'])); v['truncated'] = True
        replace_output(ops['baseline-junit'], canonical_bytes(v))
    elif fault == 'failed_exit': ops['baseline-tests']['exit_code'] = 8
    elif fault == 'post_build_database': replace_output(ops['post-build-database'], envelope(b'[]'))
    elif fault == 'raw_boundary':
        boundary = json.loads(base64.b64decode(ops['boundary-after']['output'])); boundary['source_read_only'] = False
        replace_output(ops['boundary-after'], canonical_bytes(boundary))
    elif fault == 'build_deadline': ops['baseline-build']['duration_ms'] = (spec['build_seconds']+6)*1000
    elif fault == 'digest': ops['baseline-test-discovery']['output_sha256'] = '0'*64
    elif fault == 'contract': spec['parallel'] = 1
    elif fault == 'junit_mismatch': probe['tests_result']['junit'] = base64.b64encode(b'<testsuite tests="0"/>').decode()
    elif fault in ('missing_test', 'skip'):
        raw = (b'<testsuite tests="0"/>' if fault == 'missing_test' else
               b'<testsuite tests="1"><testcase name="owned_suite"><skipped/></testcase></testsuite>')
        replace_output(ops['baseline-junit'], envelope(raw))
        probe['tests_result']['junit'] = base64.b64encode(raw).decode()
    with pytest.raises(ValueError):
        validate_baseline_collection(probe, spec, no_artifacts)


def test_empty_baseline_cannot_be_relabelled_as_a_full_test_population(tmp_path):
    probe, _, _ = execute(tmp_path)
    ops = {row['id']: row for row in probe['operations']}
    discovery = canonical_bytes({'kind': 'ctestInfo', 'version': {'major': 1, 'minor': 0}, 'tests': []})
    replace_output(ops['baseline-test-discovery'], discovery)
    probe.update(tests_discovered=[], native_test_discovery=base64.b64encode(discovery).decode())
    junit = b'<testsuite tests="0"/>'
    replace_output(ops['baseline-junit'], envelope(junit))
    probe['tests_result'].update(executed=[], passed=[], skipped=[], junit=base64.b64encode(junit).decode())
    with pytest.raises(ValueError):
        validate_baseline_collection(probe, contract(), no_artifacts)


def bundle(tmp_path, *, kind='undefined'):
    """The real producer creates every transport row; only Docker is substituted."""
    from nico.assessment_cpp_configuration_probe import probe_project_configuration, READ_PROGRAM
    from nico.assessment_cpp_project_compiler import PROGRAM as COMPILER_PROGRAM
    from nico.assessment_cpp_runtime_scope import retained_runtime_bytes, validate_retained_runtime
    from scripts.qualify_cpp_project_configuration import persist_project_artifact, qualification_probe_receipt
    from tests.test_cpp_project_compiler import inputs
    from tests.test_cpp_compiler_budget_v2 import native_result
    from tests.test_cpp_static_environment_integration import EnvironmentDocker
    from tests.test_cpp_runtime_collection import fixture as runtime_fixture
    from nico.assessment_cpp_full_project import compilation_contexts
    from nico.assessment_cpp_project_snapshot import (capture_project_snapshot, project_snapshot_request,
        PROJECT_SNAPSHOT_PROGRAM)

    generated = tmp_path/'generated'; generated.mkdir()
    database, compiler_targets, _, _ = inputs(generated)
    runtime_dir = tmp_path/'runtime'; runtime_dir.mkdir()
    retained, targets, options, scope = runtime_fixture(runtime_dir, kind=kind)
    targets.update(compiler_targets)
    snapshot = capture_project_snapshot(generated/'build', generated/'private'/'combined',
        project_snapshot_request(compilation_contexts(database, targets, '/work/build')))
    root = runtime_dir/'source'
    (root/'main.cpp').write_bytes(b'#include "config.h"\nint main(){return VALUE;}\n')
    (root/'original.h').write_bytes(b'#define ORIGINAL 1\n')
    baseline = contract(); baseline['compilation_database_sha256'] = hashlib.sha256(database).hexdigest()
    runtime_operations = []
    def capture_runtime(value):
        if isinstance(value, dict):
            if 'id' in value and 'argv' in value: runtime_operations.append(value)
            else:
                for child in value.values(): capture_runtime(child)
        elif isinstance(value, list):
            for child in value: capture_runtime(child)
    capture_runtime(retained['evidence'])

    class WholeNative(Native):
        def __init__(self):
            super().__init__(targets)
            self.static = EnvironmentDocker(targets)
        def __call__(self, args, **kwargs):
            # The real producer chooses which sandbox runs each command.
            if any(arg.startswith('nico-project-static-') for arg in args):
                return self.static(args, **kwargs)
            for operation in runtime_operations:
                argv = operation['argv']
                if args[-len(argv):] == argv:
                    self.calls.append((args, kwargs))
                    return {**{key: operation[key] for key in ('exit_code', 'timed_out', 'output_truncated')},
                            'output': base64.b64decode(operation['output'])}
            if READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
                self.calls.append((args, kwargs)); raw = envelope(database)
            elif PROJECT_SNAPSHOT_PROGRAM in args:
                self.calls.append((args, kwargs)); raw = canonical_bytes(snapshot)
            elif COMPILER_PROGRAM in args:
                self.calls.append((args, kwargs)); raw = canonical_bytes(native_result(json.loads(kwargs['input_bytes'])))
            else:
                return super().__call__(args, **kwargs)
            return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'output': raw}

    output = tmp_path/'retained'; output.mkdir()
    def retain(key, raw):
        return persist_project_artifact(output, key, raw)
    image = 'sha256:'+'a'*64
    probe = probe_project_configuration(root, targets, image, project_options=options,
        baseline_execution=baseline, command=WholeNative(), capture_generated_context=True,
        project_compiler_evidence=True, project_static_analysis=True, extended_compiler_budget=True,
        compiler_environment=True, runtime_plan=retained['plan'], retain_artifact=retain)
    assert probe['tests_passed'] is True, probe['error']
    assert probe['project_static_stage']['complete'] is True, probe['project_static_stage']['error']
    assert probe['runtime_summary']['complete'] is (kind is None)
    runtime_raw = retained_runtime_bytes(retained['interfaces'], retained['plan'], probe['runtime_evidence'])
    runtime = validate_retained_runtime(runtime_raw, targets, options, scope)
    manifest = {'repository': 'nico/owned-source', 'commit_sha': 'b'*40, 'tree_sha': 'c'*40,
                'project_options': options}
    manifest_raw, baseline_raw, scope_raw = map(canonical_bytes, (manifest, baseline, scope))
    receipt = {'schema': 'nico.cpp-configuration-qualification.v2', 'producer_source_sha': 'd'*40,
        'production_qualified': False, 'production_dispatch_exercised': False, 'compiled': True,
        'tests_executed': True, 'status': probe['status'], 'stage': 'execution_unproven' if kind else 'completed',
        'benchmark_sha256': hashlib.sha256(manifest_raw).hexdigest(),
        'execution_contract_sha256': hashlib.sha256(baseline_raw).hexdigest(),
        'runtime_scope_sha256': hashlib.sha256(scope_raw).hexdigest(),
        'runtime_plan_sha256': hashlib.sha256(canonical_bytes(retained['plan'])).hexdigest(),
        'source': {**{k: manifest[k] for k in ('repository', 'commit_sha', 'tree_sha')},
                   'inventory_complete': True, 'targets': targets},
        'probe': qualification_probe_receipt(probe),
        'runtime': {'complete': not bool(kind), 'artifact': retain('project-runtime-evidence', runtime_raw),
                    'native_evidence_sha256': hashlib.sha256(runtime_raw).hexdigest(),
                    'duration_ms': runtime['duration_ms']}}
    kwargs = {'manifest_raw': manifest_raw, 'baseline_raw': baseline_raw, 'scope_raw': scope_raw,
              'producer_source_sha': 'd'*40, 'image': image}
    return receipt, lambda ref: (output/ref['path']).read_bytes(), kwargs


@pytest.mark.parametrize('kind', [None, 'undefined'])
def test_full_collection_reconstructs_every_owned_population_preserving_target_result(tmp_path, kind):
    receipt, read, kwargs = bundle(tmp_path, kind=kind)
    before = deepcopy(receipt)
    result = validate_project_collection(receipt, read, **kwargs)
    assert receipt == before
    assert result['collection_complete'] is True and result['target_tests_passed'] is (kind is None)
    assert result['compiler_contexts'] == result['static_contexts'] == 3
    assert result['baseline']['required'] == ['owned_suite']
    assert result['runtime']['summary']['complete'] is (kind is None)
    assert result['production_qualified'] is False and result['full_project_qualified'] is False


@pytest.mark.parametrize('kind', [None, 'undefined'])
def test_collection_policy_never_grants_the_existing_image_qualification(tmp_path, kind):
    from scripts.export_qualified_cpp_worker_image import validate_full_project_qualification
    receipt, read, kwargs = bundle(tmp_path, kind=kind)
    assert validate_project_collection(receipt, read, **kwargs)['collection_complete'] is True
    with pytest.raises(ValueError, match='image_handoff_full_project_qualification_invalid'):
        validate_full_project_qualification(receipt, source_sha=kwargs['producer_source_sha'], image=kwargs['image'])


@pytest.mark.parametrize('kind', [None, 'undefined'])
def test_original_probe_status_must_agree_with_reconstructed_target_result(tmp_path, kind):
    receipt, read, kwargs = bundle(tmp_path, kind=kind)
    receipt.update(status='BASELINE_EXECUTED' if kind else 'UNPROVEN',
                   stage='completed' if kind else 'execution_unproven')
    receipt['probe'].update(status=receipt['status'],
        error=None if kind else 'worker_configuration_probe_runtime_incomplete')
    with pytest.raises(ValueError):
        validate_project_collection(receipt, read, **kwargs)


@pytest.mark.parametrize('opt_in', [False, True])
def test_cli_defaults_keep_legacy_receipt_and_new_policy_requires_explicit_choice(tmp_path, opt_in):
    # Fail before source acquisition or Docker. The retained initial receipt is
    # enough to observe the real argparse policy choice and producer binding.
    manifest = tmp_path/'manifest.json'; manifest.write_text('{}')
    output = tmp_path/'output'
    argv = [sys.executable, '-m', 'scripts.qualify_cpp_project_configuration',
        '--image', 'sha256:'+'a'*64, '--qualification-source', str(tmp_path/'no-source'),
        '--qualification-manifest', str(manifest), '--output', str(output)]
    if opt_in:
        baseline = tmp_path/'baseline.json'; baseline.write_bytes(canonical_bytes(contract()))
        scope = tmp_path/'scope.json'
        scope.write_bytes((Path(__file__).parents[1]/'tests/fixtures/cpp/bitcoin-runtime-scope.json').read_bytes())
        argv += ['--accept-completed-collection', '--producer-source-sha', 'd'*40,
            '--baseline-execution-contract', str(baseline), '--runtime-scope-contract', str(scope)]
    result = subprocess.run(argv, cwd=Path(__file__).parents[1], capture_output=True, timeout=15)
    assert result.returncode != 0
    receipt = json.loads((output/'receipt.json').read_bytes())
    assert receipt['schema'] == 'nico.cpp-configuration-qualification.'+('v2' if opt_in else 'v1')
    assert receipt.get('producer_source_sha') == ('d'*40 if opt_in else None)
    assert receipt['production_qualified'] is False
    assert not (output/'collection-acceptance.json').exists()


@pytest.mark.parametrize('fault', ['producer', 'image', 'source', 'manifest_hash', 'baseline_hash', 'scope_hash',
    'cleanup', 'boundary', 'static_image', 'static_source', 'static_population', 'runtime_summary',
    'compiler_population', 'artifact_hash', 'production', 'historical_schema', 'runtime_plan',
    'runtime_projection', 'outer_runtime_exit', 'outer_runtime_argv', 'outer_runtime_output',
    'missing_runtime_operation', 'duplicate_runtime_operation', 'raw_static_image', 'raw_static_source'])
def test_full_collection_rejects_identity_or_retained_population_substitution(tmp_path, fault):
    receipt, read, kwargs = bundle(tmp_path)
    p = receipt['probe']
    if fault == 'producer': kwargs['producer_source_sha'] = 'e'*40
    elif fault == 'image': kwargs['image'] = 'sha256:'+'e'*64
    elif fault == 'source': receipt['source']['commit_sha'] = 'e'*40
    elif fault == 'manifest_hash': receipt['benchmark_sha256'] = '0'*64
    elif fault == 'baseline_hash': receipt['execution_contract_sha256'] = '0'*64
    elif fault == 'scope_hash': receipt['runtime_scope_sha256'] = '0'*64
    elif fault == 'cleanup': p['cleanup_verified'] = False
    elif fault == 'boundary': p['boundary']['external_network_blocked'] = False
    elif fault == 'static_image': p['project_static_stage']['image_config_digest'] = 'sha256:'+'e'*64
    elif fault == 'static_source': p['project_static_stage']['source_population_sha256'] = '0'*64
    elif fault == 'static_population': p['project_static']['analyzed_contexts_count'] -= 1
    elif fault == 'runtime_summary': p['runtime_summary']['complete'] = True
    elif fault == 'compiler_population': p['project_compiler']['checked_contexts'] = []
    elif fault == 'artifact_hash': receipt['runtime']['artifact']['sha256'] = '0'*64
    elif fault == 'production': receipt['production_qualified'] = True
    elif fault == 'historical_schema': receipt['schema'] = 'nico.cpp-configuration-qualification.v1'
    elif fault == 'runtime_plan': receipt['runtime_plan_sha256'] = '0'*64
    elif fault == 'runtime_projection': p['runtime_evidence']['native_evidence_sha256'] = '0'*64
    elif fault.startswith('outer_runtime_'):
        row = next(row for row in p['operations'] if row['id'] == 'runtime-fuzz-campaign')
        if fault == 'outer_runtime_exit': row['exit_code'] = 1
        elif fault == 'outer_runtime_argv': row['invocation'] += ['-runs=1']
        elif fault == 'outer_runtime_output': row['output'] = base64.b64encode(b'other bytes').decode()
    elif fault == 'missing_runtime_operation':
        p['operations'] = [row for row in p['operations'] if row['id'] != 'runtime-fuzz-campaign']
    elif fault == 'duplicate_runtime_operation':
        p['operations'].append(deepcopy(next(row for row in p['operations'] if row['id'] == 'runtime-fuzz-campaign')))
    elif fault.startswith('raw_static_'):
        op = next(row for row in p['project_static_stage']['operations'] if row['id'] ==
                  ('static-image' if fault == 'raw_static_image' else 'static-source'))
        replacement = [{'Id': 'sha256:'+'e'*64}] if fault == 'raw_static_image' else {'different.cpp': 'e'*64}
        replace_output(op, canonical_bytes(replacement))
    with pytest.raises(ValueError):
        validate_project_collection(receipt, read, **kwargs)


@pytest.mark.parametrize('key', ['configure', 'project-generated-context', 'project-compiler-evidence',
    'baseline-build', 'project-static-environment', 'project-static-evidence', 'static-restore', 'static-start'])
def test_full_collection_requires_every_controller_operation(tmp_path, key):
    receipt, read, kwargs = bundle(tmp_path)
    p = receipt['probe']
    stage = p['project_static_stage'] if key.startswith(('static-', 'project-static-')) else p
    stage['operations'] = [row for row in stage['operations'] if row['id'] != key]
    # Missing structural transport keys may reject before value validation.
    with pytest.raises((ValueError, KeyError)):
        validate_project_collection(receipt, read, **kwargs)


@pytest.mark.parametrize('fault', ['create_image', 'create_network', 'configure_argv', 'source_transfer',
    'snapshot_program', 'compiler_program', 'compiler_reference', 'version_bytes', 'unused_option',
    'static_create_image', 'static_source_argv', 'static_private', 'static_restore', 'environment_program'])
def test_full_collection_rejects_changed_execution_and_artifact_transport(tmp_path, fault):
    receipt, read, kwargs = bundle(tmp_path)
    p = receipt['probe']
    ops = {row['id']: row for row in p['operations']}
    static = {row['id']: row for row in p['project_static_stage']['operations']}
    if fault == 'create_image': ops['create']['invocation'][-2] = 'sha256:'+'e'*64
    elif fault == 'create_network': ops['create']['invocation'].remove('--network=none')
    elif fault == 'configure_argv': ops['configure']['invocation'] += ['-DBUILD_TESTS=OFF']
    elif fault == 'source_transfer': replace_output(ops['source-transfer'], canonical_bytes({'other.cpp': 'e'*64}))
    elif fault == 'snapshot_program': ops['project-generated-context']['invocation'][-1] = 'print("forged snapshot")'
    elif fault == 'compiler_program': ops['project-compiler-evidence']['invocation'][-1] = 'print("forged compiler")'
    elif fault == 'compiler_reference':
        ops['project-compiler-evidence']['output_artifact'] = deepcopy(p['generated_context']['artifact'])
        ops['project-compiler-evidence']['output_sha256'] = p['generated_context']['artifact']['sha256']
    elif fault == 'version_bytes': replace_output(ops['gcc-version'], b'14.3.0\n')
    elif fault == 'unused_option':
        raw = b'BUILD_TESTS:UNINITIALIZED=ON\n'
        replace_output(ops['configuration-cache'], envelope(raw))
        p.update(configuration_cache=base64.b64encode(raw).decode(), configuration_cache_sha256=hashlib.sha256(raw).hexdigest())
    elif fault == 'static_create_image': static['static-create']['invocation'][-2] = 'sha256:'+'e'*64
    elif fault == 'static_source_argv': static['static-source']['invocation'][-2] = 'print("different source")'
    elif fault == 'static_private': replace_output(static['static-private'], canonical_bytes({'uid': 0, 'gid': 0, 'private': True}))
    elif fault == 'static_restore':
        restored = json.loads(base64.b64decode(static['static-restore']['output']))
        restored['file_population_sha256'] = '0'*64
        replace_output(static['static-restore'], canonical_bytes(restored))
    elif fault == 'environment_program': static['project-static-environment']['invocation'][-1] = 'print("different compiler environment")'
    with pytest.raises(ValueError):
        validate_project_collection(receipt, read, **kwargs)


def fallback_program_with_literal(value):
    from nico.assessment_cpp_clang_fallback import PROGRAM
    prefix = '_DROP_EXACT=frozenset('
    lines = PROGRAM.splitlines(keepends=True)
    index = next(i for i, line in enumerate(lines) if line.startswith(prefix))
    length = len(lines[index]) - len(prefix) - len(')\n')
    assert len(value) <= length
    lines[index] = prefix + value.ljust(length) + ')\n'
    return ''.join(lines)


def test_historical_frozenset_serialization_accepts_only_identical_members(tmp_path):
    from nico.assessment_cpp_clang_fallback import PROGRAM, _DROP_EXACT
    from nico.assessment_cpp_collection_transport import _fallback_program_equal
    for values in (sorted(_DROP_EXACT), sorted(_DROP_EXACT, reverse=True)):
        changed = fallback_program_with_literal('{'+', '.join(map(repr, values))+'}')
        assert len(changed) == len(PROGRAM)
        assert _fallback_program_equal(changed, PROGRAM)


@pytest.mark.parametrize('fault', ['member', 'injection', 'tuple', 'code', 'assignment'])
def test_historical_frozenset_tolerance_rejects_other_program_changes(fault):
    from nico.assessment_cpp_clang_fallback import PROGRAM, _DROP_EXACT
    from nico.assessment_cpp_collection_transport import _fallback_program_equal
    values = sorted(_DROP_EXACT)
    if fault == 'member':
        values[0] = values[0][:-1] + ('x' if values[0][-1] != 'x' else 'y')
        changed = fallback_program_with_literal('{'+', '.join(map(repr, values))+'}')
    elif fault == 'injection':
        changed = fallback_program_with_literal("__import__('builtins').print('unexpected')")
    elif fault == 'tuple':
        changed = fallback_program_with_literal('('+', '.join(map(repr, values))+')')
    elif fault == 'code': changed = PROGRAM.replace('return ', 'returN ', 1)
    elif fault == 'assignment': changed = PROGRAM.replace('_DROP_EXACT=frozenset(', '_DROP_OTHER=frozenset(', 1)
    assert len(changed) == len(PROGRAM)
    assert changed != PROGRAM
    assert _fallback_program_equal(changed, PROGRAM) is False
