"""Installed v9 capture/transport paths with a substituted Docker boundary.

Owned native bytes are adapted explicitly to /work. The compiler operation is
deliberately failed: no mocked success or production execution credit is given.
"""
import base64
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from nico.assessment_cpp_baseline_evidence import retained_baseline_bytes, validate_retained_baseline
from nico.assessment_cpp_configuration_probe import probe_project_configuration, READ_PROGRAM
from nico.assessment_cpp_configure_first_execution import summarize_probe
from nico.assessment_cpp_fileapi_membership import CAPTURE_PROGRAM as FILEAPI_CAPTURE
from nico.assessment_cpp_native_commands import CAPTURE_PROGRAM as NATIVE_CAPTURE
from nico.assessment_cpp_project_compiler import PROGRAM as COMPILER_PROGRAM
from nico.assessment_cpp_project_snapshot import PROJECT_SNAPSHOT_PROGRAM, capture_project_snapshot
from nico.assessment_worker_receipts import canonical_bytes
from scripts.qualify_cpp_project_configuration import persist_project_artifact
from tests.test_cpp_baseline_execution import contract
from tests.test_cpp_configure_first_execution import ref
from tests.test_cpp_fileapi_transport_integration import FileAPIDocker
from tests.test_cpp_native_command_plan import owned, pack


def adapted(client, cache):
    data, native_raw, fileapi_raw, database = owned()
    kwargs = data['membership_kwargs']
    def rebase(raw):
        return raw.decode().replace(kwargs['source_root'],'/work/source').replace(kwargs['build_root'],'/work/build').replace(
            kwargs['compiler_paths']['C'],'/usr/local/bin/gcc').replace(kwargs['cmake_path'],'/opt/cmake-wheel/cmake/data/bin/cmake').encode()
    database = rebase(database)
    fileapi = json.loads(fileapi_raw)
    for name, row in fileapi['files'].items():
        model = json.loads(rebase(base64.b64decode(row['data'])))
        if name.startswith('index-'):
            model['reply'] = {client:model['reply'][fileapi['client']]}
        fileapi['files'][name] = pack(canonical_bytes(model))
    fileapi.update(source_root='/work/source',build_root='/work/build',client=client,
        cache_sha256=cache,database_sha256=hashlib.sha256(database).hexdigest())
    fileapi_raw = canonical_bytes(fileapi)
    native = json.loads(native_raw)
    native.update(source_root='/work/source',build_root='/work/build',cache_sha256=cache,
        database_sha256=hashlib.sha256(database).hexdigest(),fileapi_capture_sha256=hashlib.sha256(fileapi_raw).hexdigest())
    native['files'] = {name:pack(rebase(base64.b64decode(row['data']))) for name,row in native['files'].items()}
    return fileapi_raw, canonical_bytes(native), database, data['targets']


class NativeCommandDocker(FileAPIDocker):
    def __init__(self, targets, tmp_path, fault=None):
        super().__init__(targets)
        self.tmp_path, self.fault = tmp_path, fault
        self.fileapi_raw = self.native_raw = None
        self.native_reads = self.fileapi_reads = 0
        self.compiler_request = None
        self.database = adapted('client-nico-placeholder',None)[2]

    def __call__(self, args, **kwargs):
        raw, code = None, 0
        if FILEAPI_CAPTURE in args:
            request = json.loads(kwargs['input_bytes'])
            self.fileapi_raw,self.native_raw,database,targets = adapted(request['client'],request['cache_sha256'])
            assert database == self.database and targets == self.targets
            raw = self.fileapi_raw
            self.fileapi_reads += 1
            if self.fileapi_reads == 2 and self.fault == 'stale_fileapi':
                raw += b' '
        elif NATIVE_CAPTURE in args:
            raw = self.native_raw
            self.native_reads += 1
            if self.native_reads == 1 and self.fault == 'malformed_native':
                raw = b'{}'
            if self.native_reads == 2 and self.fault == 'stale_native':
                raw += b' '
        elif READ_PROGRAM in args and '/work/build/compile_commands.json' in args:
            raw = canonical_bytes({'data':base64.b64encode(self.database).decode(),'truncated':False})
        elif PROJECT_SNAPSHOT_PROGRAM in args:
            request = json.loads(kwargs['input_bytes'])
            build, private = self.tmp_path/'generated-build',self.tmp_path/'private'
            (build/'generated').mkdir(parents=True)
            (build/'generated/config.h').write_bytes(b'#define CONFIG_SENTINEL 23\n')
            private.mkdir(mode=0o700)
            captured = capture_project_snapshot(build,private/'generated-baseline',request)
            raw = canonical_bytes(captured)
        elif COMPILER_PROGRAM in args:
            self.compiler_request = json.loads(kwargs['input_bytes'])
            raw,code = b'owned controlled compiler execution unavailable',1
        if raw is None:
            return super().__call__(args,**kwargs)
        self.calls.append((args,kwargs))
        return {'exit_code':code,'timed_out':False,'output_truncated':False,'output':raw}


def run_case(tmp_path, fault=None):
    source,out=tmp_path/'source',tmp_path/'out'
    source.mkdir();out.mkdir()
    targets=owned()[0]['targets']
    original=Path(__file__).parent/'fixtures/cpp/fileapi-export-off-owned-control/source'
    for name in targets:
        path=source/name;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes((original/name).read_bytes())
    docker=NativeCommandDocker(targets,tmp_path,fault)
    baseline=contract();baseline.pop('compilation_database_sha256')
    baseline.update(schema='nico.cpp-baseline-execution.v2',freeze_compilation_database='after_configuration_before_build')
    probe=probe_project_configuration(source,targets,'sha256:'+'a'*64,project_options={'BUILD_TESTS':'ON'},
        baseline_execution=baseline,command=docker,capture_enabled_targets=True,capture_native_commands=True,
        capture_generated_context=True,project_compiler_evidence=True,
        retain_artifact=lambda key,raw:persist_project_artifact(out,key,raw))
    return probe,targets,docker,out,{'schema':'nico.cpp-configure-first-contract.v6','baseline_execution':baseline}


def test_complete_plan_reaches_private_compiler_without_replacing_original_database(tmp_path):
    probe,targets,docker,out,config=run_case(tmp_path)
    assert probe['schema']=='nico.cpp-project-configuration-probe.v9'
    assert probe['configured_invocations']==1 and probe['analysis_invocations']==2
    assert base64.b64decode(probe['compilation_database'])==docker.database
    assert probe['compilation_database_sha256']!=probe['analysis_compilation_database_sha256']
    request=docker.compiler_request
    assert request is not None
    assert {x['file'] for x in request['contexts']}=={'/work/source/main.c','/work/source/hidden.c'}
    assert len(request['contexts'])==2 and request['database_sha256']==probe['analysis_compilation_database_sha256']
    assert probe['status']=='UNPROVEN' and probe['error']=='worker_configuration_probe_compiler_failed'
    assert probe['generated_context_verified'] is True and probe['cleanup_verified'] is True
    artifacts={row['id']:ref(row['id'],(out/row['output_artifact']['path']).read_bytes())
        for row in probe['operations'] if row.get('output_artifact')}
    summary=summarize_probe(probe,targets,artifacts)
    summary['project_options']=probe['project_options']
    assert summary['schema']=='nico.cpp-configure-first-native.v5'
    assert summary['context_argv_binding_verified'] is True and summary['complete_execution'] is False
    raw=retained_baseline_bytes(probe,targets,config,'sha256:'+'a'*64)
    assert json.loads(raw)['schema']=='nico.cpp-baseline-evidence.v3'
    result=validate_retained_baseline(raw,targets,config,'sha256:'+'a'*64,summary,
        membership_raw=docker.fileapi_raw,native_raw=docker.native_raw,native_post_raw=docker.native_raw)
    assert result['collection_complete'] is True  # Only baseline collection.
    for fault in ('native_digest','analysis_digest','input_digest','missing_post','post_digest','wrong_capture_argv'):
        value=json.loads(raw);native=deepcopy(summary)
        rows={x['id']:x for x in value['probe']['operations']}
        if fault=='native_digest':native['native_command_capture_sha256']='0'*64
        elif fault=='analysis_digest':value['probe']['analysis_compilation_database_sha256']='0'*64
        elif fault=='input_digest':rows['project-native-commands']['input_sha256']='0'*64
        elif fault=='missing_post':value['probe']['operations'].remove(rows['project-native-commands-post-build'])
        elif fault=='post_digest':rows['project-native-commands-post-build']['output_sha256']='0'*64
        else:rows['project-native-commands']['invocation'].append('--trust-summary')
        with pytest.raises(ValueError):
            validate_retained_baseline(canonical_bytes(value),targets,config,'sha256:'+'a'*64,native,
                membership_raw=docker.fileapi_raw,native_raw=docker.native_raw,native_post_raw=docker.native_raw)


@pytest.mark.parametrize('fault',['malformed_native','stale_native','stale_fileapi'])
def test_missing_malformed_or_changed_native_inputs_stop_dependent_execution(tmp_path,fault):
    probe,_,docker,out,_=run_case(tmp_path,fault)
    assert probe['status']=='UNPROVEN' and probe['cleanup_verified'] is True
    assert docker.compiler_request is None
    assert probe['native_command_capture'] is not None
    raw=(out/probe['native_command_capture']['path']).read_bytes()
    if fault=='malformed_native':
        assert raw==b'{}' and probe['native_command_plan'] is None
        assert probe['compiled'] is False
    else:
        assert probe['error']=='worker_configuration_probe_frozen_native_plan_mismatch'
        assert probe['compiled'] is True and probe['tests_executed'] is False
