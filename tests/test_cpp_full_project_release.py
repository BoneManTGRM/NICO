"""Release boundary regressions; native Docker is exercised by the release job."""
import hashlib
import json
from pathlib import Path

import pytest
import yaml

from nico.assessment_cpp_collection import validate_project_collection
from scripts import cpp_full_project_handoff as handoff
from scripts import cpp_full_project_release as release
from tests.test_cpp_assessment_collection import bundle


def retained(tmp_path, kind='undefined'):
    receipt, read, kwargs = bundle(tmp_path, kind=kind)
    root = tmp_path / 'retained'
    (root / 'receipt.json').write_text(json.dumps(receipt))
    for name, key in zip(handoff.CONTRACTS, ('manifest_raw', 'baseline_raw', 'scope_raw')):
        (root / name).write_bytes(kwargs[key])
    decision = validate_project_collection(receipt, read, **kwargs)
    (root / 'collection-acceptance.json').write_text(json.dumps(decision))
    return root, kwargs, decision


@pytest.mark.parametrize('kind', [None, 'undefined'])
def test_native_collection_revalidated_and_target_failures_preserved(tmp_path, kind):
    root, kwargs, decision = retained(tmp_path, kind)
    copy = tmp_path / 'copy'
    digest = handoff.validate_collection(root, source_sha=kwargs['producer_source_sha'], image=kwargs['image'], retain=copy, enabled_targets_required=False, collect_completed_compiler_failures=False)
    assert digest == hashlib.sha256(handoff._canonical(decision)).hexdigest()
    assert handoff.validate_collection(copy, source_sha=kwargs['producer_source_sha'], image=kwargs['image'], enabled_targets_required=False, collect_completed_compiler_failures=False) == digest
    assert json.loads((copy / 'collection-acceptance.json').read_text())['target_tests_passed'] is (kind is None)


@pytest.mark.parametrize('fault', ['producer', 'image', 'decision', 'artifact', 'contract', 'symlink'])
def test_collection_tampering_rejected(tmp_path, fault):
    root, kwargs, _ = retained(tmp_path)
    source, image = kwargs['producer_source_sha'], kwargs['image']
    if fault == 'producer': source = 'e' * 40
    elif fault == 'image': image = 'sha256:' + 'f' * 64
    elif fault == 'decision': (root / 'collection-acceptance.json').write_text('{}')
    elif fault == 'artifact': next((root / 'artifacts').iterdir()).write_text('{}')
    elif fault == 'contract': (root / handoff.CONTRACTS[0]).write_text('{}')
    elif fault == 'symlink':
        target = root / 'receipt.json'; moved = tmp_path / 'moved.json'
        target.rename(moved); target.symlink_to(moved)
    with pytest.raises((ValueError, OSError)):
        handoff.validate_collection(root, source_sha=source, image=image, enabled_targets_required=False, collect_completed_compiler_failures=False)


def test_current_handoff_cannot_downgrade_to_legacy_complete_collection(tmp_path):
    root, kwargs, decision = retained(tmp_path, kind=None)
    assert decision['collection_complete'] is True
    with pytest.raises(ValueError, match='qualification_collection_invalid'):
        handoff.validate_collection(root, source_sha=kwargs['producer_source_sha'], image=kwargs['image'])


@pytest.fixture
def trusted(monkeypatch):
    values = {'GITHUB_REPOSITORY': release.REPOSITORY, 'GITHUB_REPOSITORY_ID': '1282576027',
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
        'GITHUB_WORKFLOW_REF': release.WORKFLOW, 'GITHUB_WORKFLOW_SHA': 'a'*40,
        'GITHUB_SHA': 'a'*40, 'RUNNER_ENVIRONMENT': 'github-hosted',
        'GITHUB_JOB': 'publish-image', 'GITHUB_RUN_ATTEMPT': '1', 'NICO_IMAGE_HANDOFF_SHA256': 'b'*64}
    for key, value in values.items(): monkeypatch.setenv(key, value)


def test_main_manual_release_identity(trusted):
    assert release.identity('publish') == ('a'*40, 'b'*64)


@pytest.mark.parametrize('key,value', [
    ('GITHUB_EVENT_NAME','pull_request'),
    ('GITHUB_REF','refs/heads/feat/cpp-full-project-capacity'), ('GITHUB_RUN_ATTEMPT','2'),
    ('GITHUB_WORKFLOW_SHA','c'*40), ('GITHUB_REPOSITORY_ID','1'),
    ('RUNNER_ENVIRONMENT','self-hosted'), ('GITHUB_WORKFLOW_REF','other'),
    ('GITHUB_JOB','qualify-image'), ('NICO_IMAGE_HANDOFF_SHA256','')])
def test_wrong_release_context_rejected(trusted, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match='identity'):
        release.identity('publish')




def test_marked_main_push_release_identity(trusted, monkeypatch, tmp_path):
    event = tmp_path / 'event.json'
    event.write_text(json.dumps({
        'ref': 'refs/heads/main',
        'head_commit': {'message': 'Release exact C++ worker [cpp-qualify]'},
    }))
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'push')
    monkeypatch.setenv('GITHUB_EVENT_PATH', str(event))
    assert release.identity('publish') == ('a'*40, 'b'*64)


@pytest.mark.parametrize('payload', [
    {'ref': 'refs/heads/main', 'head_commit': {'message': 'ordinary main push'}},
    {'ref': 'refs/heads/main', 'head_commit': None},
    {},
])
def test_unmarked_or_incomplete_push_release_identity_rejected(
    trusted, monkeypatch, tmp_path, payload
):
    event = tmp_path / 'event.json'
    event.write_text(json.dumps(payload))
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'push')
    monkeypatch.setenv('GITHUB_EVENT_PATH', str(event))
    with pytest.raises(ValueError, match='identity'):
        release.identity('publish')


def test_push_release_identity_rejects_missing_or_malformed_event(
    trusted, monkeypatch, tmp_path
):
    monkeypatch.setenv('GITHUB_EVENT_NAME', 'push')
    monkeypatch.delenv('GITHUB_EVENT_PATH', raising=False)
    with pytest.raises(ValueError, match='identity'):
        release.identity('publish')
    event = tmp_path / 'event.json'
    event.write_text('{')
    monkeypatch.setenv('GITHUB_EVENT_PATH', str(event))
    with pytest.raises(ValueError, match='identity'):
        release.identity('publish')


@pytest.mark.parametrize('version',[1,2,3,4])
def test_legacy_handoff_cannot_publish_from_new_controller(trusted, tmp_path,version):
    (tmp_path / 'handoff.json').write_text(json.dumps({'source_sha':'a'*40,'schema':'nico.qualified-image-handoff.v'+str(version)}))
    with pytest.raises(ValueError, match='source_mismatch'):
        release.publish(tmp_path, 'unused', tmp_path/'out', command=lambda *a,**k: pytest.fail('Docker reached'))


def test_release_workflow_separates_collection_from_write_authority():
    path = Path(__file__).parents[1] / '.github/workflows/cpp-full-project-release.yml'
    workflow = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
    assert set(workflow['on']) == {'workflow_dispatch', 'push'}
    assert workflow['on']['push']['branches'] == ['main']
    jobs = workflow['jobs']
    assert '[cpp-qualify]' in jobs['qualify-image']['if']
    assert '[cpp-qualify]' in jobs['publish-image']['if']
    assert workflow['permissions'] == {'contents':'read'}
    assert 'permissions' not in jobs['qualify-image']
    assert jobs['publish-image']['permissions']['packages'] == 'write'
    assert jobs['verify-image']['permissions']['packages'] == 'read'
    runs = '\n'.join(s.get('run','') for s in jobs['qualify-image']['steps'])
    assert '--accept-completed-collection' in runs
    assert 'qualify_cppcheck_worker_control --image "$(cat full-project-image-id.txt)"' in runs
    assert 'docker/assessment-full-project-fuzz.Dockerfile' in runs
    assert 'cpp_full_project_handoff import' in runs
    assert 'needs.qualify-image.outputs.handoff_sha256' in jobs['publish-image']['env']['NICO_IMAGE_HANDOFF_SHA256']
    assert 'full-project-image-handoff-${{ github.sha }}-${{ github.run_id }}-${{ github.run_attempt }}' in path.read_text()

# The archive fixture is inert; native collection validation above uses actual
# retained producer outputs and is independently tested against tampering.
from tests.test_cpp_worker_image_promotion import package, publish


@pytest.mark.parametrize('corrupt', [False, True])
@pytest.mark.parametrize('version',[3,4,5])
def test_v3_promotion_requires_reconstructed_collection_before_docker(package, tmp_path, monkeypatch, corrupt,version):
    directory, _, recipe, image = package
    manifest_path = directory / 'handoff.json'
    manifest = json.loads(manifest_path.read_bytes())
    manifest.update(schema='nico.qualified-image-handoff.v'+str(version), full_project_collection_sha256='c'*64)
    manifest_path.write_bytes(handoff._canonical(manifest))
    checked = []
    def revalidate(root, *, source_sha, image):
        assert root == directory / 'collection'
        assert source_sha == 'a'*40 and image == package[3]
        checked.append(True)
        return 'e'*64 if corrupt else 'c'*64
    monkeypatch.setattr(handoff, 'validate_collection', revalidate)
    anchored = (directory, hashlib.sha256(manifest_path.read_bytes()).hexdigest(), recipe, image)
    if corrupt:
        with pytest.raises(ValueError, match='qualification_mismatch'):
            publish(anchored, tmp_path)
        assert not (tmp_path/'promotion').exists()
    else:
        result, calls = publish(anchored, tmp_path)
        assert result['full_project_collection_sha256'] == 'c'*64
        assert result['image_manifest'].endswith('@sha256:'+'d'*64)
        assert result['production_qualified'] is False
        assert calls
    assert checked == [True]


def test_current_collection_workflow_and_cli_require_the_same_explicit_policy():
    for path in ('.github/workflows/cpp-full-project-integration.yml','.github/workflows/cpp-full-project-release.yml'):
        workflow=yaml.safe_load(Path(path).read_bytes())
        commands=[s.get('run','') for j in workflow['jobs'].values() for s in j['steps']]
        baseline=[c for c in commands if 'scripts.qualify_cpp_project_configuration ' in c
            and '--baseline-execution-contract' in c]
        assert len(baseline)==1
        assert '--collect-completed-compiler-failures' in baseline[0]
        assert '--accept-completed-collection' in baseline[0] and '--materialize-generated-inputs' in baseline[0]

from tests.test_cpp_worker_image_release import receipt


@pytest.mark.parametrize('fault', [None, 'cached', 'pull', 'config', 'manifest', 'source'])
def test_new_controller_clean_authenticated_retrieval_boundaries(trusted, receipt, tmp_path, monkeypatch, fault):
    monkeypatch.setenv('GITHUB_JOB', 'verify-image')
    monkeypatch.setenv('NICO_IMAGE_PULL_TOKEN', 'owned-inert-pull-token')
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    monkeypatch.delenv('NICO_IMAGE_PUBLICATION_TOKEN', raising=False)
    if fault in {'manifest', 'source'}:
        value = receipt[1].copy()
        if fault == 'manifest': value['image_manifest'] = 'ghcr.io/foreign/image@sha256:'+'d'*64
        else: value['source_sha'] = 'e'*40
        receipt[0].write_text(json.dumps(value))
    calls = []
    def command(argv, **kwargs):
        assert 'NICO_IMAGE_PULL_TOKEN' not in release.os.environ
        assert 'owned-inert-pull-token' not in ' '.join(argv)
        calls.append(argv)
        if 'ls' in argv and fault == 'cached': return b'sha256:cached\n'
        if 'login' in argv: assert kwargs['input_bytes'] == b'owned-inert-pull-token\n'
        if 'pull' in argv:
            assert argv[-1] == receipt[1]['image_manifest']
            if fault == 'pull': raise ValueError('secret-bearing remote failure')
        if 'inspect' in argv:
            return json.dumps([{'Id': 'sha256:'+'f'*64 if fault == 'config' else receipt[1]['image_config_id'],
                'Os':'linux','Architecture':'amd64'}]).encode()
        return b''
    if fault:
        with pytest.raises(ValueError):
            release.verify(receipt[0], tmp_path/'result', command=command, registry_probe=lambda:403)
        if fault in {'manifest','source'}:
            assert calls == []
            return
        result = json.loads((tmp_path/'result/verification.json').read_text())
        assert result['image_pull_verified'] is False
        assert result['failure_stage'] == {'cached':'inventory','pull':'pull','config':'inspect'}[fault]
    else:
        result = release.verify(receipt[0], tmp_path/'result', command=command, registry_probe=lambda:403)
        assert result['state'] == 'published_and_retrieved' and result['image_pull_verified'] is True
        assert result['registry_access_mode'] == 'actions_package_token'
        assert result['anonymous_token_http_status'] == 403
        assert result['source_sha'] == result['controller_source_sha'] == 'a'*40
    assert result['anonymous_pull_verified'] is False and result['production_qualified'] is False
    assert 'owned-inert-pull-token' not in json.dumps(result) and 'secret-bearing' not in json.dumps(result)
    assert not list((tmp_path/'result').glob('private-*'))
