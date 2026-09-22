"""Owned fixtures for image handoff identity; not native image qualification."""
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from scripts import export_qualified_cpp_worker_image as handoff


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


@pytest.fixture
def inputs(tmp_path):
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    image = 'sha256:' + hashlib.sha256(config).hexdigest()
    contract = {'image_digest': image, 'profile': 'cppcheck-standalone-v1'}
    proof = {'schema': 'nico.cppcheck_worker_control.v1', 'source_sha': 'a' * 40,
             'status': 'PASS_OWNED_RUNTIME_CASES', 'contract': contract,
             'configured_control': {'contract': dict(contract, profile='cpp-configured-v1')},
             'configured_negative': {'contract': dict(contract, profile='cpp-configured-v1')},
             'runtime_control': {'contract': dict(contract, profile='cpp-runtime-cases-v1')},
             'runtime_negative': {'contract': dict(contract, profile='cpp-runtime-cases-v1')},
             'sanitizer_controls': [{'contract': dict(contract, profile='cpp-sanitized-v1')} for _ in range(4)]}
    recipe = tmp_path / 'recipe'; recipe.write_bytes(b'owned recipe fixture\n')
    metadata = [{'Id': image, 'Os': 'linux', 'Architecture': 'amd64', 'Size': 1024}]
    calls = []

    def exporter(expected, archive):
        calls.append(expected)
        assert expected == image
        name = image.removeprefix('sha256:') + '.json'
        with tarfile.open(archive, 'w') as out:
            for path, raw in [(name, config), ('manifest.json', json.dumps([{'Config': name, 'Layers': [], 'RepoTags': []}]).encode())]:
                member = tarfile.TarInfo(path); member.size = len(raw)
                out.addfile(member, io.BytesIO(raw))

    return proof, metadata, recipe, tmp_path / 'handoff', exporter, calls


def package(inputs):
    proof, metadata, recipe, output, exporter, _ = inputs
    proof['evidence_sha256'] = digest({k: v for k, v in proof.items() if k != 'evidence_sha256'})
    return handoff.export_qualified_image(proof, metadata, recipe, output, source_sha='a' * 40, exporter=exporter)


def test_retains_exact_export_and_qualification_binding(inputs):
    result = package(inputs)
    proof, metadata, recipe, output, _, calls = inputs
    assert calls == [metadata[0]['Id']]
    assert result['image_config_id'] == metadata[0]['Id']
    assert result['archive']['sha256'] == hashlib.sha256((output / 'image.tar').read_bytes()).hexdigest()
    assert result['qualification_sha256'] == proof['evidence_sha256']
    assert result['recipe_sha256'] == hashlib.sha256(recipe.read_bytes()).hexdigest()
    assert result['registry_published'] is False
    assert result['production_qualified'] is False
    assert json.loads((output / 'handoff.json').read_bytes()) == result


@pytest.mark.parametrize('mutation', ['failed', 'source', 'image', 'platform', 'missing_control'])
def test_invalid_native_binding_never_exports(inputs, mutation):
    proof, metadata, _, output, _, calls = inputs
    if mutation == 'failed': proof['status'] = 'FAIL'
    if mutation == 'source': proof['source_sha'] = 'b' * 40
    if mutation == 'image': proof['runtime_control']['contract']['image_digest'] = 'sha256:' + 'f' * 64
    if mutation == 'platform': metadata[0]['Architecture'] = 'arm64'
    if mutation == 'missing_control': proof['sanitizer_controls'].pop()
    with pytest.raises(ValueError): package(inputs)
    assert calls == [] and not output.exists()


def test_tampered_proof_hash_never_exports(inputs):
    proof, metadata, recipe, output, exporter, calls = inputs
    proof['evidence_sha256'] = '0' * 64
    with pytest.raises(ValueError):
        handoff.export_qualified_image(proof, metadata, recipe, output, source_sha='a' * 40, exporter=exporter)
    assert calls == [] and not output.exists()


@pytest.mark.parametrize('failure', ['partial', 'wrong_config', 'oversized'])
def test_failed_archive_leaves_no_handoff(inputs, monkeypatch, failure):
    proof, metadata, recipe, output, original, calls = inputs
    def exporter(image, archive):
        if failure == 'partial':
            archive.write_bytes(b'partial'); raise RuntimeError('fixture failure')
        original(image, archive)
        if failure == 'wrong_config': archive.write_bytes(b'not a Docker archive')
    if failure == 'oversized': monkeypatch.setattr(handoff, 'MAX_ARCHIVE_BYTES', 1024)
    changed = (proof, metadata, recipe, output, exporter, calls)
    with pytest.raises((ValueError, RuntimeError, tarfile.TarError)): package(changed)
    assert not output.exists()


def test_existing_handoff_is_never_overwritten(inputs):
    output = inputs[3]; output.mkdir(); (output / 'retained').write_bytes(b'immutable')
    with pytest.raises(FileExistsError): package(inputs)
    assert (output / 'retained').read_bytes() == b'immutable'
    assert inputs[-1] == []
