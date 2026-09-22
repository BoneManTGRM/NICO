"""Full-project contract/receipt regressions; all native rows here are synthetic."""
from copy import deepcopy
from dataclasses import asdict
import base64
import hashlib
import json

import pytest

from nico.assessment_cpp_full_project import (
    PROFILE, configuration, execution_steps, validate_configuration, validate_native,
)
from nico.assessment_worker_consumer import _receipt
from nico.assessment_worker_jobs import _digest
from nico.assessment_worker_receipts import validate_contract, validate_receipt
from scripts.worker_protocol_fixture import identity


def plan():
    return {'profile': PROFILE, 'tool_version': '2.17.1', 'image_digest': 'sha256:' + 'd' * 64,
        'configuration': configuration(units=['main.cpp', 'sum.cpp'],
            unit_tests=['unit'], integration_tests=['integration']),
        'targets': {p: hashlib.sha256(p.encode()).hexdigest()
                    for p in ['CMakeLists.txt', 'main.cpp', 'sum.cpp', 'sum.hpp']},
        'limits': {'max_attempts': 1, 'wall_seconds': 240, 'lease_seconds': 30},
        'max_receipt_bytes': 2 * 1024 * 1024}


def encoded(raw):
    return base64.b64encode(raw).decode('ascii')


def native(plan_value=None):
    p = plan_value or plan()
    rows = []
    for spec in execution_steps(p):
        out = b''
        artifacts = {}
        step = spec['id']
        if step == 'cmake-version': out = b'cmake version 3.31.6\n'
        if step == 'compiler-version': out = b'14.2.0\n'
        if step == 'analyzer-version': out = b'Cppcheck 2.17.1\n'
        if step.endswith('-configure'):
            directory = spec['build_dir']
            sanitize = spec.get('sanitizer')
            flags = ['-fsanitize=' + sanitize] if sanitize else []
            data = [{'directory': directory, 'file': '/work/source/' + unit,
                     'arguments': ['/usr/local/bin/g++', *flags, '-c', '/work/source/' + unit]}
                    for unit in p['configuration']['translation_units']]
            artifacts['compilation_database'] = encoded(json.dumps(data).encode())
        if step == 'static-analysis':
            out = b'Checking /work/source/main.cpp ...\nChecking /work/source/sum.cpp ...\n'
            artifacts['analysis_xml'] = encoded(b'<results version="2"><cppcheck version="2.17.1"/><errors/></results>')
        if step.endswith('-discover'):
            out = json.dumps({'kind': 'ctestInfo', 'version': {'major': 1, 'minor': 0},
                    'tests': [{'name': name, 'command': ['/work/build/control', name]}
                              for name in ['unit', 'integration', 'outside-scope']]}).encode()
        if spec.get('tests'):
            artifacts['junit'] = encoded(('<testsuite tests="' + str(len(spec['tests'])) + '">' +
                ''.join('<testcase name="' + name + '" status="run"/>' for name in spec['tests']) +
                '</testsuite>').encode())
        rows.append({'id': step, 'invocation': spec['invocation'], 'attempted': True,
            'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'duration_ms': 2,
            'output': encoded(out), 'artifacts': artifacts})
    return {'schema': 'nico.cpp-full-project-native.v1', 'steps': rows,
        'source_hashes': deepcopy(p['targets']), 'boundary_verified': True,
        'boundary': {'source_read_only': True, 'work_root_owned_sticky': True, 'uid': 1000, 'gid': 1000, 'no_new_privileges': True,
            'effective_capabilities': 0, 'cpu_max': '200000 100000', 'memory_max': '2147483648',
            'pids_max': '256', 'swap_max': '0', 'work_mount': ['rw', 'nosuid', 'nodev'],
            'root_read_only': True, 'docker_socket_absent': True,
            'credential_environment_absent': True, 'external_network_blocked': True},
        'memory_peak_bytes': 350000000, 'cleanup_verified': True, 'error': None}


def wrap(value, p=None):
    p = p or plan()
    job = {'contract': p, 'identity': asdict(identity(p)), 'lease_id': 'e' * 32,
           'worker_id': 'github:123456:12345678:1'}
    return _receipt(job, {'native': value})


def test_real_profile_is_accepted_by_existing_contract_and_uses_version_six_receipt():
    p = plan()
    assert validate_contract(p) == p
    n = native(p)
    r = wrap(n, p)
    assert r['schema'] == 'nico.worker-native-receipt.v6'
    _, record, _ = validate_receipt(identity(p), p, r['lease_id'], r['worker_id'], r)
    assert record['completed'] is True
    assert record['cpp_build_evidence']['project_build_system_executed'] is True
    assert record['cpp_build_evidence']['build_completed'] is True
    assert record['cpp_build_evidence']['fuzz_executed'] is False
    assert record['cpp_build_evidence']['full_project_qualified'] is False
    assert record['cppcheck_source_coverage']['header_context_verified'] is False
    assert record['client_delivery_allowed'] is False


def test_failed_tests_do_not_erase_completed_static_analysis():
    p, n = plan(), native()
    row = next(r for r in n['steps'] if r['id'] == 'baseline-unit')
    row['exit_code'] = 8
    row['artifacts']['junit'] = encoded(b'<testsuite tests="1"><testcase name="unit" status="fail"><failure/></testcase></testsuite>')
    result = validate_native(n, p)
    assert result['complete'] is True  # Cppcheck completion, not full execution assurance.
    assert result['build']['implemented_command_scope_complete'] is False
    unit = next(r for r in result['build']['stages'] if r['id'] == 'baseline-unit')
    assert unit['status'] == 'failed' and unit['passed_tests'] == []
    assert unit['executed_tests'] == ['unit']


@pytest.mark.parametrize('path', ['../bad.cpp', '/tmp/x', 'bad//x', 'bad/./x', 'x\n.cpp', '.git/x'])
def test_invalid_source_population_rejected(path):
    p = plan(); p['configuration']['translation_units'][0] = path
    with pytest.raises(ValueError): validate_contract(p)


@pytest.mark.parametrize('field,value', [('source_byte_limit', True), ('source_byte_limit', 67108865),
    ('parallel', 0), ('parallel', 3), ('platform', 'darwin'), ('cmake_version', 'latest'),
    ('compiler_version', 'latest'), ('sanitizers', ['address', 'address']),
    ('translation_units', []), ('unit_tests', []), ('integration_tests', ['unit'])])
def test_malformed_or_unbounded_configuration_fails_closed(field, value):
    p = plan(); p['configuration'][field] = value
    with pytest.raises(ValueError): validate_contract(p)


def test_public_arbitrary_commands_and_cmake_controller_overrides_are_not_accepted():
    p = plan(); p['configuration']['commands'] = [['bash', '-c', 'anything']]
    with pytest.raises(ValueError): validate_contract(p)
    p = plan(); p['configuration']['project_options']['CMAKE_CXX_COMPILER'] = '/tmp/compiler'
    with pytest.raises(ValueError): validate_contract(p)


@pytest.mark.parametrize('field,value', [('source_hashes', {}), ('boundary_verified', 1),
    ('cleanup_verified', 'true'), ('memory_peak_bytes', True), ('schema', 'other'),
    ('steps', []), ('error', 'arbitrary private error')])
def test_bad_native_contract_rejected(field, value):
    n = native(); n[field] = value
    with pytest.raises(ValueError): validate_native(n, plan())


@pytest.mark.parametrize('field,value', [('exit_code', True), ('attempted', 1),
    ('invocation', ['other']), ('duration_ms', -1), ('output', 'not base64')])
def test_bad_step_fields_rejected(field, value):
    n = native(); n['steps'][0][field] = value
    with pytest.raises(ValueError): validate_native(n, plan())


def test_duplicate_compile_database_entries_do_not_inflate_coverage():
    n = native(); row = next(r for r in n['steps'] if r['id'] == 'baseline-configure')
    db = json.loads(base64.b64decode(row['artifacts']['compilation_database']))
    db.append(db[0])
    row['artifacts']['compilation_database'] = encoded(json.dumps(db).encode())
    result = validate_native(n, plan())
    assert result['complete'] is False
    assert result['coverage']['configuration_aware'] is False


@pytest.mark.parametrize('xml', [b'<broken', b'<testsuite tests="0"/>',
    b'<testsuite tests="1"><testcase name="other"/></testsuite>',
    b'<testsuite tests="1"><testcase name="unit"><skipped/></testcase></testsuite>'])
def test_empty_malformed_wrong_or_skipped_tests_never_pass(xml):
    n = native(); row = next(r for r in n['steps'] if r['id'] == 'baseline-unit')
    row['artifacts']['junit'] = encoded(xml)
    result = validate_native(n, plan())
    assert result['build']['implemented_command_scope_complete'] is False


def test_missing_instrumentation_cannot_claim_sanitizer_execution():
    n = native(); row = next(r for r in n['steps'] if r['id'] == 'address-configure')
    data = json.loads(base64.b64decode(row['artifacts']['compilation_database']))
    for entry in data: entry['arguments'] = [x for x in entry['arguments'] if not x.startswith('-fsanitize=')]
    row['artifacts']['compilation_database'] = encoded(json.dumps(data).encode())
    result = validate_native(n, plan())
    assert result['build']['sanitizers']['address']['instrumentation_configuration_verified'] is False
    assert result['build']['implemented_command_scope_complete'] is False


def test_compact_report_keeps_stage_truth_without_native_logs():
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    p = plan(); r = wrap(native(), p)
    _, record, _ = validate_receipt(identity(p), p, r['lease_id'], r['worker_id'], r)
    record['raw_artifact_retention_complete'] = True
    record['raw_artifact_sha256'] = _digest(r)
    compact = compact_scanner_records({'scan_id': 'synthetic-scan', 'scanner_results': [record]}, commit_sha='a' * 40)
    assert compact[0]['cpp_build_evidence'] == record['cpp_build_evidence']
    assert 'output' not in json.dumps(compact[0]['cpp_build_evidence'])


def test_declared_subset_build_targets_cannot_be_counted_as_all_translation_units():
    p = plan(); p['configuration']['build_targets'] = ['control']
    with pytest.raises(ValueError): validate_contract(p)


def test_planned_compile_database_is_not_a_compiler_execution_population():
    result = validate_native(native(), plan())
    assert result['build']['compiled_translation_units'] is None
    assert result['build']['compilation_database_translation_units'] == ['main.cpp', 'sum.cpp']


def test_writable_source_or_nonsticky_parent_cannot_pass_source_binding():
    for field, value in [('source_read_only', False), ('work_root_owned_sticky', False)]:
        n = native(); n['boundary'][field] = value
        result = validate_native(n, plan())
        assert result['complete'] is False
        assert result['build']['implemented_command_scope_complete'] is False


class FakeDocker:
    """Contract-only test double. Never launches Docker or assessed commands."""
    def __init__(self, p, n):
        self.plan, self.native, self.calls = p, n, []
        self.boundary_count = 0
        self.fail_id = None
        self.fail_kind = None

    def __call__(self, args, **kwargs):
        from nico.assessment_cpp_full_project_execution import BOUNDARY_PROGRAM, INPUT_PROGRAM, READ_PROGRAM
        self.calls.append((args, kwargs))
        out, exit_code, timeout, truncated = b'', 0, False, False
        if args[:3] == ['docker', 'image', 'inspect']:
            out = json.dumps([{'Id': self.plan['image_digest']}]).encode()
        elif BOUNDARY_PROGRAM in args:
            self.boundary_count += 1
            out = json.dumps(self.native['boundary']).encode()
        elif INPUT_PROGRAM in args:
            assert '--user=0:0' in args
            assert all(set(v) == {'base64', 'sha256', 'executable'} for v in json.loads(kwargs['input_bytes']).values())
            out = json.dumps(self.plan['targets']).encode()
        elif READ_PROGRAM in args:
            path = args[-2]
            for spec, row in zip(execution_steps(self.plan), self.native['steps']):
                for name, target in spec['artifacts'].items():
                    if target == path:
                        out = json.dumps({'data': row['artifacts'][name], 'truncated': False}).encode()
        elif args[:2] == ['docker', 'exec']:
            if args[-1] == '/sys/fs/cgroup/memory.peak':
                out = b'350000000\n'
            else:
                row = next(r for r in self.native['steps'] if args[3:] == r['invocation'])
                out = base64.b64decode(row['output'])
                if row['id'] == self.fail_id:
                    exit_code = 124 if self.fail_kind == 'timeout' else 125
                    timeout = self.fail_kind == 'timeout'
                    truncated = not timeout
        return {'output': out, 'exit_code': exit_code, 'timed_out': timeout, 'output_truncated': truncated}


def source_fixture(tmp_path):
    p = plan()
    for path in p['targets']:
        (tmp_path / path).write_bytes(path.encode())
    return p


def test_executor_uses_real_dispatch_branch_and_a_credential_free_container(tmp_path, monkeypatch):
    from nico import assessment_cpp_full_project_execution as executor
    from nico.assessment_worker_container import run_isolated_cppcheck
    p = source_fixture(tmp_path); fake = FakeDocker(p, native(p))
    monkeypatch.setattr(executor, '_command', fake)
    result = run_isolated_cppcheck(p, tmp_path, checkpoint=lambda: None, timeout_seconds=60)
    evaluated = validate_native(result['native'], p)
    assert evaluated['complete'] is True
    create = next(args for args, _ in fake.calls if args[:2] == ['docker', 'create'])
    assert {'--network=none', '--read-only', '--user=1000:1000', '--cap-drop=ALL',
        '--security-opt=no-new-privileges', '--memory=2g', '--cpus=2', '--pids-limit=256'} <= set(create)
    assert not any(x in {'--privileged', '--volume', '--mount'} for x in create)
    roots = [args for args, _ in fake.calls if '--user=0:0' in args]
    assert len(roots) == 1 and executor.INPUT_PROGRAM in roots[0]
    assert fake.boundary_count == 2
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']
    assert all('--user=0:0' not in args for args, _ in fake.calls if args[3:4] in [['cmake'], ['ctest'], ['cppcheck']])


@pytest.mark.parametrize('kind', ['timeout', 'truncated'])
def test_timeout_or_truncation_cleans_up_and_preserves_unattempted_steps(tmp_path, kind):
    from nico.assessment_cpp_full_project_execution import run_full_project
    p = source_fixture(tmp_path); fake = FakeDocker(p, native(p))
    fake.fail_id, fake.fail_kind = 'baseline-build', kind
    n = run_full_project(p, tmp_path, checkpoint=lambda: None, timeout_seconds=60, command=fake)['native']
    row = next(r for r in n['steps'] if r['id'] == 'baseline-build')
    assert row['attempted'] is True and (row['timed_out'] or row['output_truncated'])
    assert next(r for r in n['steps'] if r['id'] == 'static-analysis')['attempted'] is False
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']
    assert validate_native(n, p)['build']['implemented_command_scope_complete'] is False


def test_failed_boundary_never_reaches_project_commands(tmp_path):
    from nico.assessment_cpp_full_project_execution import run_full_project, INPUT_PROGRAM
    p = source_fixture(tmp_path); n = native(p); n['boundary']['external_network_blocked'] = False
    fake = FakeDocker(p, n)
    result = run_full_project(p, tmp_path, checkpoint=lambda: None, timeout_seconds=60, command=fake)
    assert not any(INPUT_PROGRAM in args for args, _ in fake.calls)
    assert all(not r['attempted'] for r in result['native']['steps'])
    assert result['native']['error'] == 'worker_full_project_control_failed'
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']


@pytest.mark.parametrize('problem', ['symlink', 'extra', 'digest', 'bytes'])
def test_invalid_source_does_not_launch_any_container(tmp_path, problem):
    from nico.assessment_cpp_full_project_execution import run_full_project
    p = source_fixture(tmp_path)
    if problem == 'symlink':
        (tmp_path / 'sum.hpp').unlink(); (tmp_path / 'sum.hpp').symlink_to(tmp_path / 'main.cpp')
    elif problem == 'extra': (tmp_path / 'extra').write_bytes(b'no')
    elif problem == 'digest': (tmp_path / 'sum.hpp').write_bytes(b'changed')
    else: p['configuration']['source_byte_limit'] = 1
    fake = FakeDocker(p, native(p))
    with pytest.raises(ValueError):
        run_full_project(p, tmp_path, checkpoint=lambda: None, timeout_seconds=60, command=fake)
    assert fake.calls == []


def test_dead_lease_aborts_commands_and_still_removes_container(tmp_path):
    from nico.assessment_cpp_full_project_execution import run_full_project
    p = source_fixture(tmp_path); fake = FakeDocker(p, native(p))
    def checkpoint():
        if any(args[:2] == ['docker', 'start'] for args, _ in fake.calls):
            raise ValueError('synthetic_expired_lease')
    result = run_full_project(p, tmp_path, checkpoint=checkpoint, timeout_seconds=60, command=fake)
    assert result['native']['error'] == 'worker_full_project_control_failed'
    assert all(not r['attempted'] for r in result['native']['steps'])
    assert fake.calls[-1][0][:3] == ['docker', 'rm', '--force']


@pytest.mark.parametrize('language,phrase', [('en', 'C/C++ project execution'), ('es-MX', 'Ejecución del proyecto C/C++')])
def test_existing_report_stage_renders_project_evidence_in_both_languages(language, phrase):
    from nico.v2_premium_report_renderer import _canonical_stages
    p = plan(); n = native(p)
    row = next(r for r in n['steps'] if r['id'] == 'baseline-unit')
    row['exit_code'] = 8
    row['artifacts']['junit'] = encoded(b'<testsuite tests="1"><testcase name="unit" status="fail"><failure/></testcase></testsuite>')
    r = wrap(n, p); _, record, _ = validate_receipt(identity(p), p, r['lease_id'], r['worker_id'], r)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(r))
    canonical = {'report_language': language, 'scanner_execution_records': [record],
                 'identity': {'run_id': record['run_id'], 'commit_sha': record['commit_sha']}}
    before = deepcopy(canonical)
    stage = next(s for s in _canonical_stages(canonical) if s['stage_id'] == 'dependency_security_static_analysis')
    assert phrase in stage['summary']
    assert ('passed=0/1' if language == 'en' else 'aprobadas=0/1') in stage['summary']
    assert any(('native exit=8' if language == 'en' else 'salida nativa=8') in s for s in stage['evidence'])
    assert 'libFuzzer' in ' '.join(stage['unavailable']) or 'LibFuzzer' in ' '.join(stage['unavailable'])
    assert canonical == before


def test_failed_sanitizer_tests_still_record_actual_execution_not_absence():
    n = native(); p = plan()
    row = next(r for r in n['steps'] if r['id'] == 'address-unit')
    row['exit_code'] = 8
    row['artifacts']['junit'] = encoded(b'<testsuite tests="1"><testcase name="unit" status="fail"><failure/></testcase></testsuite>')
    build = validate_native(n, p)['build']
    assert build['sanitizers']['address']['executed'] is True
    assert build['sanitizers']['address']['passed'] is False
    assert build['sanitizers']['address']['instrumentation_configuration_verified'] is True
    assert build['sanitizers']['address']['instrumentation_verified'] is False
    assert build['requested_scope_complete'] is False
    assert build['sanitizers_executed'] is True


@pytest.mark.parametrize('problem', ['run', 'revision', 'digest', 'retention', 'observation'])
def test_rendering_does_not_promote_unbound_project_evidence(problem):
    from nico.v2_premium_report_renderer import _canonical_stages
    p = plan(); r = wrap(native(p), p)
    _, record, _ = validate_receipt(identity(p), p, r['lease_id'], r['worker_id'], r)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(r))
    canonical = {'scanner_execution_records': [record],
        'identity': {'run_id': record['run_id'], 'commit_sha': record['commit_sha']}}
    if problem == 'run': canonical['identity']['run_id'] = 'another-run'
    elif problem == 'revision': canonical['identity']['commit_sha'] = 'f' * 40
    elif problem == 'digest': record['raw_artifact_sha256'] = 'f' * 64
    elif problem == 'retention': record['raw_artifact_retention_complete'] = False
    else: record['execution_observed_for_this_report'] = False
    stage = next(s for s in _canonical_stages(canonical) if s['stage_id'] == 'dependency_security_static_analysis')
    assert 'C/C++ project execution: build completed.' not in stage['summary']
    assert any('not bound to a verified retained receipt' in s for s in stage['unavailable'])


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_public_report_export_keeps_failed_test_truth_and_approval_boundary(tmp_path, language):
    from scripts.qualify_cpp_full_project_integration import render_result
    p, n = plan(), native()
    row = next(r for r in n['steps'] if r['id'] == 'baseline-unit')
    row['exit_code'] = 8
    row['artifacts']['junit'] = encoded(b'<testsuite tests="1"><testcase name="unit" status="fail"><failure/></testcase></testsuite>')
    r = wrap(n, p); _, record, _ = validate_receipt(identity(p), p, r['lease_id'], r['worker_id'], r)
    record.update(raw_artifact_retention_complete=True, raw_artifact_sha256=_digest(r))
    before = deepcopy(record)
    result = render_result({'canonical_record': record}, tmp_path, language)
    assert result['summary_in_all_formats'] is True and result['production_report'] is False
    markdown = (tmp_path / ('owned-project-' + language + '.md')).read_text()
    assert ('passed=0/1' if language == 'en' else 'aprobadas=0/1') in markdown
    assert record == before
