"""Submit a pre-authorized durable job to the dedicated protected-main workflow.

No public contract selection, operator credentials, broad App tokens or automatic
retry of an ambiguous submission are provided. Existing server-token permissions
are neither inferred nor expanded; GitHub must accept the fixed dispatch.
"""
from __future__ import annotations

import json
import multiprocessing
import os
from pathlib import Path
import re
import tempfile
import time

import requests

from nico.assessment_worker_auth import JOB_ID
from nico.assessment_worker_consumer import _unique_object
from nico.assessment_worker_jobs import JobIdentity, WorkerJobs
from nico.assessment_worker_launch import read_response


def authentication_mode():
    # Partial App configuration remains an App failure, not an implicit switch
    # to a more broadly privileged token. Never read operator or GITHUB_TOKEN.
    if any(os.getenv(key) for key in ('NICO_GITHUB_APP_ID', 'NICO_GITHUB_APP_PRIVATE_KEY',
                                      'NICO_GITHUB_APP_INSTALLATION_ID')):
        return 'github_app_installation'
    return 'server_token' if os.getenv('NICO_GITHUB_TOKEN') else 'unavailable'


def _dispatch_token(repository, repository_id, mode, session, headers, signer):
    from nico.github_app_auth import build_github_app_jwt
    response = None
    try:
        if mode == 'server_token':
            token = os.getenv('NICO_GITHUB_TOKEN', '')
            if not token or len(token) > 16384 or any(char.isspace() for char in token):
                return None
            response = session.get('https://api.github.com/repos/' + repository,
                headers={**headers, 'Authorization': 'Bearer ' + token},
                timeout=(2, 5), allow_redirects=False, stream=True)
            value = json.loads(read_response(response, limit=65536, deadline=time.monotonic() + 8),
                               object_pairs_hook=_unique_object)
            if (type(value.get('id')) is not int or value['id'] != int(repository_id)
                    or str(value.get('full_name', '')).lower() != repository.lower()):
                return None
            # Fixed destination/use does not downscope this existing token.
            # A subsequent Actions refusal stays a failure; no permissions change.
            return token
        if mode != 'github_app_installation':
            return None
        installation = os.getenv('NICO_GITHUB_APP_INSTALLATION_ID', '')
        if not re.fullmatch(r'[1-9][0-9]{0,19}', installation):
            return None
        token, _error = (signer or build_github_app_jwt)()
        if not token:
            return None
        # Explicitly reduce authority to one repository and only Actions write.
        # This cannot grant permissions not already held by the installation.
        response = session.post('https://api.github.com/app/installations/' + installation + '/access_tokens',
            headers={**headers, 'Authorization': 'Bearer ' + token},
            json={'repository_ids': [int(repository_id)], 'permissions': {'actions': 'write'}},
            timeout=(2, 5), allow_redirects=False, stream=True)
        if response.status_code != 201:
            return None
        raw = bytearray()
        deadline = time.monotonic() + 8
        for chunk in response.iter_content(chunk_size=65536):
            if len(raw) + len(chunk) > 65536 or time.monotonic() >= deadline:
                return None
            raw.extend(chunk)
        value = json.loads(raw, object_pairs_hook=_unique_object)
        installation_token = value.get('token')
        repositories = value.get('repositories')
        if (not isinstance(installation_token, str) or not installation_token or len(installation_token) > 16384
                or any(char.isspace() for char in installation_token)
                or value.get('permissions') not in ({'actions': 'write'}, {'actions': 'write', 'metadata': 'read'})
                or not isinstance(repositories, list) or len(repositories) != 1
                or repositories[0].get('id') != int(repository_id)
                or str(repositories[0].get('full_name', '')).lower() != repository.lower()):
            return None
        return installation_token
    finally:
        if response is not None:
            response.close()


def _submit(job_id, repository, repository_id, *, session=None, signer=None, mode=None):
    """No retry here: submission may have succeeded before its response was lost."""
    if (not JOB_ID.fullmatch(job_id)
            or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository)
            or not re.fullmatch(r'[1-9][0-9]{0,19}', repository_id)):
        return {'state': 'rejected', 'run_id': None}
    mode = authentication_mode() if mode is None else mode
    owned_session = session is None
    session = session or requests.Session()
    session.trust_env = False
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10'}
    dispatched = False
    response = None
    try:
        token = _dispatch_token(repository, repository_id, mode, session, headers, signer)
        if not token:
            return {'state': 'rejected', 'run_id': None}
        dispatched = True
        response = session.post('https://api.github.com/repos/' + repository + '/actions/workflows/assessment-worker.yml/dispatches',
            headers={**headers, 'Authorization': 'Bearer ' + token},
            json={'ref': 'main', 'inputs': {'job_id': job_id}},
            timeout=(2, 5), allow_redirects=False, stream=True)
        if response.status_code == 204:  # Older supported GitHub response, no run identity claim.
            return {'state': 'accepted', 'run_id': None}
        if response.status_code == 200:
            value = json.loads(read_response(response, limit=65536, deadline=time.monotonic() + 8),
                               object_pairs_hook=_unique_object)
            run_id = value.get('workflow_run_id')
            if type(run_id) is int and 1 <= run_id < 10**20:
                return {'state': 'accepted', 'run_id': run_id}
            return {'state': 'unknown', 'run_id': None}
        # Server errors can happen after enqueue; only explicit client refusals
        # establish that this submission was rejected.
        return {'state': 'rejected' if 400 <= response.status_code < 500 else 'unknown', 'run_id': None}
    except Exception:
        return {'state': 'unknown' if dispatched else 'rejected', 'run_id': None}
    finally:
        if response is not None:
            response.close()
        if owned_session:
            session.close()


def _submission_child(destination, job_id, repository, repository_id, mode):
    try:
        result = _submit(job_id, repository, repository_id, mode=mode)
        Path(destination).write_text(json.dumps(result))
    except Exception:
        pass  # The parent records unknown; no exception or token is logged.


def submit_once(job_id, repository, repository_id, *, deadline_epoch, mode):
    timeout = min(30, max(0, deadline_epoch - time.time()))
    if timeout <= 0:
        return {'state': 'rejected', 'run_id': None}
    with tempfile.TemporaryDirectory(prefix='nico-dispatch-') as temporary:
        destination = Path(temporary) / 'result.json'
        process = multiprocessing.get_context('spawn').Process(target=_submission_child,
            args=(destination, job_id, repository, repository_id, mode))
        try:
            process.start()
            process.join(timeout)
            if process.is_alive() or process.exitcode != 0 or not destination.is_file():
                return {'state': 'unknown', 'run_id': None}
            with destination.open('rb') as handle:
                result = json.loads(handle.read(1024))
            if (set(result) != {'state', 'run_id'} or result['state'] not in {'accepted', 'rejected', 'unknown'}):
                return {'state': 'unknown', 'run_id': None}
            return result
        finally:
            if process.pid is not None:
                if process.is_alive():
                    process.terminate()
                    process.join(0.25)
                if process.is_alive():
                    process.kill()
                process.join(1)
                process.close()


def dispatch_existing_job(jobs, job, repository, repository_id, *, submit=submit_once):
    identity = JobIdentity(**job['identity'])
    mode = authentication_mode()
    reservation = jobs.reserve_dispatch(identity, repository, authentication_mode=mode)
    if reservation is None:
        return jobs.get(identity)
    try:
        result = submit(identity.job_id, repository, repository_id, deadline_epoch=job['deadline_epoch'], mode=mode)
    except Exception:
        result = {'state': 'unknown', 'run_id': None}
    return jobs.finish_dispatch(identity, reservation, result['state'], run_id=result['run_id'])


def dispatch_if_enabled(scan, adapter, qualification=None):
    """Trusted deployment switch only; public intake still cannot select a profile.

    Activation requires separately retained profile/image qualification and the
    real protected-main/backend-release proof. A flag is not that evidence.
    The full-project profile is attached only when select_production_profile
    accepts a controlled-project receipt. Bitcoin execution is not implied.
    """
    from nico.assessment_worker_capacity_v1 import select_production_profile
    selected = select_production_profile(qualification)
    if selected is not None and isinstance(scan, dict):
        scan = {**scan, "cpp_worker_profile": selected["profile"],
                "cpp_worker_resource_class": selected["resource_class"]}
    if os.getenv('NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED') != '1':
        return scan
    repository = os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY', 'BoneManTGRM/NICO')
    repository_id = os.getenv('NICO_ASSESSMENT_WORKER_REPOSITORY_ID', '')
    jobs = WorkerJobs(adapter)
    job = jobs.get_by_id(scan['worker_job_id'])
    if job is None:
        raise ValueError('worker_dispatch_job_missing')
    dispatch_existing_job(jobs, job, repository, repository_id)
    return adapter.get('scanner_runs', scan['scan_id'])
