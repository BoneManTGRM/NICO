"""Completed evidence collection is separate from a clean assessed target.

The v3 image handoff revalidates this decision before publication.
It does not grant production qualification or activation.
It reconstructs native evidence; it never changes the original probe result.
"""
from __future__ import annotations

import base64
import hashlib
import re

from nico.assessment_worker_receipts import canonical_bytes
from nico.assessment_cpp_full_project import _json, _database, _discovery, _junit
from nico.assessment_cpp_full_project_execution import boundary_valid, READ_PROGRAM
from nico.assessment_cpp_configuration_probe import CTEST_EXEC_PROGRAM


def _require(condition):
    if not condition:
        raise ValueError('qualification_collection_invalid')


def _digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _bind_runtime_projection(native, probe):
    """The controller's original operation records must agree with native bytes."""
    expected = {}
    def visit(value):
        if isinstance(value, dict):
            if 'id' in value and 'argv' in value:
                _require(value['id'] not in expected)
                expected[value['id']] = value
            else:
                for child in value.values():
                    visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
    visit(native)
    observed = {row['id']: row for row in probe['operations'] if row['id'].startswith('runtime-')}
    _require(observed.keys() == expected.keys())
    create = next(row for row in probe['operations'] if row['id'] == 'create')['invocation']
    container = create[create.index('--name') + 1]
    for key, value in expected.items():
        row = observed[key]
        prefix = ['docker', 'exec']
        if value['user']:
            prefix += ['--user=' + value['user']]
        if value['workdir']:
            prefix += ['--workdir=' + value['workdir']]
        prefix += ['--env=' + name + '=' + item for name, item in sorted(value['environment'].items())]
        if key == 'runtime-fuzz-corpus-stage':
            prefix.append('--interactive')
        _require(type(row['exit_code']) is int
                 and all(row[field] == value[field] for field in ('exit_code', 'timed_out', 'output_truncated', 'output_sha256'))
                 and row['output'] == value['output']
                 and row['invocation'] == [*prefix, container, *value['argv']])


def _operations(rows, artifact, *, allow_baseline_failure=False):
    """Check transport results and bytes, independently of summary flags."""
    _require(isinstance(rows, list) and 0 < len(rows) < 256)
    result, seen = {}, set()
    for row in rows:
        key = row['id']
        _require(key not in seen)
        seen.add(key)
        # Runtime operations have their own exact-argv/result validator.
        if key.startswith('runtime-'):
            continue
        _require(type(row['exit_code']) is int and (row['exit_code'] == 0
                  or (allow_baseline_failure and key == 'baseline-tests' and row['exit_code'] == 8))
                 and row['timed_out'] is False and row['output_truncated'] is False
                 and type(row['duration_ms']) is int and row['duration_ms'] >= 0)
        raw = (artifact(row['output_artifact']) if row.get('output_artifact')
               else base64.b64decode(row['output'], validate=True))
        _require(hashlib.sha256(raw).hexdigest() == row['output_sha256'])
        result[key] = (row, raw)
    return result


def validate_baseline_collection(probe, contract, artifact, *, allow_target_failure=False):
    """Bind complete baseline membership and native argv to the frozen contract."""
    ops = _operations(probe['operations'], artifact, allow_baseline_failure=allow_target_failure)
    _require(probe['baseline_execution'] == contract)
    create = ops['create'][0]['invocation']
    name = create[create.index('--name') + 1]
    prefix = ['docker', 'exec', name]
    expected = {
        'baseline-build': [*prefix, 'cmake', '--build', '/work/build', '--parallel', str(contract['parallel'])],
        'baseline-test-discovery': [*prefix, 'ctest', '--test-dir', '/work/build', '--show-only=json-v1'],
        'baseline-tests': ['docker', 'exec',
            *(['-e', 'DIR_UNIT_TEST_DATA=/work/unit_test_data'] if probe.get('unit_test_data') is not None else []),
            name, 'python3', '-I', '-S', '-c', CTEST_EXEC_PROGRAM,
            '/work/build/nico-baseline-ctest.log', 'ctest', '--test-dir', '/work/build',
            '--parallel', str(contract['parallel']), '--timeout', str(contract['test_case_seconds']),
            '--output-on-failure', '--output-junit', '/work/build/nico-baseline-junit.xml'],
        'baseline-junit': [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/nico-baseline-junit.xml', str(2 * 1024 * 1024)],
        'baseline-test-log': [*prefix, 'python3', '-I', '-S', '-c', READ_PROGRAM,
            '/work/build/nico-baseline-ctest.log', str(1024 * 1024)],
    }
    for key, argv in expected.items():
        _require(ops[key][0]['invocation'] == argv)
    for key, seconds in [('baseline-build', contract['build_seconds']),
                         ('baseline-tests', contract['test_seconds'])]:
        _require(ops[key][0]['duration_ms'] <= (seconds + 5) * 1000)
    discovery = ops['baseline-test-discovery'][1]
    _require(discovery == base64.b64decode(probe['native_test_discovery'], validate=True))
    names = _discovery(discovery)
    _require(names and names == probe['tests_discovered']
             and not any(name.endswith('_DISCOVERY_FAILURE') for name in names))
    database = base64.b64decode(probe['compilation_database'], validate=True)
    for key in ('compilation-database', 'post-build-database'):
        value = _json(ops[key][1])
        _require(set(value) == {'data', 'truncated'} and value['truncated'] is False
                 and base64.b64decode(value['data'], validate=True) == database)
    _require(_json(ops['boundary-after'][1]) == probe['boundary']
             and _json(ops['image'][1])[0]['Id'] == probe['image_config_digest'])
    files = {}
    for key in ('baseline-junit', 'baseline-test-log'):
        value = _json(ops[key][1])
        _require(set(value) == {'data', 'truncated'} and value['truncated'] is False)
        files[key] = base64.b64decode(value['data'], validate=True)
        _require(0 < len(files[key]) <= (2 if key == 'baseline-junit' else 1) * 1024 * 1024)
    results = probe['tests_result']
    _require(files['baseline-junit'] == base64.b64decode(results['junit'], validate=True)
             and results['junit_truncated'] is False and results['log_truncated'] is False)
    executed, passed, skipped = _junit(files['baseline-junit'], names)
    _require(executed == names and skipped == []
             and results['executed'] == executed and results['passed'] == passed and results['skipped'] == [])
    from nico.assessment_cpp_runtime_execution import _completed_sanitizer_test_failure
    success = ops['baseline-tests'][0]['exit_code'] == 0 and passed == names
    failure = allow_target_failure and _completed_sanitizer_test_failure(
        ops['baseline-tests'][0],
        {'required': names, 'executed': executed, 'passed': passed, 'skipped': skipped},
        files['baseline-junit'])
    _require(success or failure)
    return {'required': names, 'executed': executed, 'passed': passed, 'skipped': skipped}


def validate_project_collection(receipt, read_artifact, *, manifest_raw, baseline_raw,
                                scope_raw, producer_source_sha, image):
    """Accept only full source-bound collection; retain all original failures.

    ``read_artifact`` reads a bounded local file by its validated artifact reference.
    Producer/image arguments come from the qualification job, not the target source.
    """
    from nico.assessment_cpp_project_snapshot import validate_project_snapshot, PROJECT_GENERATED_STREAM_LIMIT
    from nico.assessment_cpp_project_compiler import project_compiler_request, validate_project_compiler
    from nico.assessment_cpp_static_environment import environment_request, validate_environment
    from nico.assessment_cpp_project_static import project_static_request, validate_project_static
    from nico.assessment_cpp_clang_fallback import clang_fallback_request, validate_clang_fallback, merge_static_analysis
    from nico.assessment_cpp_runtime_collection import validate_runtime_collection
    from nico.assessment_cpp_collection_transport import validate_transport

    _require(re.fullmatch(r'[a-f0-9]{40}', producer_source_sha or '') is not None
             and re.fullmatch(r'sha256:[a-f0-9]{64}', image or '') is not None
             and receipt.get('schema') == 'nico.cpp-configuration-qualification.v2'
             and receipt.get('producer_source_sha') == producer_source_sha
             and receipt.get('production_qualified') is False
             and receipt.get('production_dispatch_exercised') is False
             and receipt.get('compiled') is True and receipt.get('tests_executed') is True
             and receipt.get('error') is None)
    for raw, key in [(manifest_raw, 'benchmark_sha256'), (baseline_raw, 'execution_contract_sha256'),
                     (scope_raw, 'runtime_scope_sha256')]:
        _require(isinstance(raw, bytes) and 0 < len(raw) <= 16384
                 and hashlib.sha256(raw).hexdigest() == receipt[key])
    manifest, baseline, scope = map(_json, (manifest_raw, baseline_raw, scope_raw))
    # This first policy covers the frozen database contract used by the native
    # qualification job. Freeze-at-config contracts require a separate binding.
    _require(baseline.get('schema') == 'nico.cpp-baseline-execution.v1')
    source, probe = receipt['source'], receipt['probe']
    targets = source['targets']
    _require(source['inventory_complete'] is True
             and all(source[key] == manifest[key] for key in ('repository', 'commit_sha', 'tree_sha'))
             and probe['project_options'] == manifest['project_options']
             and probe['image_config_digest'] == image
             and probe['source_population_sha256'] == _digest(targets)
             and all(probe.get(key) is True for key in ('compiled', 'tests_executed', 'tests_passed',
                     'generated_context_verified', 'boundary_verified', 'cleanup_verified', 'scratch_capacity_verified'))
             and probe.get('full_project_qualified') is False
             and boundary_valid(probe['boundary'], profile=baseline['profile']))
    _require((receipt['status'], receipt['stage'], probe['status'], probe.get('error')) in {
        ('BASELINE_EXECUTED', 'completed', 'BASELINE_EXECUTED', None),
        ('UNPROVEN', 'execution_unproven', 'UNPROVEN', 'worker_configuration_probe_runtime_incomplete')})

    def artifact(ref):
        _require(isinstance(ref, dict) and set(ref) == {'path', 'sha256', 'bytes'}
                 and type(ref['bytes']) is int and 0 < ref['bytes'] <= PROJECT_GENERATED_STREAM_LIMIT
                 and re.fullmatch(r'artifacts/project-[a-z-]+-[a-f0-9]{64}\.json', ref['path']) is not None
                 and ref['path'].endswith('-' + ref['sha256'] + '.json'))
        raw = read_artifact(ref)
        _require(isinstance(raw, bytes) and len(raw) == ref['bytes']
                 and hashlib.sha256(raw).hexdigest() == ref['sha256'])
        return raw

    baseline_result = validate_baseline_collection(probe, baseline, artifact)
    runtime_raw = artifact(receipt['runtime']['artifact'])
    runtime = validate_runtime_collection(runtime_raw, targets, manifest['project_options'], scope)
    retained_runtime = _json(runtime_raw)
    validate_transport(probe, _operations(probe['operations'], artifact), targets,
                       runtime_plan=retained_runtime['plan'])
    rawdb = base64.b64decode(probe['compilation_database'], validate=True)
    _require(hashlib.sha256(rawdb).hexdigest() == baseline['compilation_database_sha256']
             == probe['compilation_database_sha256'])
    contexts = _database(rawdb, None, '/work/build', nested=True, source_targets=targets)
    snapshot = validate_project_snapshot(_json(artifact(probe['generated_context']['artifact'])), contexts)
    creq = project_compiler_request(rawdb, targets, snapshot, extended_budget=True)
    craw = artifact(probe['project_compiler']['artifact'])
    compiler = validate_project_compiler(craw, creq)
    _require(compiler['complete'] is True and compiler == {k: v for k, v in probe['project_compiler'].items() if k != 'artifact'})
    stage = probe['project_static_stage']
    _require(stage['image_config_digest'] == image and stage['complete'] is True
             and stage['error'] is None and stage['source_population_sha256'] == _digest(targets)
             and stage['boundary_verified'] is True and stage['cleanup_verified'] is True
             and stage['production_qualified'] is False
             and boundary_valid(stage['boundary'], profile=baseline['profile'], executable=False))
    static_ops = _operations(stage['operations'], artifact)
    _require(_json(static_ops['static-boundary'][1]) == stage['boundary']
             and _json(static_ops['static-image'][1])[0]['Id'] == image
             and _json(static_ops['static-source'][1]) == targets)
    validate_transport(stage, static_ops, targets, snapshot=snapshot)
    ereq = environment_request(creq, craw, image)
    env = validate_environment(artifact(stage['compiler_environment']['artifact']), ereq)
    sreq = project_static_request(rawdb, targets, snapshot, craw, extended_compiler_budget=True, environment=env)
    static = probe['project_static']
    primary = validate_project_static(artifact(static['artifact']), sreq)
    if static.get('fallback_artifact') is not None:
        freq = clang_fallback_request(sreq, primary, extended_budget=True, contention_aware=True)
        analysis = merge_static_analysis(primary, validate_clang_fallback(artifact(static['fallback_artifact']), freq, sreq))
    else:
        analysis = primary
    _require(analysis['complete'] is True and static['complete'] is True and stage['analysis'] == static)
    for key in ('required_contexts', 'attempted_contexts', 'analyzed_contexts', 'findings', 'limitations', 'modeled_inputs'):
        _require(len(analysis[key]) == static[key + '_count'] and _digest(analysis[key]) == static[key + '_sha256'])
    native = retained_runtime['evidence']
    _bind_runtime_projection(native, probe)
    _require(probe['runtime_evidence'] == {
        **{key: native[key] for key in ('schema', 'plan_sha256', 'complete', 'error', 'duration_ms')},
        'native_evidence_sha256': _digest(native), 'receipt_projection': 'hash-bound-summary-v1'})
    _require(runtime['summary'] == probe['runtime_summary']
             and runtime['runtime_plan_sha256'] == receipt['runtime_plan_sha256']
             and receipt['runtime']['complete'] is runtime['target_tests_passed']
             and receipt['runtime']['native_evidence_sha256'] == hashlib.sha256(runtime_raw).hexdigest())
    _require((receipt['status'] == 'BASELINE_EXECUTED') is runtime['target_tests_passed'])
    return {'schema': 'nico.cpp-assessment-collection.v1', 'collection_complete': True,
        'target_tests_passed': runtime['target_tests_passed'], 'producer_source_sha': producer_source_sha,
        'image_config_digest': image, 'qualification_receipt_sha256': _digest(receipt),
        'target_commit_sha': source['commit_sha'], 'target_tree_sha': source['tree_sha'],
        'source_population_sha256': _digest(targets), 'runtime': runtime,
        'baseline': baseline_result, 'compiler_contexts': len(compiler['checked_contexts']),
        'static_contexts': len(analysis['analyzed_contexts']), 'static_observations': len(analysis['findings']),
        'analyzer_header_coverage_verified': analysis['analyzer_header_coverage_verified'],
        'full_project_qualified': False, 'production_qualified': False}
