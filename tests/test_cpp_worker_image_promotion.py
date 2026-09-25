"""Image-promotion contracts over owned inert archives; no registry access."""
import hashlib
import io
import json
import tarfile
from pathlib import Path

import pytest

from scripts import export_qualified_cpp_worker_image as handoff
from scripts import promote_cpp_worker_image as promotion


@pytest.fixture
def package(tmp_path):
    config = b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    image = 'sha256:' + hashlib.sha256(config).hexdigest()
    base = {'image_digest': image, 'profile': 'cppcheck-standalone-v1'}
    proof = {'schema': 'nico.cppcheck_worker_control.v1', 'source_sha': 'a' * 40,
             'status': 'PASS_OWNED_RUNTIME_CASES', 'contract': base,
             **{key: {'contract': {**base, 'profile': profile}} for key, profile in (
                 ('configured_control', 'cpp-configured-v1'), ('configured_negative', 'cpp-configured-v1'),
                 ('runtime_control', 'cpp-runtime-cases-v1'), ('runtime_negative', 'cpp-runtime-cases-v1'))},
             'sanitizer_controls': [{'contract': {**base, 'profile': 'cpp-sanitized-v1'}} for _ in range(4)]}
    proof['evidence_sha256'] = hashlib.sha256(handoff._canonical(proof)).hexdigest()
    recipe = tmp_path / 'recipe'; recipe.write_bytes(b'owned inert recipe\n')
    directory = tmp_path / 'handoff'
    def exporter(_image, archive):
        name = image[7:] + '.json'
        with tarfile.open(archive, 'w') as output:
            for path, raw in [(name, config), ('manifest.json', json.dumps([{'Config': name, 'Layers': [], 'RepoTags': []}]).encode())]:
                member = tarfile.TarInfo(path); member.size = len(raw)
                output.addfile(member, io.BytesIO(raw))
    handoff.export_qualified_image(proof, [{'Id': image, 'Os': 'linux', 'Architecture': 'amd64', 'Size': 1024}],
        recipe, directory, source_sha='a' * 40, exporter=exporter)
    expected = hashlib.sha256((directory / 'handoff.json').read_bytes()).hexdigest()
    return directory, expected, recipe, image


def fake_docker(image, calls, *, fail=None, wrong_config=False):
    manifest = promotion.DESTINATION + '@sha256:' + 'd' * 64
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        if 'push' in argv:
            # The durable intent must exist before any external write starts.
            assert json.loads(Path(kwargs.pop('receipt_probe')).read_text())['state'] == 'push_unknown'
        if fail and fail in argv:
            raise ValueError('worker_container_timed_out')
        if 'inspect' in argv:
            return json.dumps([{'Id': 'sha256:' + 'f' * 64 if wrong_config else image,
                'Os': 'linux', 'Architecture': 'amd64', 'RepoDigests': [manifest]}]).encode()
        return b''
    return run


def publish(package, tmp_path, *, fail=None, wrong_config=False):
    directory, expected, recipe, image = package
    calls = []; receipt = tmp_path / 'promotion' / 'publication.json'
    command = fake_docker(image, calls, fail=fail, wrong_config=wrong_config)
    def observed(argv, **kwargs):
        if 'push' in argv: kwargs['receipt_probe'] = str(receipt)
        return command(argv, **kwargs)
    result = promotion.publish_image(directory, expected, recipe, receipt.parent,
        registry_token='owned-inert-fixture-token', command=observed)
    return result, calls


def test_publishes_verified_archive_without_claiming_anonymous_or_production(package, tmp_path):
    result, calls = publish(package, tmp_path)
    assert result['state'] == 'published_but_unverified'
    assert result['registry_published'] is True
    assert result['anonymous_pull_verified'] is False and result['production_qualified'] is False
    assert result['image_config_id'] == package[3]
    assert result['image_manifest'] == promotion.DESTINATION + '@sha256:' + 'd' * 64
    assert not any('build' in argv or 'run' in argv or 'pull' in argv for argv, _ in calls)
    assert all('owned-inert-fixture-token' not in ' '.join(argv) for argv, _ in calls)
    login = next(options for argv, options in calls if 'login' in argv)
    assert login['input_bytes'] == b'owned-inert-fixture-token\n'
    assert all(argv[:2] == ['docker', '--config'] and argv[3:5] == ['--host', 'unix:///var/run/docker.sock'] for argv, _ in calls)
    assert not list((tmp_path / 'promotion').glob('private-*'))


@pytest.mark.parametrize('member', ['handoff.json', 'qualification.json', 'image.tar'])
def test_substituted_bytes_rejected_before_docker(package, tmp_path, member):
    path = package[0] / member; path.write_bytes(path.read_bytes() + b'altered')
    calls = []
    with pytest.raises(ValueError):
        promotion.publish_image(package[0], package[1], package[2], tmp_path / 'promotion',
            registry_token='owned-inert-fixture-token', command=lambda *args, **kwargs: calls.append(args))
    assert calls == []


def test_wrong_recipe_rejected_before_docker(package, tmp_path):
    package[2].write_bytes(b'another recipe')
    with pytest.raises(ValueError, match='recipe'):
        publish(package, tmp_path)


@pytest.mark.parametrize('member', ['handoff.json', 'qualification.json', 'image.tar'])
def test_symlink_input_rejected(package, tmp_path, member):
    original = package[0] / member; retained = tmp_path / ('retained-' + member)
    original.rename(retained); original.symlink_to(retained)
    with pytest.raises(ValueError, match='regular'):
        publish(package, tmp_path)


def test_load_failure_never_attempts_push(package, tmp_path):
    result, calls = publish(package, tmp_path, fail='load')
    assert result['state'] == 'failed_before_push' and result['registry_published'] is False
    assert not any('push' in argv for argv, _ in calls)


def test_wrong_loaded_config_never_attempts_push(package, tmp_path):
    result, calls = publish(package, tmp_path, wrong_config=True)
    assert result['state'] == 'failed_before_push'
    assert not any('push' in argv for argv, _ in calls)


def test_push_timeout_retains_unknown_and_never_retries(package, tmp_path):
    result, calls = publish(package, tmp_path, fail='push')
    assert result['state'] == 'push_unknown' and result['registry_published'] is None
    assert sum('push' in argv for argv, _ in calls) == 1
    assert result['anonymous_pull_verified'] is False and result['production_qualified'] is False


def test_existing_receipt_directory_prevents_repeat_publication(package, tmp_path):
    publish(package, tmp_path)
    with pytest.raises(FileExistsError): publish(package, tmp_path)


@pytest.mark.parametrize('after_push', ['inspect_failure', 'foreign_manifest', 'wrong_config'])
def test_post_push_failure_preserves_publication_without_readiness(package, tmp_path, after_push):
    pushed = False
    def command(argv, **kwargs):
        nonlocal pushed
        if 'push' in argv: pushed = True
        if 'inspect' in argv:
            if pushed and after_push == 'inspect_failure': raise ValueError('lost inspect')
            return json.dumps([{'Id': 'sha256:' + 'f' * 64 if pushed and after_push == 'wrong_config' else package[3],
                'Os': 'linux', 'Architecture': 'amd64',
                'RepoDigests': ['ghcr.io/another-owner/image@sha256:' + 'd' * 64]}]).encode()
        return b''
    result = promotion.publish_image(package[0], package[1], package[2], tmp_path / 'promotion',
        registry_token='owned-inert-fixture-token', command=command)
    assert result['state'] == 'published_but_unverified' and result['registry_published'] is True
    assert result['image_manifest'] is None and result['anonymous_pull_verified'] is False


def test_archive_replaced_after_validation_cannot_change_loaded_bytes(package, tmp_path):
    original = (package[0] / 'image.tar').read_bytes()
    def command(argv, **kwargs):
        if 'load' in argv:
            (package[0] / 'image.tar').write_bytes(b'replaced')
            assert Path(argv[-1]).read_bytes() == original
            raise ValueError('stop after private copy proof')
        pytest.fail('load failure must stop publication')
    result = promotion.publish_image(package[0], package[1], package[2], tmp_path / 'promotion',
        registry_token='owned-inert-fixture-token', command=command)
    assert result['state'] == 'failed_before_push'


def test_v2_handoff_requires_same_image_full_project_qualification(tmp_path):
    config=b'{"architecture":"amd64","os":"linux","rootfs":{"type":"layers","diff_ids":[]}}'
    image='sha256:'+hashlib.sha256(config).hexdigest()
    base={'image_digest':image,'profile':'cppcheck-standalone-v1'}
    proof={'schema':'nico.cppcheck_worker_control.v1','source_sha':'a'*40,
        'status':'PASS_OWNED_RUNTIME_CASES','contract':base,
        **{key:{'contract':{**base,'profile':profile}} for key,profile in (
            ('configured_control','cpp-configured-v1'),('configured_negative','cpp-configured-v1'),
            ('runtime_control','cpp-runtime-cases-v1'),('runtime_negative','cpp-runtime-cases-v1'))},
        'sanitizer_controls':[{'contract':{**base,'profile':'cpp-sanitized-v1'}} for _ in range(4)]}
    proof['evidence_sha256']=hashlib.sha256(handoff._canonical(proof)).hexdigest()
    full={'schema':'nico.cpp-configuration-qualification.v1','status':'BASELINE_EXECUTED',
        'stage':'completed','production_qualified':False,'compiled':True,'tests_executed':True,
        'source':{'commit_sha':'b'*40,'tree_sha':'c'*40},
        'probe':{'image_config_digest':image,'status':'BASELINE_EXECUTED','compiled':True,
            'tests_passed':True,'generated_context_verified':True,
            'project_compiler':{'complete':True},'project_static':{'complete':True},
            'project_static_stage':{'complete':True}},
        'runtime':{'complete':True,'native_evidence_sha256':'d'*64}}
    recipe=tmp_path/'recipe'; recipe.write_bytes(b'full project recipe\n')
    directory=tmp_path/'handoff-v2'
    def exporter(_image,archive):
        name=image[7:]+'.json'
        with tarfile.open(archive,'w') as output:
            for path,raw in [(name,config),('manifest.json',json.dumps([{'Config':name,'Layers':[],'RepoTags':[]}]).encode())]:
                member=tarfile.TarInfo(path); member.size=len(raw); output.addfile(member,io.BytesIO(raw))
    result=handoff.export_qualified_image(proof,[{'Id':image,'Os':'linux','Architecture':'amd64','Size':1024}],
        recipe,directory,source_sha='a'*40,full_project_qualification=full,exporter=exporter)
    assert result['schema']=='nico.qualified-image-handoff.v2'
    assert (directory/'full-project-qualification.json').is_file()
    broken=dict(full); broken['runtime']={'complete':False,'native_evidence_sha256':'d'*64}
    with pytest.raises(ValueError,match='full_project'):
        handoff.export_qualified_image(proof,[{'Id':image,'Os':'linux','Architecture':'amd64','Size':1024}],
            recipe,tmp_path/'rejected',source_sha='a'*40,full_project_qualification=broken,exporter=exporter)


def test_budget_exhaustion_prevents_first_docker_command(package, tmp_path, monkeypatch):
    monkeypatch.setattr(promotion, 'MAX_SECONDS', 0)
    with pytest.raises(ValueError, match='deadline'):
        publish(package, tmp_path)
