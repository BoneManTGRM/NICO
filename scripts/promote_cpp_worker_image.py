"""Exact-image publication primitive for an authorized, disposable controller.

No ambient credential fallback, workflow grant, automatic retry or production
activation. A caller must establish publication authority and independently
anchor the retained handoff before invoking this primitive. Public retrieval
requires a separate clean runner; publication alone does not prove it.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tempfile
import time

from nico.assessment_worker_container import _command
from scripts.export_qualified_cpp_worker_image import (
    MAX_ARCHIVE_BYTES, _canonical, _verify_archive_config, validate_control_proof, validate_full_project_qualification,
)

DESTINATION = 'ghcr.io/bonemantgrm/nico/assessment-cppcheck'
MAX_SECONDS = 300


@contextmanager
def _regular(path, limit):
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    except OSError as error:
        raise ValueError('image_promotion_regular_file_required') from error
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError('image_promotion_regular_file_required')
        yield source


def _read(path, limit):
    with _regular(path, limit) as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('image_promotion_input_too_large')
    return raw


def _sha(value):
    return isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)


def _receipt(path, value):
    # Durable intent precedes push; replacement never exposes partial JSON.
    temporary = path.with_suffix('.tmp')
    with temporary.open('wb') as output:
        output.write(_canonical(value) + b'\n')
        output.flush()
        os.fsync(output.fileno())
    temporary.replace(path)
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _metadata(raw, image):
    value = json.loads(raw)
    if (not isinstance(value, list) or len(value) != 1 or not isinstance(value[0], dict)
            or value[0].get('Id') != image or value[0].get('Os') != 'linux'
            or value[0].get('Architecture') != 'amd64'):
        raise ValueError('image_promotion_loaded_identity_invalid')
    return value[0]


def publish_image(directory, expected_sha256, recipe, output, *, registry_token, command=_command):
    """Promote anchored bytes, retaining uncertainty if a push is interrupted.

    This low-level operation deliberately has no CLI or workflow trigger until
    its controller's registry authority and credential source are established.
    """
    deadline = time.monotonic() + MAX_SECONDS

    def checkpoint():
        if time.monotonic() >= deadline:
            raise ValueError('image_promotion_deadline')

    if (not isinstance(registry_token, str) or not 0 < len(registry_token) <= 16384
            or not registry_token.isascii() or any(c.isspace() for c in registry_token)):
        raise ValueError('image_promotion_credential_invalid')
    directory, output = Path(directory), Path(output)
    raw = _read(directory / 'handoff.json', 65536)
    if not _sha(expected_sha256) or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError('image_promotion_handoff_mismatch')
    manifest = json.loads(raw)
    if (not isinstance(manifest, dict) or manifest.get('schema') not in {'nico.qualified-image-handoff.v1','nico.qualified-image-handoff.v2'}
            or manifest.get('platform') != 'linux/amd64'
            or manifest.get('registry_published') is not False
            or manifest.get('production_qualified') is not False):
        raise ValueError('image_promotion_handoff_invalid')
    image, source_sha = manifest.get('image_config_id'), manifest.get('source_sha')
    if (not isinstance(image, str) or not re.fullmatch(r'sha256:[0-9a-f]{64}', image)
            or not isinstance(source_sha, str) or not re.fullmatch(r'[0-9a-f]{40}', source_sha)):
        raise ValueError('image_promotion_identity_invalid')
    proof = json.loads(_read(directory / 'qualification.json', 4 * 1024 * 1024))
    proof_hash, profiles = validate_control_proof(proof, source_sha=source_sha, image=image)
    if proof_hash != manifest.get('qualification_sha256') or profiles != manifest.get('owned_control_profiles'):
        raise ValueError('image_promotion_qualification_mismatch')
    if manifest['schema']=='nico.qualified-image-handoff.v2':
        full=json.loads(_read(directory/'full-project-qualification.json',16*1024*1024))
        full_hash=validate_full_project_qualification(full,source_sha=source_sha,image=image)
        if full_hash!=manifest.get('full_project_qualification_sha256'):
            raise ValueError('image_promotion_qualification_mismatch')
    elif manifest.get('full_project_qualification_sha256') is not None:
        raise ValueError('image_promotion_qualification_mismatch')
    if hashlib.sha256(_read(recipe, 65536)).hexdigest() != manifest.get('recipe_sha256'):
        raise ValueError('image_promotion_recipe_mismatch')
    archive = manifest.get('archive')
    if (not isinstance(archive, dict) or archive.get('name') != 'image.tar'
            or type(archive.get('bytes')) is not int or not 0 < archive['bytes'] <= MAX_ARCHIVE_BYTES
            or not _sha(archive.get('sha256'))):
        raise ValueError('image_promotion_archive_invalid')
    checkpoint()
    output.mkdir(mode=0o700)  # Never overwrite a previous attempt or retry it.
    receipt_path = output / 'publication.json'
    result = {'schema': 'nico.image-publication.v1', 'handoff_sha256': expected_sha256,
        'source_sha': source_sha, 'image_config_id': image, 'image_manifest': None,
        'destination_tag': DESTINATION + ':handoff-' + expected_sha256,
        'state': 'failed_before_push', 'registry_published': False,
        'anonymous_pull_verified': False, 'production_qualified': False}
    _receipt(receipt_path, result)
    with tempfile.TemporaryDirectory(prefix='private-', dir=output) as private:
        stage = Path(private)
        staged_archive = stage / 'image.tar'
        digest, count = hashlib.sha256(), 0
        with _regular(directory / 'image.tar', MAX_ARCHIVE_BYTES) as source, staged_archive.open('wb') as target:
            while chunk := source.read(1024 * 1024):
                checkpoint()
                count += len(chunk)
                if count > archive['bytes']:
                    raise ValueError('image_promotion_archive_mismatch')
                digest.update(chunk)
                target.write(chunk)
        if count != archive['bytes'] or digest.hexdigest() != archive['sha256']:
            raise ValueError('image_promotion_archive_mismatch')
        _verify_archive_config(staged_archive, image, checkpoint=checkpoint)
        config = stage / 'docker-config'
        config.mkdir(mode=0o700)
        args = ['docker', '--config', str(config), '--host', 'unix:///var/run/docker.sock']

        def docker(*parts, timeout=30, **kwargs):
            checkpoint()
            return command([*args, *parts], checkpoint=checkpoint,
                timeout=min(timeout, deadline - time.monotonic()), limit=65536, **kwargs)

        try:
            docker('image', 'load', '--input', str(staged_archive), timeout=90)
            _metadata(docker('image', 'inspect', image), image)
            docker('image', 'tag', image, result['destination_tag'])
            docker('login', 'ghcr.io', '--username', 'BoneManTGRM', '--password-stdin',
                input_bytes=(registry_token + '\n').encode())
            checkpoint()
            result.update(state='push_unknown', registry_published=None)
            _receipt(receipt_path, result)
            docker('image', 'push', result['destination_tag'], timeout=180)
            result.update(state='published_but_unverified', registry_published=True)
            _receipt(receipt_path, result)
            metadata = _metadata(docker('image', 'inspect', result['destination_tag']), image)
            refs = metadata.get('RepoDigests', [])
            prefix = DESTINATION + '@sha256:'
            matches = {ref for ref in refs if isinstance(ref, str)
                and ref.startswith(prefix) and _sha(ref[len(prefix):])}
            if len(matches) != 1:
                raise ValueError('image_promotion_manifest_unresolved')
            result['image_manifest'] = matches.pop()
            checkpoint()
            _receipt(receipt_path, result)
        except (Exception, KeyboardInterrupt):
            # Raw Docker errors may contain credentials. Retain only the phase;
            # a CLI timeout does not roll back the daemon or registry operation.
            _receipt(receipt_path, result)
    return result
