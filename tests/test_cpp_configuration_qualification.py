"""Qualification preparation must retain real plans, never infer execution."""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from nico import assessment_cpp_configuration_probe as execution


def capability():
    function = getattr(execution, 'probe_project_configuration', None)
    assert callable(function), 'missing isolated configure-first qualification capability'
    return function


def source(tmp_path):
    root = tmp_path / 'source'
    root.mkdir()
    (root / 'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.22)\nproject(owned LANGUAGES C CXX)\nadd_executable(owned main.cpp)\n')
    (root / 'main.cpp').write_text('int main() { return 0; }\n')
    return root, {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in root.iterdir()}


def boundary():
    return {'uid': 1000, 'gid': 1000, 'no_new_privileges': True,
        'work_root_owned_sticky': True, 'analysis_private': True, 'analysis_write_denied': True,
        'source_read_only': True, 'effective_capabilities': 0, 'cpu_max': '200000 100000',
        'memory_max': '2147483648', 'pids_max': '256', 'swap_max': '0',
        'work_mount': ['rw', 'nosuid', 'nodev'], 'root_read_only': True,
        'docker_socket_absent': True, 'credential_environment_absent': True,
        'external_network_blocked': True}


class Docker:
    """Only the inaccessible Docker boundary is replaced, not qualification logic."""
    def __init__(self, targets, *, configure_exit=0, bad_boundary=False, image_mismatch=False, truncated=False, unused_option=False):
        self.targets, self.configure_exit = targets, configure_exit
        self.bad_boundary, self.image_mismatch, self.truncated = bad_boundary, image_mismatch, truncated
        self.unused_option = unused_option
        self.calls = []

    def __call__(self, args, **kwargs):
        self.calls.append((args, kwargs))
        assert args[0] == 'docker', 'no assessed command may run on the controller'
        raw, code, truncated = b'', 0, False
        if args[:3] == ['docker', 'image', 'inspect']:
            raw = json.dumps([{'Id': 'sha256:' + ('b' if self.image_mismatch else 'a') * 64}]).encode()
        elif execution.ANALYSIS_SETUP_PROGRAM in args:
            raw = b'{"uid":1001,"gid":1001,"private":true}'
        elif execution.BOUNDARY_PROGRAM in args:
            value = boundary()
            if self.bad_boundary: value['external_network_blocked'] = False
            raw = json.dumps(value).encode()
        elif execution.INPUT_PROGRAM in args:
            raw = json.dumps(self.targets).encode()
        elif execution.READ_PROGRAM in args:
            database = [{'directory':'/work/build', 'file':'/work/source/main.cpp',
                         'command':'/usr/local/bin/g++ -O2 -o main.o -c /work/source/main.cpp'}]
            data = (b'BUILD_TESTS:UNINITIALIZED=ON\n' if self.unused_option else b'BUILD_TESTS:BOOL=ON\n') if '/work/build/CMakeCache.txt' in args else json.dumps(database).encode()
            raw = json.dumps({'data': base64.b64encode(data).decode(),
                              'truncated': self.truncated}).encode()
        elif 'cmake' in args:
            if args[-1] == '--version': raw = b'cmake version 3.31.6\n'
            else: raw, code = b'configuration output\n', self.configure_exit
        elif args[-2:] == ['g++', '-dumpfullversion']:
            raw = b'14.2.0\n'
        elif args[-2:] == ['gcc', '-dumpfullversion']:
            raw = b'14.2.0\n'
        elif args[-2:] == ['cat', '/sys/fs/cgroup/memory.peak']:
            raw = b'12345678\n'
        return {'exit_code': code, 'timed_out': False, 'output_truncated': truncated, 'output': raw}


def run(tmp_path, **fault):
    root, targets = source(tmp_path)
    docker = Docker(targets, **fault)
    retained = []
    result = capability()(root, targets, 'sha256:' + 'a'*64, project_options={'BUILD_TESTS':'ON'},
                          retain=lambda r: retained.append(json.loads(json.dumps(r))), command=docker)
    return result, docker, retained


def test_real_plan_capture_is_not_compile_test_or_full_project_success(tmp_path):
    result, docker, retained = run(tmp_path)
    assert result['status'] == 'CONFIGURATION_CAPTURED'
    assert result['configured_translation_units'] == ['main.cpp']
    assert result['compiled'] is False and result['tests_executed'] is False
    assert result['full_project_qualified'] is False
    assert result['memory_peak_bytes'] == 12345678
    assert retained[0]['status'] == 'UNPROVEN'
    assert retained[-1] == result
    create = next(args for args, _ in docker.calls if args[1] == 'create')
    assert '--network=none' in create and '--read-only' in create and '--cap-drop=ALL' in create
    assert '--security-opt=no-new-privileges' in create and '--user=1000:1000' in create
    assert not any(arg in {'-v', '--mount', '--privileged'} for arg in create)
    configure = next(args for args, _ in docker.calls if 'cmake' in args and '-S' in args)
    assert '-DBUILD_TESTS=ON' in configure
    assert not any('--build' in args or 'ctest' in args for args, _ in docker.calls)
    assert docker.calls[-1][0][1:3] == ['rm', '--force']


@pytest.mark.parametrize('fault', [dict(configure_exit=1), dict(bad_boundary=True),
                                  dict(image_mismatch=True), dict(truncated=True)])
def test_failed_or_untrusted_configuration_stays_unproven(tmp_path, fault):
    result, docker, retained = run(tmp_path, **fault)
    assert result['status'] == 'UNPROVEN'
    assert result['full_project_qualified'] is False
    if fault.get('configure_exit'):
        assert any(row['exit_code'] == 1 for row in result['operations'])
    assert retained[-1] == result


@pytest.mark.parametrize('options', [{'CMAKE_PROJECT_INCLUDE':'/tmp/payload'}, {'X':'a;b'},
    {'X':'https://example.invalid'}, {'X':True}, {'X':'-DFOO=bar'}])
def test_no_project_option_can_change_the_trusted_configure_invocation(tmp_path, options):
    root, targets = source(tmp_path)
    docker = Docker(targets)
    with pytest.raises(ValueError):
        capability()(root, targets, 'sha256:' + 'a'*64, project_options=options, command=docker)
    assert docker.calls == []


def test_interruption_retains_returned_configure_bytes_before_next_operation(tmp_path):
    root, targets = source(tmp_path)
    docker = Docker(targets)
    retained = []
    def interrupted(args, **kwargs):
        if execution.READ_PROGRAM in args: raise KeyboardInterrupt()
        return docker(args, **kwargs)
    result = capability()(root, targets, 'sha256:'+'a'*64, project_options={}, command=interrupted,
                          retain=lambda r: retained.append(json.loads(json.dumps(r))))
    assert result['status'] == 'UNPROVEN'
    assert any(row['id'] == 'configure' and row['exit_code'] == 0 for row in result['operations'])
    assert any(any(row['id'] == 'configure' for row in r['operations']) for r in retained)
    assert docker.calls[-1][0][1:3] == ['rm', '--force']


def test_full_checkout_population_is_hash_bound_before_container_execution(tmp_path):
    from scripts import qualify_cpp_project_configuration as integration
    function = getattr(integration, 'freeze_configuration_checkout', None)
    assert callable(function), 'missing complete immutable checkout inventory'
    checkout = tmp_path / 'repo'
    checkout.mkdir()
    (checkout/'CMakeLists.txt').write_text('project(owned LANGUAGES CXX)\n')
    (checkout/'main.cpp').write_text('int main() { return 0; }\n')
    (checkout/'data.txt').write_bytes(b'non-source bytes\n')
    def git(*args):
        return subprocess.run(['git', '-C', str(checkout), *args], check=True, capture_output=True,
            env={'PATH':'/usr/bin:/bin','GIT_CONFIG_NOSYSTEM':'1','GIT_CONFIG_GLOBAL':'/dev/null',
                 'GIT_AUTHOR_NAME':'Fixture','GIT_COMMITTER_NAME':'Fixture',
                 'GIT_AUTHOR_EMAIL':'fixture@example.invalid','GIT_COMMITTER_EMAIL':'fixture@example.invalid'}).stdout.decode().strip()
    git('init', '-q'); git('add', '.'); git('commit', '-qm', 'owned')
    manifest = {'schema':'nico.cpp-configuration-benchmark.v1', 'repository':'nico/owned-fixture',
        'commit_sha':git('rev-parse','HEAD'), 'tree_sha':git('rev-parse','HEAD^{tree}'),
        'inventory':{'entries':3,'blobs':3,'source_bytes':sum(p.stat().st_size for p in checkout.iterdir() if p.is_file())},
        'project_options':{}}
    output = tmp_path/'frozen'
    receipt = function(checkout, output, manifest)
    assert receipt['inventory_complete'] is True
    assert len(receipt['targets']) == 3
    assert receipt['materialized_files'] == 3
    assert receipt['compiled'] is False
    assert set(receipt['targets']) == {'CMakeLists.txt','main.cpp','data.txt'}
    for name, digest in receipt['targets'].items():
        assert hashlib.sha256((output/name).read_bytes()).hexdigest() == digest
    (checkout/'main.cpp').write_text('modified after checkout\n')
    with pytest.raises(ValueError, match='digest'):
        function(checkout, tmp_path/'changed', manifest)
    assert not (tmp_path/'changed').exists(), 'failed inventory must never be promoted'


def test_live_checkout_must_match_frozen_revision_and_whole_tree(tmp_path):
    from scripts import qualify_cpp_project_configuration as integration
    function = getattr(integration, 'freeze_configuration_checkout', None)
    assert callable(function), 'missing complete immutable checkout inventory'
    # Wrong/malformed frozen identities are rejected before invoking Git or Docker.
    with pytest.raises(ValueError):
        function(tmp_path, tmp_path/'frozen', {'schema':'invalid'})


def test_pinned_large_configuration_is_wired_after_owned_native_success():
    root = Path(__file__).resolve().parents[1]
    workflow = (root/'.github/workflows/cpp-full-project-integration.yml').read_text()
    assert 'tests/test_cpp_configuration_qualification.py' in workflow
    assert '--qualification-source' in workflow
    assert workflow.index('--project-compiler-options --image') < workflow.index('--qualification-source')
    assert 'cpp-configuration-qualification/' in workflow


def test_a_cmake_command_line_option_is_not_a_verified_effective_option(tmp_path):
    result, docker, retained = run(tmp_path, unused_option=True)
    assert result['status'] == 'UNPROVEN'
    assert result['error'] == 'worker_configuration_probe_option_unverified'


def test_effective_options_and_exact_cache_bytes_are_retained(tmp_path):
    result, docker, retained = run(tmp_path)
    assert result['effective_project_options'] == {'BUILD_TESTS': 'ON'}
    raw = base64.b64decode(result['configuration_cache'])
    assert hashlib.sha256(raw).hexdigest() == result['configuration_cache_sha256']


def test_large_static_analysis_is_projected_to_hash_bound_receipt_summary():
    from scripts import qualify_cpp_project_configuration as integration
    function = getattr(integration, 'qualification_probe_receipt', None)
    assert callable(function), 'missing bounded qualification receipt projection'
    analysis = {
        'complete': True,
        'required_contexts': [f'ctx-{i}' for i in range(475)],
        'attempted_contexts': [f'ctx-{i}' for i in range(475)],
        'analyzed_contexts': [f'ctx-{i}' for i in range(475)],
        'findings': [{'id': f'f-{i}', 'path': 'src/example.cpp', 'line': i + 1} for i in range(25000)],
        'limitations': [{'context_id': f'ctx-{i%475}', 'rule_id': 'modeled-input'} for i in range(25000)],
        'modeled_inputs': [{'context_id': f'ctx-{i%475}', 'header_name': 'vector', 'model': 'std'} for i in range(25000)],
        'native_evidence_sha256': 'a' * 64,
        'compiler_evidence_sha256': 'b' * 64,
        'artifact': {'path': 'artifacts/project-static-evidence-' + 'a'*64 + '.json',
                     'sha256': 'a'*64, 'bytes': 3878970},
        'human_review_completed': False,
        'production_qualified': False,
    }
    probe = {'schema': 'nico.cpp-project-configuration-probe.v7',
             'project_static': analysis,
             'project_static_stage': {'complete': True, 'analysis': analysis, 'operations': []}}
    projected = function(probe)
    assert probe['project_static']['findings'][0]['id'] == 'f-0', 'projection must not mutate live proof'
    summary = projected['project_static']
    assert summary['receipt_projection'] == 'hash-bound-summary-v1'
    for key in ('required_contexts', 'attempted_contexts', 'analyzed_contexts',
                'findings', 'limitations', 'modeled_inputs'):
        assert key not in summary
        assert summary[key + '_count'] == len(analysis[key])
        assert len(summary[key + '_sha256']) == 64
    assert summary['artifact'] == analysis['artifact']
    assert projected['project_static_stage']['analysis'] == summary
    assert len(integration.canonical_bytes(projected)) < 512 * 1024
