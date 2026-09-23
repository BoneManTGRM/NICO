"""Reconciled library-input expansion and actual interrupted-provisioning tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest
from scripts import provision_cpp_fuzz_tools as tool


EVENT_NAMES = ('libevent-2.1-7', 'libevent-core-2.1-7', 'libevent-dev',
               'libevent-extra-2.1-7', 'libevent-openssl-2.1-7', 'libevent-pthreads-2.1-7')


def expanded_lock():
    from tests.test_cpp_project_dependencies import project_lock
    value = project_lock(); value['schema'] = 'nico.cpp-project-dependencies.v2'
    for name in EVENT_NAMES:
        version = '2.1.12-stable-8+deb12u1'
        value['packages'].append({'package': name, 'version': version, 'architecture': 'amd64',
            'bytes': 4, 'sha256': hashlib.sha256(b'test').hexdigest(),
            'url': 'https://security.debian.org/debian-security/pool/updates/main/libe/libevent/'
                   + name + '_' + version + '_amd64.deb'})
    return value


def test_complete_libevent_lock_composes_with_original_dependencies():
    value = expanded_lock()
    assert tool.validate_lock(value) == value['packages']
    from tests.test_cpp_project_dependencies import project_lock
    original = project_lock()
    assert tool.validate_lock(original) == original['packages']


@pytest.mark.parametrize('change', ['missing', 'duplicate', 'origin', 'version', 'scheme', 'pair', 'size', 'hash'])
def test_libevent_identity_population_and_budget_cannot_be_substituted(change):
    value = expanded_lock(); item = value['packages'][-1]
    if change == 'missing': value['packages'].pop()
    if change == 'duplicate': value['packages'][-1] = deepcopy(value['packages'][-2])
    if change == 'origin': item['url'] = item['url'].replace('security.debian.org', 'example.invalid')
    if change == 'scheme': item['url'] = item['url'].replace('https:', 'http:')
    if change == 'version': item['version'] = '2.1.12-stable-7'
    if change == 'pair':
        item['version'] = '2.1.12-stable-9'
        item['url'] = item['url'].replace('2.1.12-stable-8+deb12u1', item['version'])
    if change == 'size': item['bytes'] = 16 * 1024 * 1024
    if change == 'hash': item['sha256'] = 'x' * 64
    with pytest.raises(ValueError): tool.validate_lock(value)


def test_expanded_fixed_inputs_download_and_retain_exact_lock(tmp_path, monkeypatch):
    value = expanded_lock(); path = tmp_path / 'lock.json'; path.write_text(json.dumps(value))
    monkeypatch.setattr(tool, 'PROJECT_LOCK', path)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert args[:2] == ['curl', '--disable'] and '-L' not in args
        assert set(kwargs['env']) == {'PATH'} and kwargs['timeout'] <= 31
        Path(args[args.index('--output') + 1]).write_bytes(b'test')
    output = tmp_path / 'inputs'
    result = tool.provision(output, project_dependencies=True, run=run)
    assert result['status'] == 'VERIFIED_TOOL_INPUTS' and len(result['packages']) == 9
    assert len(calls) == 9 and not result['installed'] and not result['target_executed']
    assert (output / 'lock.json').read_bytes() == path.read_bytes()
    assert result['lock_sha256'] == hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.mark.parametrize('project', [False, True])
def test_returned_package_survives_real_abrupt_exit(tmp_path, project):
    value = json.loads((tool.PROJECT_LOCK if project else tool.LOCK).read_bytes())
    for row in value['packages']:
        row.update(bytes=4, sha256=hashlib.sha256(b'test').hexdigest())
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(value)); dest = tmp_path / 'interrupted'
    program = '''
import os, sys
from pathlib import Path
from scripts import provision_cpp_fuzz_tools as tool
project = sys.argv[3] == 'True'
if project: tool.PROJECT_LOCK = Path(sys.argv[1])
else: tool.LOCK = Path(sys.argv[1])
count = 0
def run(argv, **kwargs):
    global count
    count += 1
    if count == 2: os._exit(73)
    Path(argv[argv.index('--output')+1]).write_bytes(b'test')
tool.provision(Path(sys.argv[2]), project_dependencies=project, run=run)
'''
    result = subprocess.run([sys.executable, '-c', program, str(lock), str(dest), str(project)],
                            capture_output=True, timeout=10)
    assert result.returncode == 73, result.stderr.decode()
    assert (dest / 'receipt.json').is_file(), 'verified input lost on abrupt exit'
    receipt = json.loads((dest / 'receipt.json').read_bytes())
    assert receipt['status'] == 'UNPROVEN' and len(receipt['packages']) == 1
    assert not receipt['installed'] and not receipt['target_executed']
    assert not (dest / 'SHA256SUMS').exists()


@pytest.mark.parametrize('project, elapsed', [(False, 91), (True, 31)])
def test_aggregate_budget_is_not_reset_between_inputs(tmp_path, monkeypatch, project, elapsed):
    value = json.loads((tool.PROJECT_LOCK if project else tool.LOCK).read_bytes())
    for row in value['packages']: row.update(bytes=4, sha256=hashlib.sha256(b'test').hexdigest())
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(value))
    monkeypatch.setattr(tool, 'PROJECT_LOCK' if project else 'LOCK', lock)
    now, calls = [0], []
    monkeypatch.setattr(tool.time, 'monotonic', lambda: now[0])
    def run(argv, **kwargs):
        calls.append(argv); Path(argv[argv.index('--output')+1]).write_bytes(b'test'); now[0] = elapsed
    dest = tmp_path / 'inputs'
    with pytest.raises(ValueError, match='download_deadline'):
        tool.provision(dest, project_dependencies=project, run=run)
    receipt = json.loads((dest/'receipt.json').read_bytes())
    assert len(calls) == 1 and len(receipt['packages']) == 1 and receipt['status'] == 'UNPROVEN'


def test_nested_control_really_uses_event_library_without_reverting_prior_features():
    from scripts.qualify_cpp_full_project_integration import fixture, plan
    files = fixture(generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    cpp, cmake = files['src/library/sum.cpp'], files['src/library/CMakeLists.txt']
    for required in ('event_base_new()', 'event_base_free(', 'evthread_use_pthreads()', 'event_get_version_number()'):
        assert required in cpp, 'native control does not exercise Libevent'
    assert 'event_pthreads' in cmake and 'NICO_EVENT_LIBRARY' in cmake
    assert 'find_package(Boost 1.74.0 EXACT CONFIG REQUIRED)' in cmake
    assert 'Boost::headers SQLite::SQLite3' in cmake
    contract = plan('sha256:' + 'a' * 64, generated_headers=True, bounded_fuzz=True, project_dependencies=True)
    assert contract['configuration']['schema'] == 'nico.cpp-cmake-configuration.v6'
    assert contract['configuration']['translation_units'] == ['main.cpp', 'src/library/sum.cpp']
    assert contract['targets'] == {path: hashlib.sha256(text.encode()).hexdigest() for path, text in files.items()}


def test_workflow_retains_lock_and_exercises_new_regressions():
    root = Path(__file__).resolve().parents[1]
    workflow = (root/'.github/workflows/cpp-full-project-integration.yml').read_text()
    image = (root/'docker/assessment-full-project-fuzz.Dockerfile').read_text()
    assert 'tests/test_cpp_dependency_retention.py' in workflow
    assert 'toolchain/full-project/project-dependencies/lock.json' in workflow
    assert 'cp lock.json receipt.json SHA256SUMS' in image
    assert 'apt-get' not in image


@pytest.mark.parametrize('schema', [[], {}])
def test_malformed_schema_is_rejected_without_type_error(schema):
    with pytest.raises(ValueError): tool.validate_lock({'schema': schema})
