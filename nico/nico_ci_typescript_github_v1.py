"""Read-only, NICO-only GitHub authority for retained TypeScript evidence.

Public entry point creates the existing App-aware client. Private client injection
is only a controller/test seam, never an API accepting target-provided metadata.
No workflow dispatch, archive download, new credential configuration, or score activation.
"""
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import re
import time

from nico.nico_ci_typescript_evidence_v1 import (
    AuthenticatedRun, MAX_BYTES, REPOSITORY, WORKFLOW, import_nico_ci_evidence,
)

API=f'https://api.github.com/repos/{REPOSITORY}'
TRUSTED_FILES=(WORKFLOW,'scripts/run_phase9_node_scanners.py','scripts/nico_ci_typescript_check.cjs',
               'nico/nico_ci_typescript_evidence_v1.py')
ROOT=Path(__file__).resolve().parents[1]


def _require(condition,reason):
    if not condition: raise ValueError(reason)


def _time(value):
    _require(isinstance(value,str),'provider_timestamp_missing')
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    _require(result.tzinfo is not None,'provider_timestamp_unzoned')
    return result


def _sha(raw): return hashlib.sha256(raw).hexdigest()


def _new_client():
    from nico.hosted_metadata_auth import MetadataAuthGitHubAssessmentClient
    return MetadataAuthGitHubAssessmentClient()


def import_current_nico_ci_evidence(archive: bytes, *, target_sha: str, run_id: str,
                                    run_attempt: str, artifact_id: str):
    """Authenticate provider observations afresh; never accept an AuthenticatedRun JSON.

    Call only from the authorized controller. Existing credential availability and
    Actions/Contents read access are prerequisites; this function grants neither.
    The supplied archive is untrusted until its independently fetched digest binds.
    """
    try:
        client=_new_client()
    except Exception:
        return _incomplete(archive,'github_client_unavailable')
    return _import_with_client(client,archive,target_sha=target_sha,run_id=run_id,
                               run_attempt=run_attempt,artifact_id=artifact_id,
                               now=datetime.now(timezone.utc))


def _incomplete(archive,reason):
    return {'scanner':'typescript','status':'incomplete','clean':False,'reason':reason,
            'retained_archive_sha256':_sha(archive),'production_scanner_integrated':False,'score_override':False}


def _import_with_client(client,archive,*,target_sha,run_id,run_attempt,artifact_id,now):
    try:
        return _collect_and_import(client,archive,target_sha,run_id,run_attempt,artifact_id,now)
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError,OSError) as error:
        # Provider error text may contain request headers, URLs or secret material.
        # Concrete policy failures are raised with controlled codes below.
        reason=str(error) if isinstance(error,ValueError) and re.fullmatch('[a-z_]+',str(error)) else 'provider_evidence_invalid'
        return _incomplete(archive,reason)


def _collect_and_import(client,archive,target_sha,run_id,run_attempt,artifact_id,now):
    _require(len(archive)<=3*MAX_BYTES,'archive_budget_exceeded')
    _require(isinstance(target_sha,str) and re.fullmatch('[a-f0-9]{40}',target_sha),'target_sha_invalid')
    _require(all(isinstance(v,str) and re.fullmatch('[1-9][0-9]*',v) for v in (run_id,run_attempt,artifact_id)),'provider_identifier_invalid')
    _require(getattr(client,'auth_mode',None) in {'github_app_installation','server_token'}
             and bool(getattr(client,'headers',{}).get('Authorization')),'authenticated_github_client_required')
    deadline=time.monotonic()+600; calls=0
    def get(path,params=None):
        nonlocal calls
        calls+=1
        _require(calls<=1500 and time.monotonic()<deadline,'provider_capture_budget')
        value,error=client.get_json(API+path,params)
        _require(time.monotonic()<deadline,'provider_capture_budget')
        _require(not error,'github_read_unavailable')
        _require(isinstance(value,dict),'provider_object_missing')
        return value
    def main_head():
        return get('/git/ref/heads/main').get('object',{}).get('sha')
    repo=get(''); repo_id=repo.get('id')
    _require(repo.get('full_name')==REPOSITORY and type(repo_id) is int and repo_id>0,'repository_identity_mismatch')
    _require(main_head()==target_sha,'main_sha_not_current')
    run_path=f'/actions/runs/{run_id}'
    run=get(run_path)
    def validate_run(value):
        _require(value.get('id')==int(run_id) and value.get('run_attempt')==int(run_attempt),'run_attempt_mismatch')
        _require(value.get('head_sha')==target_sha and value.get('head_branch')=='main','run_source_mismatch')
        _require(value.get('event') in {'push','workflow_dispatch'} and value.get('status')=='completed'
                 and value.get('conclusion') in {'success','failure'},'run_not_terminal')
        _require(value.get('path') in {WORKFLOW,WORKFLOW+'@main',WORKFLOW+'@refs/heads/main'},'run_workflow_path_mismatch')
        for name in ('repository','head_repository'):
            _require(value.get(name,{}).get('id')==repo_id and value.get(name,{}).get('full_name')==REPOSITORY,'run_repository_mismatch')
    validate_run(run)
    started=_time(run.get('run_started_at')); updated=_time(run.get('updated_at'))
    _require(started<=updated<=now and now-updated<=timedelta(days=7),'run_stale_or_future')
    attempt=get(run_path+f'/attempts/{run_attempt}'); validate_run(attempt)
    identity=('id','run_attempt','head_sha','head_branch','event','status','conclusion','workflow_id','path','run_started_at','updated_at')
    _require(all(attempt.get(k)==run.get(k) for k in identity),'attempt_snapshot_mismatch')
    workflow_id=run.get('workflow_id')
    _require(type(workflow_id) is int and workflow_id>0,'workflow_identifier_missing')
    workflow=get(f'/actions/workflows/{workflow_id}')
    _require(workflow.get('id')==workflow_id and workflow.get('path')==WORKFLOW and workflow.get('state')=='active','workflow_identity_mismatch')
    def latest_run():
        values=get(f'/actions/workflows/{workflow_id}/runs',{'branch':'main','head_sha':target_sha,'per_page':1}).get('workflow_runs')
        _require(isinstance(values,list) and len(values)==1,'latest_run_missing')
        _require(values[0].get('id')==int(run_id) and values[0].get('run_attempt')==int(run_attempt),'run_superseded')
    latest_run()
    jobs=get(run_path+f'/attempts/{run_attempt}/jobs',{'per_page':100})
    rows=jobs.get('jobs')
    _require(isinstance(rows,list) and jobs.get('total_count')==len(rows) and len(rows)<=100,'jobs_capture_incomplete')
    selected=[j for j in rows if j.get('name')=='Frontend validation']
    _require(len(selected)==1,'frontend_job_ambiguous')
    job=selected[0]
    _require(job.get('run_id')==int(run_id) and job.get('run_attempt',int(run_attempt))==int(run_attempt)
             and job.get('head_sha')==target_sha and job.get('status')=='completed','job_identity_mismatch')
    def outcome(name):
        steps=[s for s in job.get('steps',[]) if s.get('name')==name]
        _require(len(steps)==1 and steps[0].get('status')=='completed'
                 and steps[0].get('conclusion') in {'success','failure'},'step_capture_incomplete')
        return steps[0]['conclusion']
    _require(outcome('Checkout repo')=='success' and outcome('Upload exact-run TypeScript evidence')=='success','checkout_or_upload_failed')
    build=outcome('Build frontend'); check=outcome('Retain post-build TypeScript evidence')
    artifact_path=f'/actions/artifacts/{artifact_id}'
    artifact=get(artifact_path); arun=artifact.get('workflow_run',{})
    expected=f'nico-typescript-{target_sha}-{run_id}-{run_attempt}'
    _require(artifact.get('id')==int(artifact_id) and artifact.get('name')==expected
             and artifact.get('expired') is False and artifact.get('size_in_bytes')==len(archive),'artifact_identity_mismatch')
    _require(arun.get('id')==int(run_id) and arun.get('repository_id')==repo_id and arun.get('head_repository_id')==repo_id
             and arun.get('head_sha')==target_sha and arun.get('head_branch')=='main','artifact_run_mismatch')
    _require(started<=_time(artifact.get('created_at'))<=updated,'artifact_attempt_time_mismatch')
    _require(artifact.get('digest')=='sha256:'+_sha(archive),'artifact_digest_mismatch')
    commit=get('/git/commits/'+target_sha)
    _require(commit.get('sha')==target_sha,'commit_identity_mismatch')
    tree_sha=commit.get('tree',{}).get('sha')
    _require(isinstance(tree_sha,str) and re.fullmatch('[a-f0-9]{40}',tree_sha),'commit_tree_missing')
    tree=get('/git/trees/'+tree_sha,{'recursive':'1'})
    _require(tree.get('sha')==tree_sha and tree.get('truncated') is False and isinstance(tree.get('tree'),list),'tree_capture_incomplete')
    source={}; size=0; blob_cache={}
    for entry in tree['tree']:
        path=entry.get('path','')
        if not (path.startswith('apps/web/') or path in TRUSTED_FILES): continue
        if entry.get('type')=='tree': continue
        _require(entry.get('type')=='blob' and entry.get('mode') in {'100644','100755'}
                 and path not in source and not any(p in {'','.','..'} for p in path.split('/')),'source_boundary_invalid')
        length=entry.get('size'); blob_sha=entry.get('sha')
        _require(type(length) is int and 0<=length<=MAX_BYTES and isinstance(blob_sha,str)
                 and re.fullmatch('[a-f0-9]{40}',blob_sha),'source_blob_identity_invalid')
        size+=length
        _require(size<=128*1024*1024 and len(source)<10000,'source_inventory_budget')
        if blob_sha not in blob_cache:
            blob=get('/git/blobs/'+blob_sha)
            _require(blob.get('sha')==blob_sha and blob.get('encoding')=='base64' and blob.get('size')==length,'blob_metadata_mismatch')
            encoded=blob.get('content','')
            _require(isinstance(encoded,str) and len(encoded)<=2*MAX_BYTES,'blob_capture_budget')
            raw=base64.b64decode(''.join(encoded.split()),validate=True)
            _require(len(raw)==length and hashlib.sha1(b'blob '+str(length).encode()+b'\0'+raw).hexdigest()==blob_sha,'blob_content_mismatch')
            blob_cache[blob_sha]=raw
        raw=blob_cache[blob_sha]; source[path]=_sha(raw)
    for path in TRUSTED_FILES:
        _require(source.get(path)==_sha((ROOT/path).read_bytes()),'workflow_or_exporter_not_reviewed')
    # Bracket the multi-request capture: reject newer attempts, main moves or artifact changes.
    _require(main_head()==target_sha,'main_changed_during_capture')
    fresh=get(run_path); validate_run(fresh)
    _require(all(fresh.get(k)==run.get(k) for k in identity),'run_changed_during_capture')
    latest_run()
    _require(get(artifact_path)==artifact,'artifact_changed_during_capture')
    authenticated=AuthenticatedRun(repository=REPOSITORY,source_sha=target_sha,workflow_sha=target_sha,
        workflow_ref=f'{REPOSITORY}/{WORKFLOW}@refs/heads/main',run_id=run_id,run_attempt=run_attempt,
        event=run['event'],head_branch='main',run_status='completed',build_outcome=build,check_outcome=check,
        artifact_name=expected,artifact_run_id=run_id,artifact_digest=artifact['digest'],artifact_expired=False,
        source_inventory=source)
    result=import_nico_ci_evidence(archive,authenticated=authenticated,target_sha=target_sha)
    result.update(build_outcome=build,check_outcome=check,artifact_id=artifact_id,workflow_id=workflow_id,
                  metadata_authenticated=True,observed_at=now.isoformat())
    return result
