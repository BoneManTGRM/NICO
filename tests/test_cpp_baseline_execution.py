"""Frozen whole-project build evidence must never collapse into config success."""
import base64
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path

import pytest
from nico import assessment_cpp_configuration_probe as probe
from nico.assessment_worker_capacity_v1 import resources_for, docker_resource_args
from tests.test_cpp_configuration_qualification import Docker, source, boundary

PROFILE = 'cpp-baseline-qualification-v1'
DB = [{'directory':'/work/build', 'file':'/work/source/main.cpp',
       'command':'/usr/local/bin/g++ -O2 -o main.o -c /work/source/main.cpp'}]


def contract():
    return {'schema':'nico.cpp-baseline-execution.v1', 'profile':PROFILE,
            'compilation_database_sha256':hashlib.sha256(json.dumps(DB).encode()).hexdigest(),
            'build_seconds':1200, 'test_seconds':480, 'test_case_seconds':60,
            'parallel':4}


class Native(Docker):
    def __init__(self, targets, fault=None):
        super().__init__(targets)
        self.fault = fault

    def __call__(self, args, **kwargs):
        if getattr(probe, 'SCRATCH_PROGRAM', None) in args:
            self.calls.append((args,kwargs))
            return {'exit_code':0,'timed_out':False,'output_truncated':False,
                    'output':json.dumps({'capacity_bytes':9663676416, 'available_bytes':9663676416}).encode()}
        if probe.BOUNDARY_PROGRAM in args:
            self.calls.append((args, kwargs))
            b = boundary(); b.update(cpu_max='400000 100000', memory_max='12884901888')
            if self.fault == 'boundary': b['memory_max'] = 'max'
            return {'exit_code':0,'timed_out':False,'output_truncated':False,
                    'output':json.dumps(b).encode()}
        if 'ctest' in args:
            self.calls.append((args, kwargs))
            raw = (json.dumps({'kind':'ctestInfo','version':{'major':1,'minor':0},
                               'tests':[{'name':'owned_suite','command':['/work/build/owned']}]}).encode()
                   if '--show-only=json-v1' in args else b'1/1 passed\n')
            return {'exit_code':8 if self.fault == 'test' and '--show-only=json-v1' not in args else 0,
                    'timed_out':False,'output_truncated':False,'output':raw}
        if probe.READ_PROGRAM in args and '/work/build/nico-baseline-junit.xml' in args:
            self.calls.append((args, kwargs))
            outcome = '<failure/>' if self.fault == 'junit' else ''
            raw = ('<testsuite tests="1"><testcase name="owned_suite">'+outcome+'</testcase></testsuite>').encode()
            return {'exit_code':0,'timed_out':False,'output_truncated':False,
                    'output':json.dumps({'data':base64.b64encode(raw).decode(),'truncated':False}).encode()}
        if 'cmake' in args and '--build' in args:
            self.calls.append((args, kwargs))
            return {'exit_code':2 if self.fault == 'build' else 0,
                    'timed_out':self.fault == 'timeout','output_truncated':False,'output':b'owned build output\n'}
        return super().__call__(args, **kwargs)


def execute(tmp_path, fault=None, spec=None):
    assert 'baseline_execution' in inspect.signature(probe.probe_project_configuration).parameters, 'missing actual baseline execution'
    root, targets = source(tmp_path)
    docker = Native(targets, fault)
    saved = []
    result = probe.probe_project_configuration(root, targets, 'sha256:'+'a'*64,
        project_options={'BUILD_TESTS':'ON'}, baseline_execution=spec or contract(),
        command=docker, retain=lambda r:saved.append(deepcopy(r)))
    return result, docker, saved


def test_whole_build_and_all_discovered_tests_use_frozen_capacity(tmp_path):
    result, docker, saved = execute(tmp_path)
    assert result['status'] == 'BASELINE_EXECUTED'
    assert result['compiled'] is True and result['tests_executed'] is True
    assert result['full_project_qualified'] is False  # Static/sanitizer/production separate.
    assert result['tests_discovered'] == ['owned_suite']
    assert result['tests_passed'] is True
    assert result['execution_budget_seconds'] == 1800
    create = next(a for a,k in docker.calls if a[1] == 'create')
    for flag in ('--memory=12g','--memory-swap=12g','--cpus=4','--pids-limit=256',
                 '--network=none','--read-only','--cap-drop=ALL','--security-opt=no-new-privileges'):
        assert flag in create
    assert not any(x in create for x in ('--mount','-v','--privileged'))
    build, kwargs = next((a,k) for a,k in docker.calls if '--build' in a)
    assert build[-5:] == ['cmake','--build','/work/build','--parallel','4']
    assert kwargs['timeout'] <= 1200 and '--target' not in build
    test = next(a for a,k in docker.calls if 'ctest' in a and '--output-junit' in a)
    assert not any(v in test for v in ('-R','-E','--exclude-regex'))
    assert saved[-1] == result


@pytest.mark.parametrize('fault',['boundary','build','timeout','test','junit'])
def test_failure_preserves_evidence_and_never_passes_whole_scope(tmp_path,fault):
    result, docker, saved = execute(tmp_path,fault)
    assert result['status'] == 'UNPROVEN'
    assert result['full_project_qualified'] is False
    assert result['cleanup_verified'] is True
    if fault in ('build','timeout'):
        assert any(row['id']=='baseline-build' for row in result['operations'])
        assert not any('ctest' in a and '--output-junit' in a for a,k in docker.calls)
    if fault == 'test':
        assert result['compiled'] is True
        assert result['tests_executed'] is True and result['tests_passed'] is False
    assert saved[-1] == result


def test_wrong_frozen_database_stops_before_build(tmp_path):
    spec=contract(); spec['compilation_database_sha256']='b'*64
    result,docker,saved=execute(tmp_path,spec=spec)
    assert result['status']=='UNPROVEN'
    assert not any('--build' in a for a,k in docker.calls)


@pytest.mark.parametrize('field,value',[('profile','cpp-full-project-v1'),('parallel',True),
    ('parallel',8),('build_seconds',1201),('test_seconds',481),('test_case_seconds',0),
    ('compilation_database_sha256','bogus')])
def test_unbounded_or_unknown_execution_contract_is_rejected_before_docker(tmp_path,field,value):
    spec=contract(); spec[field]=value
    with pytest.raises(ValueError): execute(tmp_path,spec=spec)


def test_new_resource_class_keeps_old_profiles_and_production_selection_unchanged():
    from nico.assessment_worker_capacity_v1 import select_production_profile
    r=resources_for(PROFILE)
    assert r['memory_bytes']==12884901888 and r['tmpfs_bytes']==9663676416
    assert resources_for('cpp-full-project-v1')['memory_bytes']==2147483648
    assert resources_for('cppcheck-standalone-v1')['memory_bytes']==268435456
    assert r['sufficient_for_bitcoin_compile'] is None
    assert select_production_profile({'profile':PROFILE}) is None


def test_published_baseline_job_is_serial_bounded_and_has_no_production_credentials():
    import yaml
    root=Path(__file__).resolve().parents[1]
    workflow=yaml.safe_load((root/'.github/workflows/cpp-full-project-integration.yml').read_text())
    job=workflow['jobs'].get('project-baseline-qualification')
    assert job, 'missing actual whole-project hosted execution'
    assert job['needs']==['owned-project-integration'] and job['timeout-minutes']==40
    assert job['runs-on']=='ubuntu-24.04'
    assert workflow['permissions']=={'contents':'read'}
    assert workflow['jobs']['owned-project-integration']['timeout-minutes']==5
    assert not job.get('services') and not job.get('env')
    text=json.dumps(job)
    assert 'baseline-execution-contract' in text and 'secrets.' not in text


def test_runtime_scratch_capacity_must_be_observed_and_bound(tmp_path):
    result, docker, saved = execute(tmp_path)
    assert result.get('scratch_capacity_verified') is True, 'missing runtime storage-capacity evidence'
    assert result['scratch_capacity_bytes'] == 9663676416


def test_timeout_remains_unproven_even_when_container_cleanup_fails(tmp_path):
    assert 'baseline_execution' in inspect.signature(probe.probe_project_configuration).parameters
    root, targets = source(tmp_path); docker=Native(targets,'timeout')
    def failed_cleanup(args, **kwargs):
        if args[1:3]==['rm','--force']:
            return {'exit_code':1,'timed_out':False,'output_truncated':False,'output':b'failed'}
        return docker(args, **kwargs)
    result=probe.probe_project_configuration(root,targets,'sha256:'+'a'*64,
        project_options={'BUILD_TESTS':'ON'}, baseline_execution=contract(), command=failed_cleanup)
    assert result['cleanup_verified'] is False
    assert result['status']=='UNPROVEN' and result['compiled'] is False
