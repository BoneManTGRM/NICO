"""Owned configured-profile contracts; synthetic records are not native proof."""
from copy import deepcopy
import hashlib
import base64
from dataclasses import asdict
import json
import sys

import pytest

from nico.assessment_worker_receipts import validate_contract


def configured_contract():
    from scripts.worker_protocol_fixture import contract
    plan = contract()
    plan['profile'] = 'cpp-configured-v1'
    plan['configuration'] = {
        'platform': 'unix64', 'compiler_version': '14.2.0',
        'translation_units': [
            {'path': 'main.cpp', 'language': 'c++', 'standard': 'c++20',
             'defines': {'BIAS': '2'}, 'include_dirs': ['include']},
            {'path': 'value.cpp', 'language': 'c++', 'standard': 'c++20',
             'defines': {'BIAS': '2'}, 'include_dirs': ['include']},
        ],
        'headers': ['include/value.h'],
    }
    plan['targets'] = {p: hashlib.sha256(p.encode()).hexdigest()
                       for p in ['main.cpp', 'value.cpp', 'include/value.h']}
    return plan


def test_source_bound_configuration_is_accepted_without_activating_intake():
    plan = configured_contract()
    assert validate_contract(plan) == plan


@pytest.mark.parametrize('change', ['shell_define', 'outside_include', 'missing_header',
    'extra_input', 'duplicate_unit', 'unsupported_standard', 'unbound_unit', 'dotgit', 'compiler'])
def test_unbound_or_executable_configuration_is_rejected(change):
    plan = configured_contract()
    config = plan['configuration']
    unit = config['translation_units'][0]
    if change == 'shell_define': unit['defines']['BIAS'] = '$(touch /work/escaped)'
    elif change == 'outside_include': unit['include_dirs'] = ['/usr/local/private']
    elif change == 'missing_header': del plan['targets']['include/value.h']
    elif change == 'extra_input': plan['targets']['unaccounted.cpp'] = 'a' * 64
    elif change == 'duplicate_unit': config['translation_units'].append(deepcopy(unit))
    elif change == 'unsupported_standard': unit['standard'] = 'c++99'
    elif change == 'unbound_unit': unit['path'] = 'other.cpp'
    elif change == 'dotgit': unit['path'] = '.git/config'
    else: config['compiler_version'] = 'unverified'
    with pytest.raises(ValueError): validate_contract(plan)


def test_standalone_profile_keeps_original_contract():
    from scripts.worker_protocol_fixture import contract
    assert validate_contract(contract()) == contract()


def configured_receipt(plan=None):
    from nico.assessment_cpp_configuration import commands, database_bytes, COMPILER_VERSION
    from nico.assessment_worker_jobs import _digest
    from scripts.worker_protocol_fixture import identity
    plan = plan or configured_contract()
    job = identity(plan)
    def encoded(value): return base64.b64encode(value).decode('ascii')
    rows = []
    for spec in commands(plan['configuration']):
        artifact, stdout = b'', b''
        if spec['id'].startswith('compile-'):
            index = int(spec['id'].split('-')[1])
            path = plan['configuration']['translation_units'][index]['path']
            artifact = f'unit-{index}: ./{path} include/value.h\n'.encode()
        if spec['id'].startswith('analyze-'):
            index = int(spec['id'].split('-')[1])
            path = plan['configuration']['translation_units'][index]['path']
            artifact = b'<results version="2"><cppcheck version="2.17.1"/><errors/></results>'
            stdout = f'Checking /work/source/{path} ...\n'.encode()
        rows.append({'id': spec['id'], 'invocation': spec['invocation'], 'attempted': True, 'exit_code': 0,
            'timed_out': False, 'output_truncated': False, 'duration_ms': 1,
            'stdout': encoded(stdout), 'stderr': '', 'artifact': encoded(artifact)})
    rows.append({'id': 'test', 'invocation': ['/work/source/native-test'], 'attempted': True, 'exit_code': 0,
        'timed_out': False, 'output_truncated': False, 'duration_ms': 1, 'stdout': '', 'stderr': '', 'artifact': ''})
    native = {'steps': rows, 'compilation_database': encoded(database_bytes(plan['configuration'])),
        'tool_versions': {'gcc': COMPILER_VERSION, 'g++': COMPILER_VERSION, 'cppcheck': plan['tool_version']},
        'binary_sha256': hashlib.sha256(b'synthetic executable placeholder').hexdigest()}
    receipt = {'schema': 'nico.worker-native-receipt.v3', 'identity': asdict(job), 'lease_id': 'e' * 32,
        'worker_id': 'github:123456:12345678:1', 'image_digest': plan['image_digest'], 'tool_version': plan['tool_version'],
        'configuration_sha256': _digest(plan['configuration']), 'target_hashes': plan['targets'],
        'native': native, 'native_sha256': _digest(native)}
    return job, receipt


def validate_configured(plan, receipt):
    from nico.assessment_worker_receipts import validate_receipt
    from scripts.worker_protocol_fixture import identity
    from nico.assessment_worker_jobs import _digest
    receipt['native_sha256'] = _digest(receipt['native'])
    return validate_receipt(identity(plan), plan, receipt['lease_id'], receipt['worker_id'], receipt)[1]


def test_configured_receipt_requires_all_native_populations():
    plan = configured_contract(); _, receipt = configured_receipt(plan)
    record = validate_configured(plan, receipt)
    assert record['completed']
    coverage = record['cppcheck_source_coverage']
    assert coverage['observed_target_count'] == 2
    assert coverage['header_context_verified'] and coverage['configuration_aware']
    assert coverage['observed_headers'] == ['include/value.h']
    assert {row['translation_unit'] for row in coverage['header_contexts']} == {'main.cpp', 'value.cpp'}
    assert record['cpp_build_evidence']['native_test'] == {'required': 1, 'executed': 1, 'passed': 1}
    assert not record['cpp_build_evidence']['sanitizers_executed']
    assert not record['client_delivery_allowed']


def test_build_and_test_proof_survives_the_existing_compact_projection():
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
    plan = configured_contract(); _, receipt = configured_receipt(plan)
    record = validate_configured(plan, receipt)
    record['raw_artifact_retention_complete'] = True
    record['raw_artifact_sha256'] = 'f' * 64
    projected = compact_scanner_records({'scan_id': record['scan_id'], 'scanner_results': [record]},
                                        commit_sha=record['commit_sha'])
    assert projected[0]['cpp_build_evidence'] == record['cpp_build_evidence']
    assert projected[0]['cppcheck_source_coverage'] == record['cppcheck_source_coverage']


@pytest.mark.parametrize('change', ['build_failure', 'link_failure', 'test_failure', 'missing_header',
    'missing_analyzer_target', 'invalid_xml', 'truncated_output', 'timeout', 'unattempted'])
def test_native_failure_or_omission_cannot_become_complete(change):
    plan = configured_contract(); _, receipt = configured_receipt(plan)
    steps = receipt['native']['steps']
    if change == 'build_failure': steps[0]['exit_code'] = 1
    elif change == 'link_failure': steps[-2]['exit_code'] = 1
    elif change == 'test_failure': steps[-1]['exit_code'] = 47
    elif change == 'missing_header':
        for index in [0, 1]:
            path = plan['configuration']['translation_units'][index]['path']
            steps[index * 2]['artifact'] = base64.b64encode(f'unit-{index}: {path}\n'.encode()).decode()
    elif change == 'missing_analyzer_target': steps[1]['stdout'] = ''
    elif change == 'invalid_xml': steps[1]['artifact'] = base64.b64encode(b'<broken').decode()
    elif change == 'truncated_output': steps[1]['output_truncated'] = True
    elif change == 'timeout': steps[-1].update(timed_out=True, exit_code=124)
    elif change == 'unattempted': steps[-1].update(attempted=False, exit_code=None, duration_ms=0)
    record = validate_configured(plan, receipt)
    assert not record['completed']
    assert record['cppcheck_source_coverage']['requested_target_count'] == 2
    assert record['cppcheck_source_coverage']['required_headers'] == ['include/value.h']
    if change == 'test_failure':
        assert record['status'] == 'failed'
        assert record['cpp_build_evidence']['build_completed']
        assert record['cpp_build_evidence']['native_test']['passed'] == 0


@pytest.mark.parametrize('change', ['command', 'database', 'missing_step', 'compiler', 'binary_hash', 'duration', 'schema'])
def test_substituted_configured_evidence_is_rejected(change):
    plan = configured_contract(); _, receipt = configured_receipt(plan)
    native = receipt['native']
    if change == 'command': native['steps'][0]['invocation'].append('-DBIAS=3')
    elif change == 'database': native['compilation_database'] = base64.b64encode(b'[]').decode()
    elif change == 'missing_step': native['steps'].pop()
    elif change == 'compiler': native['tool_versions']['gcc'] = 'other'
    elif change == 'binary_hash': native['binary_sha256'] = 'wrong'
    elif change == 'duration': native['steps'][0]['duration_ms'] = 100000000
    else: receipt['schema'] = 'nico.worker-native-receipt.v2'
    with pytest.raises(ValueError): validate_configured(plan, receipt)


def test_header_parse_evidence_comes_from_the_compiler_not_inventory():
    from nico.assessment_cpp_configuration import dependencies
    assert dependencies(b'unit-0: ./main.cpp \\\n include/value.h\n', unit='main.cpp',
        targets=['main.cpp', 'include/value.h'], index=0) == ['include/value.h', 'main.cpp']
    with pytest.raises(ValueError):
        dependencies(b'unit-0: main.cpp /etc/host-secret\n', unit='main.cpp', targets=['main.cpp'], index=0)


@pytest.fixture
def configured_docker(tmp_path, monkeypatch):
    plan = configured_contract()
    source = tmp_path / 'source'; source.mkdir()
    for name in plan['targets']:
        path = source / name; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode())
    _, receipt = configured_receipt(plan)
    native = receipt['native']; native['steps'].pop()
    binary = b'synthetic executable placeholder'
    native['binary'] = base64.b64encode(binary).decode()
    events = tmp_path / 'events.jsonl'
    executable = tmp_path / 'docker'
    executable.write_text(f'''#!{sys.executable}
import json,pathlib,sys
events=pathlib.Path({str(events)!r})
args=sys.argv[1:]
with events.open('a') as out: out.write(json.dumps(args)+'\\n')
if args[:2]==['image','inspect']: print(json.dumps([{{'Id':args[2]}}]))
elif args[0]=='create': print('created')
elif args[0]=='start':
 payload=json.loads(sys.stdin.buffer.read())
 rows=[json.loads(line) for line in events.read_text().splitlines()]
 created=[row for row in rows if row[0]=='create']
 index=len(created)
 pathlib.Path({str(tmp_path)!r},'payload-'+str(index)+'.json').write_text(json.dumps(payload))
 if index==1: print({json.dumps(native)!r})
 else:
  print('owned native test output')
  sys.exit(47)
elif args[0]=='rm': print('removed')
else: sys.exit(2)
''')
    executable.chmod(0o755)
    monkeypatch.setenv('PATH', str(tmp_path))
    return plan, source, events


def test_native_test_is_separate_and_its_nonzero_exit_is_preserved(configured_docker):
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan, source, events = configured_docker
    result = run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    assert result['native']['steps'][-1]['exit_code'] == 47
    assert base64.b64decode(result['native']['steps'][-1]['stdout']) == b'owned native test output\n'
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    creates = [row for row in rows if row[0] == 'create']
    assert len(creates) == 2 and creates[0][2] != creates[1][2]
    assert len([row for row in rows if row[:2] == ['rm', '--force']]) == 2
    second = json.loads((events.parent / 'payload-2.json').read_text())
    assert set(second['inputs']) == {'native-test'}
    assert 'commands' not in second and 'database' not in second
    for argv in creates:
        assert '--network=none' in argv and '--read-only' in argv
        assert '--cap-drop=ALL' in argv and '--security-opt=no-new-privileges' in argv
        assert not any(arg.startswith(('--env', '--mount', '--volume', '--privileged')) for arg in argv)


def test_configured_source_substitution_stops_before_execution(configured_docker):
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan, source, events = configured_docker
    (source / 'main.cpp').write_bytes(b'changed')
    with pytest.raises(ValueError, match='digest_or_budget_mismatch'):
        run_isolated_cppcheck(plan, source, checkpoint=lambda: None, timeout_seconds=10)
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert not any(row[0] == 'create' for row in rows)


def test_lost_lease_after_second_creation_prevents_native_execution(configured_docker):
    from nico.assessment_worker_container import run_isolated_cppcheck
    plan, source, events = configured_docker
    def checkpoint():
        if events.exists():
            rows = [json.loads(line) for line in events.read_text().splitlines()]
            if sum(row[0] == 'create' for row in rows) == 2:
                raise ValueError('lease_lost')
    with pytest.raises(ValueError, match='lease_lost'):
        run_isolated_cppcheck(plan, source, checkpoint=checkpoint, timeout_seconds=10)
    rows = [json.loads(line) for line in events.read_text().splitlines()]
    assert sum(row[0] == 'start' for row in rows) == 1
    assert sum(row[:2] == ['rm', '--force'] for row in rows) == 2
