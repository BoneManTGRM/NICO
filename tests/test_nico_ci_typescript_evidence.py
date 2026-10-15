"""Owned fixtures; no NICO build or dependency installation is run."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import zipfile

import pytest

ROOT=Path(__file__).resolve().parents[1]
NODE=shutil.which('node')


def sha(raw): return hashlib.sha256(raw).hexdigest()


@pytest.fixture
def project(tmp_path):
    web=tmp_path/'apps/web'; (web/'.next/types').mkdir(parents=True)
    (web/'package-lock.json').write_text(json.dumps({'lockfileVersion':3,'packages':{'node_modules/typescript':{'version':'6.0.3'}}}))
    (web/'tsconfig.json').write_text(json.dumps({'compilerOptions':{'target':'es2020','skipLibCheck':True,'strict':False,'allowJs':True,'noEmit':True,'incremental':True},'include':['**/*.ts','.next/types/**/*.ts']}))
    (web/'next-env.d.ts').write_text('import "./.next/types/routes.d.ts";\nimport "./.next/types/root-params.d.ts";')
    (web/'.next/types/routes.d.ts').write_text('export type Route="/";')
    (web/'.next/types/root-params.d.ts').write_text('export type Params={};')
    (web/'.next/types/validator.ts').write_text('export const generated: number=1;')
    (web/'app.ts').write_text('const n: number=1;')
    return tmp_path


def compiler_path():
    override=os.environ.get('NICO_TEST_TYPESCRIPT_ROOT')
    compiler=Path(override) if override else ROOT/'apps/web/node_modules/typescript'
    if not compiler.is_absolute(): pytest.fail('TypeScript fixture override must be absolute')
    return compiler


def collect(project):
    compiler=compiler_path()
    if not NODE or not (compiler/'lib/typescript.js').is_file() or not (compiler/'package.json').is_file():
        pytest.fail('Existing Node and TypeScript 6.0.3 fixture dependency required; tests never install or silently skip it')
    metadata=json.loads((compiler/'package.json').read_text())
    lock=json.loads((ROOT/'apps/web/package-lock.json').read_text())
    if metadata.get('name')!='typescript' or metadata.get('version')!='6.0.3' or lock['packages']['node_modules/typescript']['version']!='6.0.3':
        pytest.fail('TypeScript fixture dependency must match the reviewed 6.0.3 lock pin')
    harness='const x=require(process.argv[1]); process.stdout.write(JSON.stringify(x.collectProject(process.argv[2],process.argv[3])));'
    result=subprocess.run([NODE,'-e',harness,str(ROOT/'scripts/nico_ci_typescript_check.cjs'),str(project),str(compiler)],capture_output=True,text=True,timeout=20,
                          env={'PATH':'/nonexistent','NODE_OPTIONS':'','NODE_PATH':''})
    assert result.returncode==0,result.stderr
    return json.loads(result.stdout)


def test_semantic_check_preserves_actual_settings(project):
    result=collect(project)
    assert result['status']=='completed' and result['clean'] is True
    assert result['effective_configuration']['skipLibCheck'] is True
    assert result['effective_configuration']['strict'] is False
    assert result['effective_configuration']['allowJs'] is True
    assert result['effective_configuration'].get('checkJs',False) is False
    assert result['effective_configuration']['incremental'] is False
    assert result['effective_configuration']['noEmit'] is True
    assert len(result['generated_inputs'])==3
    assert any(row['path'].endswith('/validator.ts') for row in result['generated_inputs'])
    assert result['configuration_limitations']['declaration_semantics_checked'] is False
    assert result['configuration_limitations']['javascript_semantics_checked'] is False
    assert any(row['path']=='apps/web/app.ts' for row in result['program_inputs'])


def test_diagnostics_complete_is_not_clean(project):
    (project/'apps/web/app.ts').write_text('const n: number="wrong";')
    result=collect(project)
    assert result['status']=='completed' and result['clean'] is False
    assert any(row['code']==2322 for row in result['diagnostics'])
    assert result['diagnostics_text']


def test_missing_next_generated_input_fails_closed(project):
    (project/'apps/web/.next/types/routes.d.ts').unlink()
    result=collect(project)
    assert result['status']=='incomplete' and result['clean'] is False
    assert 'required_generated' in result['reason']


def test_compiler_pin_mismatch(project):
    (project/'apps/web/package-lock.json').write_text('{"packages":{"node_modules/typescript":{"version":"0.0.0"}}}')
    assert collect(project)['status']=='incomplete'


def test_source_not_executed_and_no_emit(project):
    (project/'apps/web/app.ts').write_text('throw new Error("owned fixture must not execute");')
    before={str(p):p.read_bytes() for p in project.rglob('*') if p.is_file()}
    result=collect(project)
    assert result['status']=='completed'
    assert before=={str(p):p.read_bytes() for p in project.rglob('*') if p.is_file()}


def test_generated_symlink_rejected(project,tmp_path):
    entry=project/'apps/web/.next/types/routes.d.ts'; entry.unlink()
    outside=tmp_path/'outside.d.ts'; outside.write_text('export {}'); entry.symlink_to(outside)
    assert collect(project)['status']=='incomplete'


def test_workflow_checks_after_build_and_always_retains():
    text=(ROOT/'.github/workflows/node.js.yml').read_text()
    assert text.index('run: npm run build') < text.index('--post-build-typescript')
    assert 'steps.build_frontend.outcome' in text
    assert 'name: nico-typescript-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in text
    assert text.count('if: always()')>=2
    assert text.count('- "scripts/nico_ci_typescript_check.cjs"')==2
    assert text.count('- "nico/nico_ci_typescript_evidence_v1.py"')==2


@pytest.fixture
def retained(project,tmp_path,monkeypatch):
    from nico import nico_ci_typescript_evidence_v1 as module
    native=collect(project)
    source={str(p.relative_to(project)):sha(p.read_bytes()) for p in (project/'apps/web').rglob('*') if p.is_file() and '.next' not in p.parts}
    source.update({p:sha((ROOT/p).read_bytes()) for p in (module.WORKFLOW,'scripts/run_phase9_node_scanners.py','scripts/nico_ci_typescript_check.cjs','nico/nico_ci_typescript_evidence_v1.py')})
    monkeypatch.setattr(module,'_git',lambda root,*args: 'b'*40 if args[0]=='rev-parse' else '')
    monkeypatch.setattr(module,'_source_inventory',lambda root:dict(source))
    env={'GITHUB_REPOSITORY':module.REPOSITORY,'GITHUB_SHA':'b'*40,'GITHUB_RUN_ID':'123','GITHUB_RUN_ATTEMPT':'2',
         'GITHUB_WORKFLOW_REF':f'{module.REPOSITORY}/{module.WORKFLOW}@refs/heads/main', 'GITHUB_WORKFLOW_SHA':'b'*40,
         'GITHUB_EVENT_NAME':'push','NICO_BUILD_OUTCOME':'success'}
    out=tmp_path/'evidence'
    def runner(command,root,dest):
        assert '--max-old-space-size=2048' in command
        return 0,json.dumps(native).encode(),b'',False,False
    record=module.export_post_build(project,out,env=env,runner=runner)
    assert record['status']=='completed',record
    contents={name:(out/name).read_bytes() for name in module.MEMBERS}
    archive=pack(contents)
    context=module.AuthenticatedRun(repository=module.REPOSITORY,source_sha='b'*40,workflow_sha='b'*40,
        workflow_ref=env['GITHUB_WORKFLOW_REF'],run_id='123',run_attempt='2',event='push',head_branch='main',run_status='completed',
        build_outcome='success',check_outcome='success',artifact_name='nico-typescript-'+'b'*40+'-123-2',artifact_run_id='123',
        artifact_digest='sha256:'+sha(archive),artifact_expired=False,source_inventory=source)
    return module,contents,archive,context


def pack(contents):
    output=io.BytesIO()
    with zipfile.ZipFile(output,'w') as z:
        for name,raw in contents.items(): z.writestr(name,raw)
    return output.getvalue()


def revise(retained, mutate):
    from dataclasses import replace
    module,contents,_,context=retained
    contents=dict(contents); record=json.loads(contents['typescript.json']); native=json.loads(contents['typescript.log'])
    mutate(record,native)
    contents['typescript.log']=json.dumps(native).encode(); record['native_stdout_sha256']=sha(contents['typescript.log'])
    contents['typescript.json']=json.dumps(record).encode()
    contents['manifest.json']=json.dumps({'schema':module.SCHEMA,'files':{p:sha(contents[p]) for p in ('typescript.log','typescript.json')}}).encode()
    archive=pack(contents)
    return archive,replace(context,artifact_digest='sha256:'+sha(archive))


def test_authenticated_exact_run_import(retained):
    module,_,archive,context=retained
    result=module.import_nico_ci_evidence(archive,authenticated=context,target_sha='b'*40)
    assert result['status']=='completed' and result['clean']
    assert result['production_scanner_integrated'] is False
    assert result['score_override'] is False
    assert result['configuration_limitations']['declaration_semantics_checked'] is False


@pytest.mark.parametrize('field,value',[('repository','other/repo'),('source_sha','c'*40),('workflow_sha','c'*40),
    ('workflow_ref','wrong'),('event','pull_request'),('head_branch','feature'),('run_attempt','3'),
    ('artifact_run_id','999'),('artifact_digest','sha256:'+'0'*64),('artifact_expired',True),('run_status','in_progress'),('build_outcome','skipped')])
def test_authenticated_metadata_mismatch_rejected(retained,field,value):
    from dataclasses import replace
    module,_,archive,context=retained
    with pytest.raises(ValueError): module.import_nico_ci_evidence(archive,authenticated=replace(context,**{field:value}),target_sha='b'*40)


@pytest.mark.parametrize('field,value',[('source_sha','c'*40),('run_attempt','1'),('status','incomplete'),('capture_complete',False),('raw_exit_code',2)])
def test_self_reported_success_cannot_override_independent_context(retained,field,value):
    module,_,_,_=retained
    archive,context=revise(retained,lambda record,native:record.update({field:value}))
    with pytest.raises(ValueError): module.import_nico_ci_evidence(archive,authenticated=context,target_sha='b'*40)


def test_completed_error_evidence_is_not_discarded(retained):
    from dataclasses import replace
    module,_,_,_=retained
    def mutate(record,native):
        error={'code':2322,'category':'Error','message':'Owned type error','file':'apps/web/app.ts','related':[]}
        for value in (record,native): value.update(clean=False,diagnostics=[error],diagnostics_text='Owned type error')
        record['raw_exit_code']=1
    archive,context=revise(retained,mutate)
    result=module.import_nico_ci_evidence(archive,authenticated=replace(context,check_outcome='failure'),target_sha='b'*40)
    assert result['status']=='completed' and result['clean'] is False
    assert result['diagnostics'][0]['code']==2322


@pytest.mark.parametrize('damage',['generated_missing','read_conflict','noEmit','incremental','config_hash','lock_hash','compiler_pin','compiler_hash','generated_not_checked','roots','limitations','diagnostics'])
def test_evidence_contract_damage_rejected(retained,damage):
    module,_,_,_=retained
    def mutate(record,native):
        for value in (record,native):
            if damage=='generated_missing': value['generated_inputs']=[]
            elif damage=='read_conflict': value['read_inputs'][0]['sha256']='0'*64
            elif damage in {'noEmit','incremental'}: value['effective_configuration'][damage]=damage=='incremental'
            elif damage=='config_hash': value['configuration_sha256']='0'*64
            elif damage=='lock_hash': value['lockfile_sha256']='0'*64
            elif damage=='compiler_pin': value['compiler']['version']='0.0.0'
            elif damage=='compiler_hash': value['compiler']['entry_sha256']='0'*64
            elif damage=='generated_not_checked': value['program_inputs']=[r for r in value['program_inputs'] if '.next/' not in r['path']]
            elif damage=='roots': value['root_inputs']=[]
            elif damage=='limitations': value['configuration_limitations']['declaration_semantics_checked']=True
            else: value['diagnostics']=[{'code':2322,'category':'Error','message':'retained error'}]
    archive,context=revise(retained,mutate)
    with pytest.raises(ValueError): module.import_nico_ci_evidence(archive,authenticated=context,target_sha='b'*40)


def test_archive_boundary_rejects_extra_or_duplicate_members(retained):
    from dataclasses import replace
    module,contents,_,context=retained
    archive=pack({**contents,'../outside':b'bad'})
    with pytest.raises(ValueError): module.import_nico_ci_evidence(archive,authenticated=replace(context,artifact_digest='sha256:'+sha(archive)),target_sha='b'*40)


@pytest.mark.parametrize('failure',['timeout','truncated','stderr','invalid_json'])
def test_exporter_retains_failure_manifest(project,tmp_path,monkeypatch,failure):
    from nico import nico_ci_typescript_evidence_v1 as module
    monkeypatch.setattr(module,'_git',lambda root,*args:'b'*40 if args[0]=='rev-parse' else '')
    monkeypatch.setattr(module,'_source_inventory',lambda root:{'owned':'a'*64})
    raw=b'owned retained partial output'
    result=module.export_post_build(project,tmp_path/'failed',env={'GITHUB_REPOSITORY':module.REPOSITORY,'GITHUB_SHA':'b'*40,'NICO_BUILD_OUTCOME':'success'},
        runner=lambda *args:(0,raw,b'error' if failure=='stderr' else b'',failure=='timeout',failure=='truncated'))
    assert result['status']=='incomplete' and not result['clean']
    assert (tmp_path/'failed/typescript.log').read_bytes()==raw
    assert (tmp_path/'failed/manifest.json').is_file()


def test_empty_native_log_rejected(retained):
    module,_,_,_=retained
    archive,context=revise(retained,lambda record,native:native.clear())
    with pytest.raises(ValueError): module.import_nico_ci_evidence(archive,authenticated=context,target_sha='b'*40)


def test_failure_stderr_retained_exactly(project,tmp_path,monkeypatch):
    import base64
    from nico import nico_ci_typescript_evidence_v1 as module
    monkeypatch.setattr(module,'_git',lambda root,*args:'b'*40 if args[0]=='rev-parse' else '')
    monkeypatch.setattr(module,'_source_inventory',lambda root:{'owned':'a'*64})
    stderr=b'owned failure\xff\n'
    result=module.export_post_build(project,tmp_path/'failed',env={'GITHUB_REPOSITORY':module.REPOSITORY,'GITHUB_SHA':'b'*40,'NICO_BUILD_OUTCOME':'success'},runner=lambda *args:(3,b'partial',stderr,False,False))
    assert base64.b64decode(result['native_stderr_base64'])==stderr
    assert result['native_stderr_sha256']==sha(stderr)
    assert result['raw_exit_code']==3 and result['capture_truncated'] is False


@pytest.mark.parametrize('channel',['stdout','stderr'])
def test_capture_hard_bounds_owned_output(tmp_path,channel):
    import sys
    from nico import nico_ci_typescript_evidence_v1 as module
    code,stdout,stderr,timed_out,truncated=module._capture([sys.executable,'-c',f'import sys; sys.{channel}.buffer.write(b"x"*1000000)'],tmp_path,tmp_path,timeout=2,max_bytes=1024)
    assert truncated and not timed_out
    assert len(stdout)<=1024 and len(stderr)<=1024
    assert not list(tmp_path.iterdir())


def test_capture_timeout_retains_owned_prefix(tmp_path):
    import sys
    from nico import nico_ci_typescript_evidence_v1 as module
    code,stdout,stderr,timed_out,truncated=module._capture([sys.executable,'-c','import time; print("owned",flush=True); time.sleep(10)'],tmp_path,tmp_path,timeout=.2)
    assert timed_out and not truncated and stdout==b'owned\n'


def test_independent_source_inventory_requires_workflow(retained):
    from dataclasses import replace
    module,_,archive,context=retained
    source=dict(context.source_inventory); source.pop(module.WORKFLOW)
    with pytest.raises(ValueError,match='authenticated_source_inventory_incomplete'):
        module.import_nico_ci_evidence(archive,authenticated=replace(context,source_inventory=source),target_sha='b'*40)


def test_compiler_defaults_to_actual_checkout(monkeypatch):
    monkeypatch.delenv('NICO_TEST_TYPESCRIPT_ROOT',raising=False)
    assert compiler_path()==ROOT/'apps/web/node_modules/typescript'


def test_missing_compiler_is_failure_not_skip(project,monkeypatch):
    monkeypatch.setitem(globals(),'COMPILER',project/'missing-compiler')
    monkeypatch.setenv('NICO_TEST_TYPESCRIPT_ROOT',str(project/'missing-compiler'))
    with pytest.raises(pytest.fail.Exception,match='TypeScript'):
        collect(project)


def test_relative_compiler_override_rejected(monkeypatch):
    monkeypatch.setenv('NICO_TEST_TYPESCRIPT_ROOT','relative/compiler')
    with pytest.raises(pytest.fail.Exception,match='absolute'):
        compiler_path()


def test_hosted_shards_provision_pinned_compiler():
    workflow=(ROOT/'.github/workflows/nico-ci.yml').read_text().split('  test_shards:',1)[1]
    assert 'node-version: "24"' in workflow
    assert 'npm ci --ignore-scripts --no-audit --no-fund' in workflow
    assert "require('./apps/web/node_modules/typescript').version" in workflow
