"""NICO-only post-build evidence export/import; no scanner activation or score changes."""
from __future__ import annotations
from dataclasses import dataclass
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import selectors
import signal
import subprocess
import time
import zipfile

SCHEMA='nico.ci-typescript.v1'
REPOSITORY='BoneManTGRM/NICO'
WORKFLOW='.github/workflows/node.js.yml'
MEMBERS={'typescript.log','typescript.json','manifest.json'}
MAX_BYTES=8*1024*1024


def _hash(raw): return hashlib.sha256(raw).hexdigest()
def _json(raw): return json.loads(raw,object_pairs_hook=_unique)
def _unique(pairs):
    value={}
    for key,item in pairs:
        if key in value: raise ValueError('duplicate_json_key')
        value[key]=item
    return value


def _git(root,*args):
    return subprocess.check_output(['git',*args],cwd=root,timeout=10).decode().strip()


def _source_inventory(root):
    names=subprocess.check_output(['git','ls-files','-z','--','apps/web',WORKFLOW,'scripts/run_phase9_node_scanners.py','scripts/nico_ci_typescript_check.cjs','nico/nico_ci_typescript_evidence_v1.py'],cwd=root,timeout=10).decode().split('\0')
    if len(names)>10000: raise ValueError('source_inventory_budget')
    result={}; total=0
    for name in filter(None,names):
        file=root/name
        if file.is_symlink() or not file.is_file() or file.resolve()!=file: raise ValueError('source_input_boundary')
        if total+file.stat().st_size>128*1024*1024: raise ValueError('source_inventory_bytes')
        raw=file.read_bytes(); total+=len(raw)
        if total>128*1024*1024: raise ValueError('source_inventory_bytes')
        result[name]=_hash(raw)
    return result


def _capture(command,root,out,*,timeout=120,max_bytes=MAX_BYTES):
    """Own CI command only; bounded pipes retain prefixes without unbounded files."""
    buffers=[bytearray(),bytearray()]; limits=[max_bytes,min(max_bytes,32768)]
    timed_out=False; truncated=False
    proc=subprocess.Popen(command,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True,
                          env={'PATH':os.environ.get('PATH',''),'NODE_OPTIONS':'','NODE_PATH':'','LANG':'C.UTF-8'})
    end=time.monotonic()+timeout
    try:
        with selectors.DefaultSelector() as selector:
            for i,stream in enumerate((proc.stdout,proc.stderr)):
                os.set_blocking(stream.fileno(),False); selector.register(stream,selectors.EVENT_READ,i)
            while selector.get_map() or proc.poll() is None:
                remaining=end-time.monotonic()
                if remaining<=0: timed_out=True; break
                for key,_ in selector.select(min(remaining,.05)):
                    i=key.data; available=limits[i]-len(buffers[i])
                    chunk=os.read(key.fileobj.fileno(),min(65536,available+1))
                    if not chunk: selector.unregister(key.fileobj); continue
                    buffers[i].extend(chunk[:available])
                    if len(chunk)>available: truncated=True; break
                if truncated: break
    finally:
        # Also terminate children retaining inherited pipes after their parent exits.
        if timed_out or truncated or proc.poll() is None:
            try: os.killpg(proc.pid,signal.SIGKILL)
            except ProcessLookupError: pass
        proc.wait(timeout=5)
        proc.stdout.close(); proc.stderr.close()
    return proc.returncode,bytes(buffers[0]),bytes(buffers[1]),timed_out,truncated


def export_post_build(root: Path,out: Path,*,env=None,runner=_capture):
    env=dict(os.environ if env is None else env); root=root.resolve(); out=out.resolve(); out.mkdir(parents=True,exist_ok=True)
    record={'schema':SCHEMA,'status':'incomplete','clean':False,'capture_complete':False}
    raw=b''
    try:
        if env.get('GITHUB_REPOSITORY')!=REPOSITORY: raise ValueError('nico_ci_only')
        if env.get('NICO_BUILD_OUTCOME') not in {'success','failure'}: raise ValueError('build_not_attempted')
        sha=_git(root,'rev-parse','HEAD')
        if sha!=env.get('GITHUB_SHA') or not re.fullmatch('[a-f0-9]{40}',sha): raise ValueError('source_sha_mismatch')
        if _git(root,'status','--porcelain','--untracked-files=no'): raise ValueError('tracked_source_modified')
        before=_source_inventory(root)
        record.update(source_sha=sha,source_inventory=before,repository=REPOSITORY,
                      run_id=env.get('GITHUB_RUN_ID'),run_attempt=env.get('GITHUB_RUN_ATTEMPT'),
                      workflow_ref=env.get('GITHUB_WORKFLOW_REF'),workflow_sha=env.get('GITHUB_WORKFLOW_SHA'),
                      event=env.get('GITHUB_EVENT_NAME'),build_outcome=env.get('NICO_BUILD_OUTCOME'))
        code,raw,stderr,timed_out,truncated=runner(['node','--max-old-space-size=2048',str(root/'scripts/nico_ci_typescript_check.cjs')],root,out)
        record.update(raw_exit_code=code,capture_timed_out=timed_out,capture_truncated=truncated,
                      native_stderr_base64=base64.b64encode(stderr).decode('ascii'),native_stderr_sha256=_hash(stderr))
        if timed_out or truncated or stderr: raise ValueError('capture_incomplete')
        result=_json(raw)
        if not isinstance(result,dict) or result.get('schema')!=SCHEMA: raise ValueError('native_result_schema')
        record.update(result,raw_exit_code=code)
        if (code not in {0,1} or record.get('status')!='completed' or record.get('capture_complete') is not True
                or (code==0)!=record.get('clean')):
            raise ValueError(record.get('reason') or 'native_result_incomplete')
        if _source_inventory(root)!=before or _git(root,'rev-parse','HEAD')!=sha or _git(root,'status','--porcelain','--untracked-files=no'):
            raise ValueError('source_changed_during_check')
    except (ValueError,KeyError,TypeError,OSError,subprocess.SubprocessError) as exc:
        record.update(status='incomplete',clean=False,capture_complete=False,reason=str(exc))
    (out/'typescript.log').write_bytes(raw)
    record['native_stdout_sha256']=_hash(raw)
    record_bytes=json.dumps(record,sort_keys=True,indent=2).encode()
    (out/'typescript.json').write_bytes(record_bytes)
    manifest={'schema':SCHEMA,'files':{'typescript.log':_hash(raw),'typescript.json':_hash(record_bytes)}}
    (out/'manifest.json').write_text(json.dumps(manifest,sort_keys=True,indent=2))
    return record


@dataclass(frozen=True)
class AuthenticatedRun:
    """Controller-only authenticated API observations, NEVER parsed from artifact data.

    The GitHub adapter fetches run/jobs/workflow-at-ref/artifact metadata through
    GitHub authorization. Merely constructing this object is not authentication.
    """
    repository: str
    source_sha: str
    workflow_sha: str
    workflow_ref: str
    run_id: str
    run_attempt: str
    event: str
    head_branch: str
    run_status: str
    build_outcome: str
    check_outcome: str
    artifact_name: str
    artifact_run_id: str
    artifact_digest: str
    artifact_expired: bool
    source_inventory: dict[str,str]


def import_nico_ci_evidence(archive: bytes, *, authenticated: AuthenticatedRun, target_sha: str):
    a=authenticated
    expected_name=f'nico-typescript-{target_sha}-{a.run_id}-{a.run_attempt}'
    if (a.repository!=REPOSITORY or not re.fullmatch('[a-f0-9]{40}',target_sha)
            or a.source_sha!=target_sha or a.workflow_sha!=target_sha
            or a.workflow_ref!=f'{REPOSITORY}/{WORKFLOW}@refs/heads/main'
            or a.head_branch!='main' or a.event not in {'push','workflow_dispatch'} or a.run_status!='completed'
            or a.build_outcome not in {'success','failure'} or a.check_outcome not in {'success','failure'}
            or a.artifact_name!=expected_name or a.artifact_run_id!=a.run_id or a.artifact_expired is not False
            or not re.fullmatch('[1-9][0-9]*',a.run_id) or not re.fullmatch('[1-9][0-9]*',a.run_attempt)
            or not a.source_inventory):
        raise ValueError('authenticated_run_binding_invalid')
    required_sources={WORKFLOW,'scripts/run_phase9_node_scanners.py','scripts/nico_ci_typescript_check.cjs',
                      'nico/nico_ci_typescript_evidence_v1.py','apps/web/tsconfig.json','apps/web/package-lock.json','apps/web/next-env.d.ts'}
    if not required_sources.issubset(a.source_inventory): raise ValueError('authenticated_source_inventory_incomplete')
    if len(archive)>3*MAX_BYTES or a.artifact_digest!='sha256:'+_hash(archive): raise ValueError('authenticated_artifact_digest_mismatch')
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            infos=zipped.infolist()
            if len(infos)!=3 or {i.filename for i in infos}!=MEMBERS: raise ValueError('artifact_member_set')
            contents={}
            for item in infos:
                mode=item.external_attr>>16
                if item.file_size>MAX_BYTES or item.flag_bits&1 or mode&0o170000==0o120000: raise ValueError('artifact_member_boundary')
                with zipped.open(item) as stream: raw=stream.read(MAX_BYTES+1)
                if len(raw)>MAX_BYTES or len(raw)!=item.file_size: raise ValueError('artifact_member_capture')
                contents[item.filename]=raw
    except (zipfile.BadZipFile,RuntimeError) as exc: raise ValueError('artifact_archive_invalid') from exc
    manifest=_json(contents['manifest.json']); record=_json(contents['typescript.json'])
    if manifest!={'schema':SCHEMA,'files':{p:_hash(contents[p]) for p in ('typescript.log','typescript.json')}}: raise ValueError('artifact_manifest_mismatch')
    if not isinstance(record,dict): raise ValueError('record_schema_invalid')
    for field in ('repository','source_sha','workflow_sha','workflow_ref','run_id','run_attempt','event','build_outcome'):
        if record.get(field)!=getattr(a,field): raise ValueError('record_'+field+'_mismatch')
    if record.get('source_inventory')!=a.source_inventory: raise ValueError('source_inventory_mismatch')
    if record.get('native_stdout_sha256')!=_hash(contents['typescript.log']): raise ValueError('native_stdout_digest_mismatch')
    if record.get('status')=='incomplete':
        if (record.get('schema')!=SCHEMA or record.get('clean') is not False
                or record.get('capture_complete') is not False or a.check_outcome!='failure'):
            raise ValueError('incomplete_outcome_conflict')
        # Authenticated failure evidence is retained, never promoted to checked/clean.
        return {'scanner':'typescript','status':'incomplete','clean':False,'source_sha':target_sha,
                'execution_source':'authenticated_nico_postbuild_ci','reason':'retained_check_incomplete',
                'retained_failure':{k:record[k] for k in ('reason','diagnostics','diagnostics_text','raw_exit_code',
                    'capture_timed_out','capture_truncated','native_stdout_sha256','native_stderr_base64','native_stderr_sha256') if k in record},
                'artifact_digest':a.artifact_digest,'run_id':a.run_id,'run_attempt':a.run_attempt,
                'production_scanner_integrated':False,'score_override':False}
    native=_json(contents['typescript.log'])
    native_fields={'schema','status','clean','diagnostics','diagnostics_text','compiler','lockfile_sha256',
                   'generated_inputs','configuration_sha256','raw_configuration','effective_configuration',
                   'configuration_limitations','program_inputs','read_inputs','root_inputs','capture_complete','emitted_files'}
    if not isinstance(native,dict) or set(native)!=native_fields: raise ValueError('native_schema_incomplete')
    if any(record.get(key)!=value for key,value in native.items()): raise ValueError('native_record_mismatch')
    if (record.get('capture_timed_out') is not False or record.get('capture_truncated') is not False
            or record.get('native_stderr_base64')!='' or record.get('native_stderr_sha256')!=_hash(b'')):
        raise ValueError('native_capture_incomplete')
    if (record.get('schema')!=SCHEMA or record.get('status')!='completed' or record.get('capture_complete') is not True
            or type(record.get('clean')) is not bool or record.get('native_stdout_sha256')!=_hash(contents['typescript.log'])
            or record.get('raw_exit_code')!=(0 if record['clean'] else 1)
            or a.check_outcome!=('success' if record['clean'] else 'failure')): raise ValueError('execution_incomplete_or_conflicting')
    options=record.get('effective_configuration',{})
    if options.get('noEmit') is not True or options.get('incremental') is not False or record.get('emitted_files')!=0: raise ValueError('emission_policy_mismatch')
    if record.get('compiler',{}).get('version')!='6.0.3': raise ValueError('compiler_pin_mismatch')
    if record.get('lockfile_sha256')!=a.source_inventory.get('apps/web/package-lock.json') or record.get('configuration_sha256')!=a.source_inventory.get('apps/web/tsconfig.json'):
        raise ValueError('configuration_identity_mismatch')
    generated=record.get('generated_inputs'); program=record.get('program_inputs'); reads=record.get('read_inputs')
    if not all(isinstance(rows,list) and rows for rows in (generated,program,reads)): raise ValueError('input_inventory_missing')
    def index(rows):
        result={}
        for row in rows:
            p=row.get('path',''); h=row.get('sha256','')
            if (not isinstance(p,str) or p.startswith('/') or '\\' in p or any(x in {'','..','.'} for x in p.split('/'))
                    or p in result or not re.fullmatch('[a-f0-9]{64}',h)): raise ValueError('input_inventory_invalid')
            result[p]=h
        return result
    gen=index(generated); prog=index(program); observed=index(reads)
    for name in ('routes.d.ts','root-params.d.ts'):
        if 'apps/web/.next/types/'+name not in gen or 'apps/web/.next/types/'+name not in prog: raise ValueError('required_generated_input_missing')
    if any(not p.startswith('apps/web/.next/types/') for p in gen): raise ValueError('generated_input_boundary')
    if any(observed.get(p)!=h for rows in (gen,prog) for p,h in rows.items()): raise ValueError('input_inventory_conflict')
    if any(p in a.source_inventory and a.source_inventory[p]!=h for p,h in observed.items()): raise ValueError('checked_source_mismatch')
    compiler=record['compiler']
    if (compiler.get('package_sha256')!=observed.get('@compiler/package.json')
            or compiler.get('entry_sha256')!=observed.get('@compiler/lib/typescript.js')
            or not re.fullmatch('[a-f0-9]{64}',compiler.get('node_sha256',''))
            or not re.fullmatch(r'v24\.\d+\.\d+',compiler.get('node_version',''))):
        raise ValueError('compiler_identity_incomplete')
    roots=record.get('root_inputs')
    if not isinstance(roots,list) or not roots or any(not isinstance(p,str) or p not in prog for p in roots): raise ValueError('root_inventory_incomplete')
    limits=record.get('configuration_limitations',{})
    if (limits.get('declaration_semantics_checked') is not (not bool(options.get('skipLibCheck')))
            or limits.get('javascript_semantics_checked') is not bool(options.get('checkJs'))
            or limits.get('strict_mode') is not bool(options.get('strict'))): raise ValueError('configuration_limitations_conflict')
    diagnostics=record.get('diagnostics')
    if not isinstance(diagnostics,list) or any(not isinstance(d,dict) or type(d.get('code')) is not int or d.get('category') not in {'Error','Warning','Suggestion','Message'} or not isinstance(d.get('message'),str) for d in diagnostics): raise ValueError('diagnostics_incomplete')
    if record['clean'] != (not any(d['category']=='Error' for d in diagnostics)): raise ValueError('diagnostics_outcome_conflict')
    return {'scanner':'typescript','status':'completed','clean':record['clean'],'source_sha':target_sha,
            'execution_source':'authenticated_nico_postbuild_ci','diagnostics':diagnostics,
            'configuration_limitations':record.get('configuration_limitations'), 'effective_configuration':options,
            'checked_project_scope':{'configuration':'apps/web/tsconfig.json',
                'root_file_count':len(record['root_inputs']), 'program_input_count':len(record['program_inputs']),
                'coverage':'Retained TypeScript project configuration only; not full-repository, runtime or ESLint coverage'},
            'artifact_digest':a.artifact_digest,'run_id':a.run_id,'run_attempt':a.run_attempt,
            'production_scanner_integrated':False,'score_override':False}
