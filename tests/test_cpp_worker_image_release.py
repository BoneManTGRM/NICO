"""Owned release-controller controls; no Docker or registry access."""
import json
from pathlib import Path

import pytest

from scripts import cpp_worker_image_release as release


@pytest.fixture
def trusted(monkeypatch):
    values = {'GITHUB_REPOSITORY': release.REPOSITORY, 'GITHUB_REPOSITORY_ID': '1282576027',
        'GITHUB_EVENT_NAME': 'push', 'GITHUB_REF': release.BRANCH,
        'GITHUB_WORKFLOW_REF': release.WORKFLOW, 'GITHUB_WORKFLOW_SHA': 'a' * 40,
        'GITHUB_SHA': 'a' * 40, 'RUNNER_ENVIRONMENT': 'github-hosted',
        'GITHUB_JOB': 'verify-image', 'GITHUB_RUN_ATTEMPT': '1',
        'NICO_IMAGE_HANDOFF_SHA256': 'b' * 64}
    for key, value in values.items(): monkeypatch.setenv(key, value)
    monkeypatch.delenv('GITHUB_TOKEN', raising=False)
    monkeypatch.delenv('NICO_IMAGE_PUBLICATION_TOKEN', raising=False)
    monkeypatch.delenv('NICO_IMAGE_PULL_TOKEN', raising=False)
    monkeypatch.delenv('NICO_IMAGE_QUALIFIED_SOURCE_SHA', raising=False)


@pytest.fixture
def receipt(tmp_path):
    value = {'schema': 'nico.image-publication.v1', 'source_sha': 'a' * 40,
        'handoff_sha256': 'b' * 64, 'state': 'published_but_unverified',
        'registry_published': True, 'anonymous_pull_verified': False, 'production_qualified': False,
        'destination_tag': release.DESTINATION + ':handoff-' + 'b' * 64,
        'image_config_id': 'sha256:' + 'c' * 64,
        'image_manifest': release.DESTINATION + '@sha256:' + 'd' * 64}
    path = tmp_path / 'publication.json'
    path.write_text(json.dumps(value))
    return path, value


@pytest.mark.parametrize('key,value', [
    ('GITHUB_EVENT_NAME', 'pull_request'), ('GITHUB_EVENT_NAME', 'workflow_dispatch'),
    ('GITHUB_REPOSITORY', 'foreign/NICO'), ('GITHUB_REPOSITORY_ID', '9'),
    ('GITHUB_REF', 'refs/heads/other'), ('GITHUB_WORKFLOW_SHA', 'e' * 40),
    ('GITHUB_WORKFLOW_REF', 'foreign/workflow'), ('GITHUB_RUN_ATTEMPT', '0'),
    ('GITHUB_JOB', 'publish-image'), ('RUNNER_ENVIRONMENT', 'self-hosted'),
    ('NICO_IMAGE_HANDOFF_SHA256', ''), ('GITHUB_SHA', 'main'),
])
def test_untrusted_execution_context_never_reaches_docker(trusted, receipt, tmp_path, monkeypatch, key, value):
    monkeypatch.setenv(key, value)
    with pytest.raises(ValueError, match='identity'):
        release.verify(receipt[0], tmp_path / 'result', command=lambda *a, **k: pytest.fail('Docker reached'))


@pytest.mark.parametrize('key,value', [
    ('source_sha', 'e' * 40), ('handoff_sha256', 'e' * 64),
    ('state', 'push_unknown'), ('registry_published', None),
    ('anonymous_pull_verified', True), ('production_qualified', True),
    ('destination_tag', 'ghcr.io/foreign/image:latest'),
    ('image_manifest', 'ghcr.io/foreign/image@sha256:' + 'd' * 64),
])
def test_wrong_or_incomplete_publication_is_rejected(trusted, receipt, tmp_path, key, value):
    data = dict(receipt[1], **{key: value}); receipt[0].write_text(json.dumps(data))
    with pytest.raises(ValueError):
        release.verify(receipt[0], tmp_path / 'result', command=lambda *a, **k: pytest.fail('Docker reached'))


def test_cached_daemon_cannot_pass_as_fresh_anonymous_retrieval(trusted, receipt, tmp_path):
    calls = []
    def command(argv, **kwargs): calls.append(argv); return b'sha256:cached\n'
    with pytest.raises(ValueError, match='clean_daemon'):
        release.verify(receipt[0], tmp_path / 'result', command=command)
    assert len(calls) == 1 and 'pull' not in calls[0]
    assert json.loads((tmp_path / 'result/verification.json').read_text())['anonymous_pull_verified'] is False


def test_verification_can_retry_after_visibility_change_without_republishing(trusted, monkeypatch):
    monkeypatch.setenv('GITHUB_RUN_ATTEMPT', '2')
    assert release.identity('verify') == ('a' * 40, 'b' * 64)
    monkeypatch.setenv('GITHUB_JOB', 'publish-image')
    with pytest.raises(ValueError, match='identity'):
        release.identity('publish')


@pytest.mark.parametrize('key', ['NICO_IMAGE_PUBLICATION_TOKEN', 'GITHUB_TOKEN'])
def test_verification_refuses_exported_credentials(trusted, receipt, tmp_path, monkeypatch, key):
    monkeypatch.setenv(key, 'owned-inert-token')
    with pytest.raises(ValueError, match='anonymous_environment'):
        release.verify(receipt[0], tmp_path / 'result', command=lambda *a, **k: pytest.fail('Docker reached'))


@pytest.mark.parametrize('pull_failure', [False, True])
def test_separate_anonymous_retrieval_preserves_limited_qualification(trusted, receipt, tmp_path, pull_failure):
    calls = []
    def command(argv, **kwargs):
        calls.append((argv, kwargs))
        assert 'input_bytes' not in kwargs
        if 'pull' in argv and pull_failure: raise ValueError('private package or network unavailable')
        if 'inspect' in argv:
            return json.dumps([{'Id': receipt[1]['image_config_id'], 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
        return b''
    if pull_failure:
        with pytest.raises(ValueError): release.verify(receipt[0], tmp_path / 'result', command=command)
        result = json.loads((tmp_path / 'result/verification.json').read_text())
        assert result['anonymous_pull_verified'] is False
    else:
        result = release.verify(receipt[0], tmp_path / 'result', command=command)
        assert result['anonymous_pull_verified'] is True
    assert result['production_qualified'] is False
    assert not any('login' in argv or 'build' in argv or 'run' in argv for argv, _ in calls)
    assert not list((tmp_path / 'result').glob('private-*'))


def test_publish_rejects_other_source_before_using_credential(trusted, tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_JOB', 'publish-image')
    (tmp_path / 'handoff.json').write_text(json.dumps({'source_sha': 'e' * 40}))
    with pytest.raises(ValueError, match='source_mismatch'):
        release.publish(tmp_path, tmp_path / 'recipe', tmp_path / 'result',
            command=lambda *a, **k: pytest.fail('Docker reached'))


def test_publication_uses_step_credential_and_independent_anchor(trusted, tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_JOB', 'publish-image')
    monkeypatch.setenv('NICO_IMAGE_PUBLICATION_TOKEN', 'owned-inert-token')
    (tmp_path / 'handoff.json').write_text(json.dumps({'source_sha': 'a' * 40}))
    def publisher(directory, anchor, recipe, output, *, registry_token, command):
        assert directory == tmp_path and anchor == 'b' * 64
        assert registry_token == 'owned-inert-token'
        assert 'NICO_IMAGE_PUBLICATION_TOKEN' not in release.os.environ
        return {'state': 'published_but_unverified'}
    monkeypatch.setattr(release, 'publish_image', publisher)
    assert release.publish(tmp_path, tmp_path / 'recipe', tmp_path / 'result')['state'] == 'published_but_unverified'


def test_cli_does_not_disclose_credential_bearing_failures(trusted, monkeypatch, capsys):
    monkeypatch.setenv('NICO_IMAGE_RELEASE_MODE', 'publish')
    def fail(*args, **kwargs): raise ValueError('owned-inert-token')
    monkeypatch.setattr(release, 'publish', fail)
    assert release.main() == 1
    output = capsys.readouterr().out
    assert 'owned-inert-token' not in output and json.loads(output)['production_qualified'] is False


def test_authenticated_retrieval_does_not_claim_anonymous_or_rebind_image_source(trusted, receipt, tmp_path, monkeypatch):
    monkeypatch.setenv('GITHUB_SHA', 'e' * 40)
    monkeypatch.setenv('GITHUB_WORKFLOW_SHA', 'e' * 40)
    monkeypatch.setenv('GITHUB_WORKFLOW_REF', release.RETRIEVAL_WORKFLOW)
    monkeypatch.setenv('NICO_IMAGE_QUALIFIED_SOURCE_SHA', 'a' * 40)
    monkeypatch.setenv('NICO_IMAGE_PULL_TOKEN', 'owned-inert-pull-token')
    configs = []
    def command(argv, **kwargs):
        assert 'NICO_IMAGE_PULL_TOKEN' not in release.os.environ
        assert 'owned-inert-pull-token' not in ' '.join(argv)
        if 'login' in argv:
            assert kwargs['input_bytes'] == b'owned-inert-pull-token\n'
            configs.append(Path(argv[2]))
        if 'inspect' in argv:
            return json.dumps([{'Id': receipt[1]['image_config_id'], 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
        return b''
    result = release.verify(receipt[0], tmp_path / 'result', command=command, registry_probe=lambda: 403)
    assert result['image_pull_verified'] is True and result['anonymous_pull_verified'] is False
    assert result['registry_access_mode'] == 'actions_package_token' and result['anonymous_token_http_status'] == 403
    assert result['source_sha'] == 'a' * 40 and result['controller_source_sha'] == 'e' * 40
    assert result['production_qualified'] is False and all(not path.exists() for path in configs)
    assert 'owned-inert-pull-token' not in (tmp_path / 'result/verification.json').read_text()


def test_failure_stage_and_safe_code_are_retained_without_raw_error(trusted, receipt, tmp_path):
    def command(argv, **kwargs):
        if 'pull' in argv: raise ValueError('secret-bearing remote output')
        return b''
    with pytest.raises(ValueError): release.verify(receipt[0], tmp_path / 'result', command=command)
    result = json.loads((tmp_path / 'result/verification.json').read_text())
    assert result['failure_stage'] == 'pull' and result['error_code'] == 'image_release_failed'
    assert result['image_pull_verified'] is False and 'secret-bearing' not in json.dumps(result)


def test_retrieval_workflow_cannot_publish_and_ordinary_changes_do_not_republish():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/cpp-worker-image-retrieval.yml').read_text())
    job = workflow['jobs']['verify-image']
    assert job['permissions'] == {'contents': 'read', 'packages': 'read'}
    assert job['timeout-minutes'] == 5 and set(workflow['jobs']) == {'verify-image'}
    publication = json.loads(Path('scripts/cpp_worker_published_image.json').read_text())
    assert publication['source_sha'] == job['env']['NICO_IMAGE_QUALIFIED_SOURCE_SHA']
    assert publication['handoff_sha256'] == job['env']['NICO_IMAGE_HANDOFF_SHA256']
    assert all('NICO_IMAGE_PUBLICATION_TOKEN' not in step.get('env', {}) for step in job['steps'])
    qualification = yaml.safe_load(Path('.github/workflows/cpp-worker-boundary-qualification.yml').read_text())
    assert "contains(github.event.head_commit.message, '[publish-worker-image]')" in qualification['jobs']['publish-image']['if']


def test_anonymous_probe_has_no_credentials_redirects_or_retained_token(monkeypatch):
    class Response:
        status_code = 403
        closed = False
        def close(self): self.closed = True
    response = Response()
    class Session:
        trust_env = True
        def get(self, url, **kwargs):
            assert self.trust_env is False and url == 'https://ghcr.io/token'
            assert kwargs['allow_redirects'] is False and kwargs['stream'] is True
            assert kwargs['timeout'] == (3, 5)
            assert 'headers' not in kwargs and 'auth' not in kwargs
            return response
        def close(self): pass
    monkeypatch.setattr(release.requests, 'Session', Session)
    assert release.anonymous_registry_status() == 403 and response.closed


def test_image_release_is_bound_to_current_pr1641_branch():
    expected = 'refs/heads/feat/cpp-full-project-capacity'
    assert release.BRANCH == expected
    for name in ('.github/workflows/cpp-worker-boundary-qualification.yml',
                 '.github/workflows/cpp-worker-image-retrieval.yml'):
        text = Path(name).read_text()
        assert 'feat/cpp-full-project-capacity' in text
        assert 'feat/large-repository-cpp-comprehensive' not in text


def test_publish_verification_uses_fresh_daemon_before_anonymous_pull():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/cpp-worker-boundary-qualification.yml').read_text())
    job = workflow['jobs']['verify-image']
    step = next(item for item in job['steps']
                if item.get('name') == 'Verify anonymous retrieval on a separate clean daemon')
    script = step['run']
    assert 'systemctl stop docker.service docker.socket' in script
    assert 'dockerd' in script and '--data-root' in script and '--exec-root' in script
    assert 'DockerRootDir' in script
    assert 'test "$actual_root" = "$retrieval_root/data"' in script
    assert 'NICO_IMAGE_PULL_TOKEN' not in step.get('env', {})
    assert step['env'] == {'NICO_IMAGE_RELEASE_MODE': 'verify'}
