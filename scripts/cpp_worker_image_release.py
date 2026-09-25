"""Actions-only image publication and independently recorded registry access."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import tempfile
import time
import requests

from nico.assessment_worker_container import _command
from nico.assessment_worker_launch import image_reference, provision_image
from scripts.promote_cpp_worker_image import DESTINATION, _read, _receipt, publish_image

REPOSITORY = 'BoneManTGRM/NICO'
BRANCH = 'refs/heads/feat/cpp-full-project-capacity'
WORKFLOW = REPOSITORY + '/.github/workflows/cpp-worker-boundary-qualification.yml@' + BRANCH
RETRIEVAL_WORKFLOW = REPOSITORY + '/.github/workflows/cpp-worker-image-retrieval.yml@' + BRANCH
SAFE_ERRORS = {'image_release_clean_daemon_required', 'worker_container_control_failed',
    'worker_container_timed_out', 'worker_image_identity_mismatch', 'worker_image_credential_invalid',
    'image_release_retrieval_deadline', 'image_release_identity_invalid', 'image_release_publication_invalid'}


def identity(mode):
    revision = os.environ.get('GITHUB_SHA', '')
    anchor = os.environ.get('NICO_IMAGE_HANDOFF_SHA256', '')
    attempt = os.environ.get('GITHUB_RUN_ATTEMPT', '')
    if (mode not in {'publish', 'verify'}
            or os.environ.get('GITHUB_REPOSITORY') != REPOSITORY
            or os.environ.get('GITHUB_REPOSITORY_ID') != '1282576027'
            or os.environ.get('GITHUB_EVENT_NAME') != 'push'
            or os.environ.get('GITHUB_REF') != BRANCH
            or os.environ.get('GITHUB_WORKFLOW_REF') not in (
                {WORKFLOW, RETRIEVAL_WORKFLOW} if mode == 'verify' else {WORKFLOW})
            or os.environ.get('GITHUB_WORKFLOW_SHA') != revision
            or os.environ.get('RUNNER_ENVIRONMENT') != 'github-hosted'
            or os.environ.get('GITHUB_JOB') != mode + '-image'
            or not re.fullmatch(r'[1-9][0-9]{0,9}', attempt)
            or (mode == 'publish' and attempt != '1')
            or not re.fullmatch(r'[0-9a-f]{40}', revision)
            or not re.fullmatch(r'[0-9a-f]{64}', anchor)):
        raise ValueError('image_release_identity_invalid')
    return revision, anchor


def publish(directory, recipe, output, *, command=_command):
    revision, anchor = identity('publish')
    manifest = json.loads(_read(Path(directory) / 'handoff.json', 65536))
    if not isinstance(manifest, dict) or manifest.get('source_sha') != revision:
        raise ValueError('image_release_source_mismatch')
    # Remove the credential from this process environment before subprocesses.
    token = os.environ.pop('NICO_IMAGE_PUBLICATION_TOKEN', '')
    return publish_image(directory, anchor, recipe, output, registry_token=token, command=command)


def anonymous_registry_status():
    """Retain only anonymous HTTP status, never a returned registry token."""
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        response = session.get('https://ghcr.io/token', params={'service': 'ghcr.io',
            'scope': 'repository:bonemantgrm/nico/assessment-cppcheck:pull'},
            allow_redirects=False, stream=True, timeout=(3, 5))
        return response.status_code
    except requests.RequestException:
        return None
    finally:
        if response is not None:
            response.close()
        session.close()


def verify(publication, output, *, command=_command, registry_probe=anonymous_registry_status):
    revision, anchor = identity('verify')
    token = os.environ.pop('NICO_IMAGE_PULL_TOKEN', None)
    if os.environ.get('NICO_IMAGE_PUBLICATION_TOKEN') or os.environ.get('GITHUB_TOKEN'):
        raise ValueError('image_release_anonymous_environment_required')
    image_source = os.environ.get('NICO_IMAGE_QUALIFIED_SOURCE_SHA', revision)
    if not re.fullmatch(r'[0-9a-f]{40}', image_source):
        raise ValueError('image_release_publication_invalid')
    receipt = json.loads(_read(publication, 65536))
    if (not isinstance(receipt, dict) or receipt.get('schema') != 'nico.image-publication.v1'
            or receipt.get('source_sha') != image_source or receipt.get('handoff_sha256') != anchor
            or receipt.get('state') != 'published_but_unverified'
            or receipt.get('registry_published') is not True
            or receipt.get('anonymous_pull_verified') is not False
            or receipt.get('production_qualified') is not False
            or receipt.get('destination_tag') != DESTINATION + ':handoff-' + anchor
            or not isinstance(receipt.get('image_config_id'), str)
            or not re.fullmatch(r'sha256:[0-9a-f]{64}', receipt['image_config_id'])):
        raise ValueError('image_release_publication_invalid')
    reference = image_reference(receipt.get('image_manifest'), REPOSITORY)
    output = Path(output)
    output.mkdir(mode=0o700)
    result = {**receipt, 'schema': 'nico.image-retrieval.v2', 'state': 'retrieval_unverified',
        'controller_source_sha': revision, 'image_pull_verified': False,
        'registry_access_mode': 'actions_package_token' if token is not None else 'anonymous',
        'failure_stage': 'inventory', 'error_code': None, 'anonymous_token_http_status': None}
    _receipt(output / 'verification.json', result)
    deadline = time.monotonic() + 270

    def checkpoint():
        if time.monotonic() >= deadline:
            raise ValueError('image_release_retrieval_deadline')

    try:
        if token is not None:
            result['anonymous_token_http_status'] = registry_probe()
            checkpoint()
        with tempfile.TemporaryDirectory(prefix='private-', dir=output) as directory:
            root = Path(directory)
            config = root / 'docker-config'
            config.mkdir(mode=0o700)
            images = command(['docker', '--config', str(config), '--host', 'unix:///var/run/docker.sock',
                'image', 'ls', '--all', '--quiet', '--no-trunc'], checkpoint=checkpoint, timeout=15, limit=65536)
            if images.strip():
                raise ValueError('image_release_clean_daemon_required')
            def recorded_command(args, **kwargs):
                result['failure_stage'] = next((part for part in ('login', 'pull', 'inspect') if part in args), 'provision')
                _receipt(output / 'verification.json', result)
                return command(args, **kwargs)
            provision_image(receipt['image_config_id'], reference, REPOSITORY, root, checkpoint,
                command=recorded_command, registry_token=token)
            result.update(state='published_and_retrieved', image_pull_verified=True,
                anonymous_pull_verified=token is None, failure_stage=None)
            _receipt(output / 'verification.json', result)
    except (Exception, KeyboardInterrupt) as error:
        result['error_code'] = str(error) if str(error) in SAFE_ERRORS else 'image_release_failed'
        _receipt(output / 'verification.json', result)
        raise
    return result


def main():
    mode = os.environ.get('NICO_IMAGE_RELEASE_MODE')
    try:
        if mode == 'publish':
            result = publish('cppcheck-image-handoff', 'docker/assessment-cppcheck.Dockerfile', 'image-publication')
            success = result['registry_published'] is True and result['image_manifest'] is not None
        elif mode == 'verify':
            result = verify('image-publication/publication.json', 'image-retrieval')
            success = result['image_pull_verified']
        else:
            raise ValueError('image_release_mode_invalid')
        print(json.dumps({key: result[key] for key in ('state', 'registry_published', 'anonymous_pull_verified', 'production_qualified')}))
        return 0 if success else 1
    except Exception as error:
        # Do not log raw Docker/API output or a credential-bearing exception.
        code = str(error) if str(error) in SAFE_ERRORS else 'image_release_failed'
        print(json.dumps({'state': 'image_release_failed', 'code': code, 'production_qualified': False}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
