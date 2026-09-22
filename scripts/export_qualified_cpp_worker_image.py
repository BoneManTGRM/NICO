"""Retain the exact owned-control image; this does not publish or activate it."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import resource
import shutil
import subprocess
import tarfile

MAX_ARCHIVE_BYTES = 2 * 1024 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _read_json(path, limit):
    with Path(path).open('rb') as source:
        raw = source.read(limit + 1)
    if len(raw) > limit:
        raise ValueError('image_handoff_input_too_large')
    return json.loads(raw)


def _save_image(image, archive):
    def limits():
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_ARCHIVE_BYTES, MAX_ARCHIVE_BYTES))
    # Only a validated local config ID is accepted. No pull, login or rebuild.
    subprocess.run(['docker', 'image', 'save', '--output', str(archive), image],
                   check=True, timeout=45, preexec_fn=limits)


def _verify_archive_config(archive, image, *, checkpoint=lambda: None):
    config_names = {image[7:] + '.json', 'blobs/sha256/' + image[7:]}
    retained = {}
    with tarfile.open(archive, 'r:') as source:
        for count, member in enumerate(source, 1):
            checkpoint()
            if count > 4096:
                raise ValueError('image_handoff_archive_members')
            if member.name not in config_names | {'manifest.json'}:
                continue
            if (member.name in retained or not member.isfile()
                    or not 0 < member.size <= 1024 * 1024):
                raise ValueError('image_handoff_archive_metadata')
            stream = source.extractfile(member)
            if stream is None:
                raise ValueError('image_handoff_archive_metadata')
            with stream:
                retained[member.name] = stream.read(1024 * 1024 + 1)
    manifest = json.loads(retained.get('manifest.json', b'null'))
    if (not isinstance(manifest, list) or len(manifest) != 1
            or not isinstance(manifest[0], dict)
            or manifest[0].get('Config') not in config_names
            or manifest[0]['Config'] not in retained
            or 'sha256:' + hashlib.sha256(retained[manifest[0]['Config']]).hexdigest() != image):
        raise ValueError('image_handoff_archive_config_mismatch')


def validate_control_proof(proof, *, source_sha, image):
    """Verify owned-control bindings; this never grants production qualification."""
    proof = dict(proof)
    proof_hash = proof.pop('evidence_sha256', None)
    if (not re.fullmatch(r'[0-9a-f]{40}', source_sha)
            or proof.get('source_sha') != source_sha
            or proof.get('schema') != 'nico.cppcheck_worker_control.v1'
            or proof.get('status') != 'PASS_OWNED_RUNTIME_CASES'
            or hashlib.sha256(_canonical(proof)).hexdigest() != proof_hash):
        raise ValueError('image_handoff_qualification_invalid')
    try:
        controls = [proof, *(proof[key] for key in ('configured_control', 'configured_negative',
                    'runtime_control', 'runtime_negative')), *proof['sanitizer_controls']]
        profiles = {control['contract']['profile'] for control in controls}
        if (len(controls) != 9 or profiles != {'cppcheck-standalone-v1', 'cpp-configured-v1',
                'cpp-sanitized-v1', 'cpp-runtime-cases-v1'}
                or any(control['contract']['image_digest'] != image for control in controls)):
            raise ValueError('image_handoff_control_mismatch')
    except (KeyError, TypeError) as error:
        raise ValueError('image_handoff_control_mismatch') from error
    return proof_hash, sorted(profiles)


def export_qualified_image(proof, metadata, recipe, output, *, source_sha, exporter=_save_image):
    """Bind trusted native proof and Docker export without expanding its scope."""
    if (not isinstance(metadata, list) or len(metadata) != 1
            or metadata[0].get('Os') != 'linux' or metadata[0].get('Architecture') != 'amd64'
            or type(metadata[0].get('Size')) is not int
            or not 0 < metadata[0]['Size'] <= MAX_ARCHIVE_BYTES):
        raise ValueError('image_handoff_metadata_invalid')
    image = metadata[0].get('Id', '')
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', image):
        raise ValueError('image_handoff_image_invalid')
    proof_hash, profiles = validate_control_proof(proof, source_sha=source_sha, image=image)
    recipe = Path(recipe)
    if not 0 < recipe.stat().st_size <= 65536:
        raise ValueError('image_handoff_recipe_invalid')
    output = Path(output)
    output.mkdir(mode=0o700)  # Existing retained handoffs are never overwritten.
    try:
        archive = output / 'image.tar'
        exporter(image, archive)
        if not 0 < archive.stat().st_size <= MAX_ARCHIVE_BYTES:
            raise ValueError('image_handoff_archive_size')
        _verify_archive_config(archive, image)
        with archive.open('rb') as source:
            archive_hash = hashlib.file_digest(source, 'sha256').hexdigest()
        result = {'schema': 'nico.qualified-image-handoff.v1', 'source_sha': source_sha,
            'image_config_id': image, 'platform': 'linux/amd64',
            'archive': {'name': 'image.tar', 'bytes': archive.stat().st_size, 'sha256': archive_hash},
            'recipe_sha256': hashlib.sha256(recipe.read_bytes()).hexdigest(),
            'qualification_sha256': proof_hash, 'owned_control_profiles': sorted(profiles),
            'registry_published': False, 'production_qualified': False,
            'scope': 'same-image owned controls only; no full-project or Bitcoin qualification'}
        (output / 'handoff.json').write_bytes(_canonical(result) + b'\n')
        (output / 'qualification.json').write_bytes(_canonical(dict(proof, evidence_sha256=proof_hash)) + b'\n')
        return result
    except BaseException:
        shutil.rmtree(output)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-sha', required=True)
    args = parser.parse_args()
    result = export_qualified_image(
        _read_json('cppcheck-worker-control.json', 4 * 1024 * 1024),
        _read_json('cppcheck-image-metadata.json', 1024 * 1024),
        Path('docker/assessment-cppcheck.Dockerfile'), Path('cppcheck-image-handoff'),
        source_sha=args.source_sha)
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
