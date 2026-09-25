"""Actual compiler-environment bytes must flow into the existing static stage."""
from copy import deepcopy
import base64
import hashlib
import inspect
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from nico import assessment_cpp_static_environment as env
from nico import assessment_cpp_project_static as static
from nico.assessment_cpp_project_compiler import _canonical
from tests.test_cpp_static_environment import fixture, evidence
from tests.test_cpp_project_static import native
from tests.test_cpp_project_static_stage import stage_inputs, StaticDocker


def prepared(tmp_path):
    database, targets, snapshot, compiler, compiler_raw = fixture(tmp_path)
    request = env.environment_request(compiler, compiler_raw, 'sha256:'+'a'*64)
    raw = _canonical(evidence(request))
    proof = env.validate_environment(raw, request)
    return database, targets, snapshot, compiler_raw, request, raw, proof


def project(tmp_path):
    database, targets, snapshot, compiler_raw, er, raw, proof = prepared(tmp_path)
    request = static.project_static_request(database, targets, snapshot, compiler_raw, environment=proof)
    return request, proof


def native_v2(request, *, missing=None, checker=True, rule=None):
    result = native(request, rule)
    result['schema'] = 'nico.cpp-project-static-evidence.v2'
    from xml.etree import ElementTree as ET
    for row in result['records']:
        doc = ET.fromstring(base64.b64decode(row['xml']))
        errors = doc.find('errors')
        if checker:
            ET.SubElement(errors, 'error', {'id': 'checkersReport', 'severity': 'information',
                'msg': 'Active checkers: 190/856 (use --checkers-report=<filename> to see details)'})
        if missing:
            ET.SubElement(errors, 'error', {'id': 'missingIncludeSystem', 'severity': 'information',
                'msg': 'Include file: <'+missing+'> not found. Please note: Cppcheck does not need standard library headers to get proper results.'})
        value = ET.tostring(doc)
        row['xml'] = base64.b64encode(value).decode()
        row['xml_sha256'] = hashlib.sha256(value).hexdigest()
    return _canonical(result)


def test_environment_policy_binds_request_without_changing_context_population(tmp_path):
    request, proof = project(tmp_path)
    assert request['schema'] == 'nico.cpp-project-static-request.v2'
    assert len(request['contexts']) == 3
    assert len({r['context_id'] for r in request['contexts']}) == 3
    assert request['compiler_environment'] == proof
    for row in request['contexts']:
        assert any(a.startswith('--include='+env.ROOT) for a in row['analyzer_invocation'])
        assert '--check-level=exhaustive' in row['analyzer_invocation']
    assert static.validate_project_static(native_v2(request), request)['complete']


@pytest.mark.parametrize('missing, complete', [('stdint.h', True), ('missing.h', False),
                                              ('boost/not-compiler-resolved.hpp', False),
                                              ('capnp/generated-header-support.h', False)])
def test_only_compiler_resolved_public_model_inputs_are_nonfatal(tmp_path, missing, complete):
    request, proof = project(tmp_path)
    result = static.validate_project_static(native_v2(request, missing=missing), request)
    assert result['complete'] is complete
    if complete:
        assert len(result['modeled_inputs']) == 3
        assert all(row['header_name'] == 'stdint.h' and row['model'] == 'std'
                   and row['compiler_resolved_headers'] == ['/usr/include/stdint.h']
                   and row['analyzer_header_visited'] is False for row in result['modeled_inputs'])
        assert all('native_evidence_sha256' in row for row in result['modeled_inputs'])
    else:
        assert not result['modeled_inputs']
        assert any(row['rule_id'] == 'missingIncludeSystem' for row in result['limitations'])
    assert result['analyzer_header_coverage_verified'] is False


def test_modeling_never_waives_empty_or_missing_checker_evidence(tmp_path):
    request, _ = project(tmp_path)
    result = static.validate_project_static(native_v2(request, missing='stdint.h', checker=False), request)
    assert not result['complete']
    assert any(row['rule_id'] == 'native_checkers_not_confirmed' for row in result['limitations'])


def test_forged_model_or_compiler_binding_is_rejected_before_dispatch(tmp_path):
    database, targets, snapshot, compiler_raw, er, raw, proof = prepared(tmp_path)
    for field in ('compiler_evidence_sha256', 'header_population_sha256'):
        forged = deepcopy(proof); forged[field] = '0'*64
        with pytest.raises(ValueError):
            static.project_static_request(database, targets, snapshot, compiler_raw, environment=forged)


class EnvironmentDocker(StaticDocker):
    def __call__(self, argv, **kwargs):
        if env.ENV_PROGRAM in argv:
            self.calls.append((argv, kwargs))
            value = evidence(json.loads(kwargs['input_bytes']))
            if self.fault == 'environment-digest': value['request_sha256'] = '0'*64
            return {'exit_code': 2 if self.fault == 'environment-exit' else 0,
                    'timed_out': False, 'output_truncated': False, 'output': _canonical(value)}
        if static.PROGRAM in argv:
            self.calls.append((argv, kwargs))
            value = native_v2(json.loads(kwargs['input_bytes']), missing='stdint.h', rule='uninitvar')
            return {'exit_code': 0, 'timed_out': False, 'output_truncated': False, 'output': value}
        return super().__call__(argv, **kwargs)


@pytest.mark.parametrize('fault', [None, 'environment-digest', 'environment-exit', 'environment-retention'])
def test_real_stage_retains_environment_before_analysis_and_rejects_bad_inputs(tmp_path, fault):
    assert 'compiler_environment' in inspect.signature(static.run_project_static_stage).parameters
    root, targets, database, snapshot, compiler = stage_inputs(tmp_path)
    docker = EnvironmentDocker(targets, fault=fault)
    saved, artifacts = [], {}
    def sink(key, raw):
        artifacts[key] = raw
        if fault == 'environment-retention' and key == 'project-static-environment':
            raise OSError('owned simulated retention failure')
        sha = hashlib.sha256(raw).hexdigest()
        return {'path': 'artifacts/'+key+'-'+sha+'.json', 'sha256': sha, 'bytes': len(raw)}
    result = static.run_project_static_stage(root, targets, 'sha256:'+'a'*64,
        database, snapshot, compiler, compiler_environment=True, command=docker,
        retain_artifact=sink, retain=lambda row: saved.append(deepcopy(row)))
    assert result['cleanup_verified'] and saved[-1] == result
    assert 'project-static-environment' in artifacts
    assert any(row['id'] == 'project-static-environment' for row in result['operations'])
    if fault:
        assert not result['complete'] and result['status'] == 'UNPROVEN'
        assert not any(static.PROGRAM in argv for argv, _ in docker.calls)
    else:
        assert result['complete'] and len(result['analysis']['analyzed_contexts']) == 3
        assert result['compiler_environment']['artifact']['sha256'] == hashlib.sha256(artifacts['project-static-environment']).hexdigest()
        ids = [r['id'] for r in result['operations']]
        assert ids.index('project-static-environment') < ids.index('project-static-evidence')
        assert result['execution_budget_seconds'] == 1020
        assert not result['production_qualified']


def test_both_existing_qualification_paths_enable_the_same_environment_policy():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/cpp-full-project-integration.yml').read_text())
    commands = [step.get('run', '') for job in workflow['jobs'].values() for step in job['steps']]
    owned = next(c for c in commands if 'scripts.qualify_cpp_project_generated_context ' in c)
    large = next(c for c in commands if 'scripts.qualify_cpp_project_configuration ' in c and '--baseline-execution-contract' in c)
    assert '--compiler-environment' in owned and '--compiler-environment' in large
    from scripts import qualify_cpp_project_generated_context as control
    from nico.assessment_cpp_configuration_probe import probe_project_configuration
    assert 'compiler_environment' in inspect.signature(control.qualify).parameters
    assert 'compiler_environment' in inspect.signature(probe_project_configuration).parameters


def test_standalone_program_bytes_are_deterministic_across_hash_seeds():
    command = [sys.executable, '-c', 'from nico.assessment_cpp_static_environment import ENV_PROGRAM;'
        'import hashlib;print(hashlib.sha256(ENV_PROGRAM.encode()).hexdigest())']
    hashes = [subprocess.check_output(command, env={**os.environ, 'PYTHONHASHSEED': seed}) for seed in ('1','2')]
    assert hashes[0] == hashes[1]
    compile(env.ENV_PROGRAM, 'environment', 'exec')
    compile(static.PROGRAM, 'analysis', 'exec')


def test_owned_control_exercises_predefines_implicit_dependencies_and_isystem(tmp_path):
    from scripts.qualify_cpp_project_generated_context import fixture
    assert 'compiler_environment' in inspect.signature(fixture).parameters
    root = tmp_path/'owned'
    targets = fixture(root, compiler_environment=True)
    assert 'environment.h.in' in targets
    assert '#include <boost/version.hpp>' in (root/'repeated.cpp').read_text()
    assert '#include <cstdint>' in (root/'repeated.cpp').read_text()
    assert '#ifndef __GNUC__' in (root/'repeated.cpp').read_text()
    assert '#include <owned_environment.h>' in (root/'repeated.cpp').read_text()
    cmake = (root/'CMakeLists.txt').read_text()
    assert 'SYSTEM PRIVATE' in cmake
    assert 'environment/owned_environment.h' in cmake


def test_environment_stage_uses_the_real_immutable_artifact_sink(tmp_path):
    from scripts.qualify_cpp_project_configuration import persist_project_artifact
    root, targets, database, snapshot, compiler = stage_inputs(tmp_path)
    output = tmp_path/'retained'; output.mkdir()
    result = static.run_project_static_stage(root, targets, 'sha256:'+'a'*64,
        database, snapshot, compiler, compiler_environment=True,
        command=EnvironmentDocker(targets),
        retain_artifact=lambda key, raw: persist_project_artifact(output, key, raw))
    assert result['complete'], result['error']
    reference = result['compiler_environment']['artifact']
    raw = (output/reference['path']).read_bytes()
    assert reference['bytes'] == len(raw)
    assert reference['sha256'] == hashlib.sha256(raw).hexdigest()
    assert persist_project_artifact(output, 'project-static-environment', raw) == reference
    path = output/reference['path']; path.write_bytes(b'corrupt owned evidence')
    with pytest.raises(ValueError, match='qualification_artifact_existing_mismatch'):
        persist_project_artifact(output, 'project-static-environment', raw)


def test_environment_static_evidence_accepts_bounded_compressed_xml(tmp_path):
    request, _ = project(tmp_path)
    raw = json.loads(native_v2(request))
    original = 0
    stored = 0
    for row in raw['records']:
        xml = base64.b64decode(row['xml'])
        original += len(xml)
        encoded, digest, encoding = static._encode_xml(xml, compact=True)
        row['xml'] = encoded
        row['xml_sha256'] = digest
        row['xml_encoding'] = encoding
        stored += len(base64.b64decode(encoded))
    compact = _canonical(raw)
    result = static.validate_project_static(compact, request)
    assert result['complete']
    assert stored < original


def test_environment_static_evidence_rejects_truncated_compressed_xml(tmp_path):
    request, _ = project(tmp_path)
    raw = json.loads(native_v2(request))
    row = raw['records'][0]
    xml = base64.b64decode(row['xml'])
    encoded, digest, encoding = static._encode_xml(xml, compact=True)
    compressed = base64.b64decode(encoded)
    row['xml'] = base64.b64encode(compressed[:-1]).decode()
    row['xml_sha256'] = digest
    row['xml_encoding'] = encoding
    with pytest.raises(ValueError, match='worker_project_static_xml_digest'):
        static.validate_project_static(_canonical(raw), request)



def test_static_stage_validates_compiler_evidence_once_before_internal_reuse(tmp_path, monkeypatch):
    """Large compiler receipts are validated once, then reused only in-process."""
    from nico import assessment_cpp_project_compiler as compiler
    root, targets, database, snapshot, compiler_raw = stage_inputs(tmp_path)
    docker = EnvironmentDocker(targets)
    calls = []
    original = compiler.validate_project_compiler

    def counted(raw, request):
        calls.append((hashlib.sha256(raw).hexdigest(), hashlib.sha256(compiler._canonical(request)).hexdigest()))
        return original(raw, request)

    monkeypatch.setattr(compiler, 'validate_project_compiler', counted)
    monkeypatch.setattr(static, 'validate_project_compiler', counted)
    result = static.run_project_static_stage(root, targets, 'sha256:'+'a'*64,
        database, snapshot, compiler_raw, compiler_environment=True,
        command=docker, retain_artifact=lambda key, raw: {
            'path': 'artifacts/'+key+'-'+hashlib.sha256(raw).hexdigest()+'.json',
            'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)})
    assert result['complete'], result['error']
    assert len(calls) == 1


def test_validated_compiler_state_cannot_be_reused_for_copied_bytes_or_request(tmp_path):
    from nico import assessment_cpp_project_compiler as compiler
    database, targets, snapshot, compiler_raw, _, _, _ = prepared(tmp_path)
    request = compiler.project_compiler_request(database, targets, snapshot)
    state = compiler.validated_project_compiler_state(compiler_raw, request)
    proof, records = compiler.reuse_validated_project_compiler(state, compiler_raw, request)
    assert proof['complete'] and len(records) == len(request['contexts'])
    with pytest.raises(ValueError, match='worker_project_compiler_state_mismatch'):
        compiler.reuse_validated_project_compiler(state, bytes(bytearray(compiler_raw)), request)
    with pytest.raises(ValueError, match='worker_project_compiler_state_mismatch'):
        compiler.reuse_validated_project_compiler(state, compiler_raw, deepcopy(request))
