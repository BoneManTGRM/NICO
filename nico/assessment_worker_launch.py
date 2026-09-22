"""Dedicated Actions launcher. Public dispatch input grants no execution authority."""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import parse_qs, urlencode, urlsplit

import requests

from nico.assessment_worker_auth import AUDIENCE, JOB_ID, WORKFLOW
from nico.assessment_worker_consumer import WorkerTransport, _unique_object, consume_one_job
from nico.assessment_worker_container import _command


def actions_identity():
    """Early runner guard; the backend still verifies all signed token claims."""
    repository = os.getenv('GITHUB_REPOSITORY', '')
    revision = os.getenv('GITHUB_SHA', '')
    if (not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository)
            or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or not re.fullmatch(r'[1-9][0-9]{0,19}', os.getenv('GITHUB_REPOSITORY_ID', ''))
            or os.getenv('GITHUB_EVENT_NAME') != 'workflow_dispatch'
            or os.getenv('GITHUB_REF') != 'refs/heads/main'
            or os.getenv('GITHUB_WORKFLOW_SHA') != revision
            or os.getenv('GITHUB_WORKFLOW_REF') != repository + '/' + WORKFLOW + '@refs/heads/main'
            or os.getenv('RUNNER_ENVIRONMENT') != 'github-hosted'):
        raise ValueError('worker_actions_identity_invalid')
    return repository, revision


def read_response(response, *, limit, deadline):
    if response.status_code != 200:
        raise ValueError('worker_http_rejected')
    raw = bytearray()
    for chunk in response.iter_content(chunk_size=65536):
        if time.monotonic() >= deadline:
            raise ValueError('worker_response_deadline')
        if len(raw) + len(chunk) > limit:
            raise ValueError('worker_response_size_invalid')
        raw.extend(chunk)
    if time.monotonic() >= deadline:
        raise ValueError('worker_response_deadline')
    return bytes(raw)


@dataclass(frozen=True)
class ActionsWorkerToken:
    """Picklable provider invoked inside WorkerTransport's killable process.

    The object stores only the job identity. Credentials are read just in time,
    never persisted, printed, exchanged for operator access or sent on redirects.
    """
    job_id: str

    def __call__(self):
        actions_identity()
        if not JOB_ID.fullmatch(self.job_id):
            raise ValueError('worker_job_id_invalid')
        request_url = os.getenv('ACTIONS_ID_TOKEN_REQUEST_URL', '')
        credential = os.getenv('ACTIONS_ID_TOKEN_REQUEST_TOKEN', '')
        parsed = urlsplit(request_url)
        if (parsed.scheme != 'https' or not parsed.hostname
                or not parsed.hostname.endswith('.actions.githubusercontent.com')
                or parsed.username or parsed.password or parsed.port not in {None, 443}
                or parsed.fragment or any(char.isspace() for char in request_url)
                or 'audience' in parse_qs(parsed.query, keep_blank_values=True)
                or not credential or len(credential) > 16384
                or any(char.isspace() for char in credential)):
            raise ValueError('worker_oidc_environment_invalid')
        url = request_url + ('&' if parsed.query else '?') + urlencode({'audience': AUDIENCE + '/' + self.job_id})
        session = requests.Session()
        session.trust_env = False
        response = None
        try:
            deadline = time.monotonic() + 8
            response = session.get(url, headers={'Authorization': 'Bearer ' + credential,
                'Accept': 'application/json'}, allow_redirects=False, stream=True, timeout=(2, 5))
            raw = read_response(response, limit=65536, deadline=deadline)
            value = json.loads(raw, object_pairs_hook=_unique_object)
            token = value.get('value') if isinstance(value, dict) else None
            if (not isinstance(token, str) or not token or len(token) > 16384
                    or any(char.isspace() for char in token)):
                raise ValueError('worker_oidc_token_invalid')
            return token
        finally:
            if response is not None:
                response.close()
            session.close()


def image_reference(value, repository):
    # An immutable registry manifest and a Docker config ID are distinct. Both
    # are checked; this function never authorizes publishing to the registry.
    prefix = 'ghcr.io/' + repository.lower() + '/assessment-cppcheck@sha256:'
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r'[0-9a-f]{64}', value):
        raise ValueError('worker_image_reference_invalid')
    return value


def provision_image(expected_id, reference, repository, root, checkpoint, *, command=_command, registry_token=None):
    reference = image_reference(reference, repository)
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', expected_id):
        raise ValueError('worker_image_identity_invalid')
    if registry_token is not None and (not isinstance(registry_token, str)
            or not 0 < len(registry_token) <= 16384 or not registry_token.isascii()
            or any(char.isspace() for char in registry_token)):
        raise ValueError('worker_image_credential_invalid')
    # Registry authority is controller-only, explicit and never inherited from
    # ambient Docker auth. Remove the private config before returning to source
    # acquisition, including all failure, timeout and cancellation paths.
    with tempfile.TemporaryDirectory(prefix='image-auth-', dir=root) as config:
        args = ['docker', '--config', config, '--host', 'unix:///var/run/docker.sock']
        if registry_token is not None:
            command([*args, 'login', 'ghcr.io', '--username', repository.split('/')[0], '--password-stdin'],
                checkpoint=checkpoint, timeout=15, input_bytes=(registry_token + '\n').encode(), limit=65536)
        command([*args, 'pull', '--quiet', '--platform=linux/amd64', reference],
                checkpoint=checkpoint, timeout=240, limit=65536)
        metadata = json.loads(command([*args, 'image', 'inspect', reference], checkpoint=checkpoint))
        if (not isinstance(metadata, list) or len(metadata) != 1 or not isinstance(metadata[0], dict)
                or metadata[0].get('Id') != expected_id
                or metadata[0].get('Os') != 'linux' or metadata[0].get('Architecture') != 'amd64'):
            raise ValueError('worker_image_identity_mismatch')
        checkpoint()
    return {'image_manifest': reference, 'image_config_id': expected_id}


def run(job_id, backend, reference):
    repository, revision = actions_identity()
    reference = image_reference(reference, repository)
    transport = WorkerTransport(backend, job_id, revision, ActionsWorkerToken(job_id))

    def acquire(job, root, checkpoint):
        from nico.assessment_worker_source import acquire_public_github_inputs
        image = provision_image(job['contract']['image_digest'], reference, repository, root, checkpoint)
        source, evidence = acquire_public_github_inputs(job, root, checkpoint)
        return source, {**evidence, **image}

    return consume_one_job(transport, acquire=acquire)


def main():
    """Configuration comes from protected workflow variables, never dispatch text."""
    try:
        result = run(os.environ.get('NICO_WORKER_JOB_ID', ''),
                     os.environ.get('NICO_PRODUCTION_BACKEND_URL', ''),
                     os.environ.get('NICO_ASSESSMENT_WORKER_IMAGE', ''))
    except Exception as error:
        code = str(error)
        if not re.fullmatch(r'worker_[a-z_]{1,80}', code):
            code = 'worker_launch_failed'
        print(json.dumps({'status': 'failed', 'code': code}))
        return 1
    # Raw receipt/source evidence already resides in the authenticated backend.
    # Action logs retain only identifiers, never source, diagnostics or tokens.
    print(json.dumps({key: result[key] for key in ('job_id', 'receipt_sha256', 'scanner_status')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
