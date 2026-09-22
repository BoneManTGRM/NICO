"""Submit a pre-authorized durable job to the dedicated protected-main workflow.

No public contract selection, operator credentials, token fallbacks, broad App
tokens or automatic retry of an ambiguous workflow submission are provided.
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


def _submit(job_id, repository, repository_id, *, session=None, signer=None):
    """No retry here: submission may have succeeded before its response was lost."""
    from nico.github_app_auth import build_github_app_jwt
    if (not JOB_ID.fullmatch(job_id)
            or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository)
            or not re.fullmatch(r'[1-9][0-9]{0,19}', repository_id)):
        return {'state': 'rejected', 'run_id': None}
    installation = os.getenv('NICO_GITHUB_APP_INSTALLATION_ID', '')
    if not re.fullmatch(r'[1-9][0-9]{0,19}', installation):
        return {'state': 'rejected', 'run_id': None}
    token, _error = (signer or build_github_app_jwt)()
    if not token:
        return {'state': 'rejected', 'run_id': None}
    owned_session = session is None
    session = session or requests.Session()
    session.trust_env = False
    headers = {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2026-03-10'}
    dispatched = False
    response = None
    try:
        # Explicitly reduce authority to one repository and only Actions write.
        # This cannot grant permissions not already held by the installation.
        response = session.post('https://api.github.com/app/installations/' + installation + '/access_tokens',
            headers={**headers, 'Authorization': 'Bearer ' + token},
            json={'repository_ids': [int(repository_id)], 'permissions': {'actions': 'write'}},
            timeout=(2, 5), allow_redirects=False, stream=True)
        if response.status_code != 201:
            return {'state': 'rejected', 'run_id': None}
        raw = bytearray()
        deadline = time.monotonic() + 8
        for chunk in response.iter_content(chunk_size=65536):
            if len(raw) + len(chunk) > 65536 or time.monotonic() >= deadline:
                return {'state': 'rejected', 'run_id': None}
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
            return {'state': 'rejected', 'run_id': None}
        response.close()
        response = None
        dispatched = True
        response = session.post('https://api.github.com/repos/' + repository + '/actions/workflows/assessment-worker.yml/dispatches',
            headers={**headers, 'Authorization': 'Bearer ' + installation_token},
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


def _submission_child(destination, job_id, repository, repository_id):
    try:
        result = _submit(job_id, repository, repository_id)
        Path(destination).write_text(json.dumps(result))
    except Exception:
        pass  # The parent records unknown; no exception or token is logged.


def submit_once(job_id, repository, repository_id, *, deadline_epoch):
    timeout = min(30, max(0, deadline_epoch - time.time()))
    if timeout <= 0:
        return {'state': 'rejected', 'run_id': None}
    with tempfile.TemporaryDirectory(prefix='nico-dispatch-') as temporary:
        destination = Path(temporary) / 'result.json'
        process = multiprocessing.get_context('spawn').Process(target=_submission_child,
            args=(destination, job_id, repository, repository_id))
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
    reservation = jobs.reserve_dispatch(identity, repository)
    if reservation is None:
        return jobs.get(identity)
    try:
        result = submit(identity.job_id, repository, repository_id, deadline_epoch=job['deadline_epoch'])
    except Exception:
        result = {'state': 'unknown', 'run_id': None}
    return jobs.finish_dispatch(identity, reservation, result['state'], run_id=result['run_id'])


def dispatch_if_enabled(scan, adapter):
    """Trusted deployment switch only; public intake still cannot select a profile.

    Activation requires separately retained profile/image qualification and the
    real protected-main/backend-release proof. A flag is not that evidence.
    """
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
