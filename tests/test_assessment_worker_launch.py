"""The production launcher must keep the consumer's narrow authority and bounds."""
import hashlib
import json
import pickle
from pathlib import Path
from urllib.parse import urlsplit

import pytest


def environment(monkeypatch):
    values = {
        'GITHUB_EVENT_NAME': 'workflow_dispatch', 'GITHUB_REF': 'refs/heads/main',
        'GITHUB_SHA': 'c' * 40, 'GITHUB_WORKFLOW_SHA': 'c' * 40,
        'GITHUB_REPOSITORY': 'BoneManTGRM/NICO', 'GITHUB_REPOSITORY_ID': '123456',
        'GITHUB_WORKFLOW_REF': 'BoneManTGRM/NICO/.github/workflows/assessment-worker.yml@refs/heads/main',
        'RUNNER_ENVIRONMENT': 'github-hosted',
        'ACTIONS_ID_TOKEN_REQUEST_URL': 'https://pipelines.actions.githubusercontent.com/job/idtoken?api-version=2.0',
        'ACTIONS_ID_TOKEN_REQUEST_TOKEN': 'synthetic-request-credential',
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    return values


class Response:
    def __init__(self, raw, status=200):
        self.raw, self.status_code, self.closed = raw, status, False
    def iter_content(self, chunk_size):
        yield self.raw
    def close(self):
        self.closed = True


def test_real_oidc_provider_is_picklable_job_scoped_and_never_redirects(monkeypatch):
    from nico import assessment_worker_launch as launch
    environment(monkeypatch)
    seen = []
    response = Response(b'{"value":"synthetic-scoped-jwt"}')
    class Session:
        trust_env = True
        def get(self, url, **kwargs):
            assert self.trust_env is False
            seen.append((url, kwargs))
            return response
        def close(self): pass
    monkeypatch.setattr(launch.requests, 'Session', Session)
    job = 'workerjob_' + 'a' * 64
    provider = pickle.loads(pickle.dumps(launch.ActionsWorkerToken(job)))
    assert provider() == 'synthetic-scoped-jwt'
    assert 'audience=https%3A%2F%2Fapp.nicoaudit.com%2Fassessment-worker%2F' + job in seen[0][0]
    assert seen[0][1]['allow_redirects'] is False
    assert seen[0][1]['headers']['Authorization'] == 'Bearer synthetic-request-credential'
    assert response.closed
    assert 'credential' not in repr(provider)


@pytest.mark.parametrize('key,value', [
    ('GITHUB_REF', 'refs/heads/feature'), ('GITHUB_EVENT_NAME', 'pull_request'),
    ('GITHUB_WORKFLOW_SHA', 'd' * 40), ('RUNNER_ENVIRONMENT', 'self-hosted'),
    ('GITHUB_WORKFLOW_REF', 'BoneManTGRM/NICO/.github/workflows/other.yml@refs/heads/main'),
    ('ACTIONS_ID_TOKEN_REQUEST_URL', 'https://untrusted.invalid/token'),
    ('ACTIONS_ID_TOKEN_REQUEST_URL', 'https://pipelines.actions.githubusercontent.com@untrusted.invalid/token'),
    ('ACTIONS_ID_TOKEN_REQUEST_URL', 'https://pipelines.actions.githubusercontent.com/token?audience=other'),
])
def test_wrong_workflow_or_oidc_destination_is_rejected_before_network(monkeypatch, key, value):
    from nico import assessment_worker_launch as launch
    environment(monkeypatch)
    monkeypatch.setenv(key, value)
    monkeypatch.setattr(launch.requests, 'Session', lambda: pytest.fail('network reached'))
    with pytest.raises(ValueError):
        launch.ActionsWorkerToken('workerjob_' + 'a' * 64)()


@pytest.mark.parametrize('raw,status', [
    (b'{"value":"secret"}', 302), (b'{"value":"a","value":"b"}', 200),
    (b'{"value":"two tokens"}', 200), (b'x' * 65537, 200),
])
def test_oidc_refusal_and_ambiguous_response_fail_closed(monkeypatch, raw, status):
    from nico import assessment_worker_launch as launch
    environment(monkeypatch)
    response = Response(raw, status)
    class Session:
        def get(self, *args, **kwargs): return response
        def close(self): pass
    monkeypatch.setattr(launch.requests, 'Session', Session)
    with pytest.raises(ValueError):
        launch.ActionsWorkerToken('workerjob_' + 'a' * 64)()
    assert response.closed


@pytest.mark.parametrize('path', ['src/main.cpp', 'src/what?#%.cpp'])
def test_source_provisioning_materializes_original_bytes_and_exact_population(tmp_path, path):
    from nico.assessment_worker_source import acquire_public_github_inputs
    tmp_path.chmod(0o700)
    source = b'int main() { return 0; }\r\n'
    revision = 'a' * 40
    digest = hashlib.sha256(source).hexdigest()
    blob = hashlib.sha1(b'blob ' + str(len(source)).encode() + b'\0' + source, usedforsecurity=False).hexdigest()
    calls = []
    def download(url, destination, *, limit, checkpoint, deadline):
        checkpoint(); calls.append(url)
        if '/git/commits/' in url:
            raw = json.dumps({'sha': revision, 'tree': {'sha': 'b' * 40}}).encode()
        elif '/git/trees/' in url:
            raw = json.dumps({'sha': 'b' * 40, 'truncated': False, 'tree': [
                {'path': path, 'mode': '100644', 'type': 'blob', 'sha': blob, 'size': len(source)},
            ]}).encode()
        else:
            raw = source
        assert len(raw) <= limit
        destination.write_bytes(raw)
    record = {'identity': {'repository_id': 'https://github.com/owned/control', 'revision': revision},
        'contract': {'targets': {path: digest}}, 'deadline_epoch': __import__('time').time() + 60,
        'source_access': {'mode': 'anonymous_public', 'credential_used': False}}
    root, evidence = acquire_public_github_inputs(record, tmp_path, lambda: None, download=download)
    assert (root / path).read_bytes() == source
    assert evidence['source_bytes'] == len(source) and evidence['materialized_count'] == 1
    assert evidence['commit_sha'] == revision and evidence['tree_sha'] == 'b' * 40
    assert evidence['assessed_code_executed'] is False
    from urllib.parse import quote
    assert calls[-1] == 'https://raw.githubusercontent.com/owned/control/' + revision + '/' + quote(path, safe='/')


@pytest.mark.parametrize('repository', [
    'https://user:secret@github.com/owned/control', 'https://github.com/owned/control?ref=main',
    'https://github.com/owned/control/../other', 'file:///tmp/source', 'https://gitlab.com/owned/control',
])
def test_source_rejects_unsupported_or_credentialed_repository_before_network(tmp_path, repository):
    from nico.assessment_worker_source import acquire_public_github_inputs
    record = {'identity': {'repository_id': repository, 'revision': 'a' * 40},
        'contract': {'targets': {'main.cpp': 'b' * 64}}, 'deadline_epoch': __import__('time').time() + 60,
        'source_access': {'mode': 'anonymous_public', 'credential_used': False}}
    with pytest.raises(ValueError):
        acquire_public_github_inputs(record, tmp_path, lambda: None,
            download=lambda *args, **kwargs: pytest.fail('network reached'))


def test_image_provisioning_binds_manifest_reference_to_config_id(tmp_path):
    from nico.assessment_worker_launch import provision_image
    image = 'sha256:' + 'd' * 64
    reference = 'ghcr.io/bonemantgrm/nico/assessment-cppcheck@sha256:' + 'e' * 64
    calls = []
    def command(args, **kwargs):
        calls.append(args)
        if 'inspect' in args:
            return json.dumps([{'Id': image, 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
        return b''
    provision_image(image, reference, 'BoneManTGRM/NICO', tmp_path, lambda: None, command=command)
    assert 'pull' in calls[0] and reference in calls[0]
    assert 'inspect' in calls[1] and reference in calls[1]
    with pytest.raises(ValueError, match='identity'):
        provision_image('sha256:' + 'f' * 64, reference, 'BoneManTGRM/NICO', tmp_path, lambda: None, command=command)


@pytest.mark.parametrize('failure', [None, 'login', 'pull', 'inspect'])
def test_private_image_credential_and_config_never_survive_provisioning(tmp_path, failure):
    from nico.assessment_worker_launch import provision_image
    image = 'sha256:' + 'd' * 64
    reference = 'ghcr.io/bonemantgrm/nico/assessment-cppcheck@sha256:' + 'e' * 64
    calls = []; configurations = []
    def command(args, **kwargs):
        calls.append((args, kwargs))
        config = Path(args[2]); configurations.append(config)
        assert config.is_dir() and config.stat().st_mode & 0o777 == 0o700
        assert 'owned-inert-pull-token' not in ' '.join(args)
        if 'login' in args:
            assert kwargs['input_bytes'] == b'owned-inert-pull-token\n'
            (config / 'config.json').write_text('owned-inert-pull-token')
        if failure in args: raise ValueError('worker_container_control_failed')
        if 'inspect' in args:
            return json.dumps([{'Id': image, 'Os': 'linux', 'Architecture': 'amd64'}]).encode()
        return b''
    if failure:
        with pytest.raises(ValueError):
            provision_image(image, reference, 'BoneManTGRM/NICO', tmp_path, lambda: None,
                command=command, registry_token='owned-inert-pull-token')
    else:
        assert provision_image(image, reference, 'BoneManTGRM/NICO', tmp_path, lambda: None,
            command=command, registry_token='owned-inert-pull-token')['image_config_id'] == image
    assert calls and all(not path.exists() for path in configurations)
    assert not any(path.is_file() for path in tmp_path.rglob('*'))


@pytest.mark.parametrize('reference', [
    'ghcr.io/bonemantgrm/nico/assessment-cppcheck:latest',
    'ghcr.io/other/repo@sha256:' + 'd' * 64,
    'registry.invalid/assessment@sha256:' + 'd' * 64,
])
def test_unpinned_or_foreign_image_is_rejected_before_pull(tmp_path, reference):
    from nico.assessment_worker_launch import provision_image
    with pytest.raises(ValueError):
        provision_image('sha256:' + 'd' * 64, reference, 'BoneManTGRM/NICO', tmp_path,
            lambda: None, command=lambda *a, **kw: pytest.fail('pull reached'))


def test_dedicated_workflow_accepts_only_job_identity_and_keeps_narrow_permissions():
    import yaml
    workflow = yaml.safe_load(Path('.github/workflows/assessment-worker.yml').read_text())
    trigger = workflow.get('on', workflow.get(True))
    assert set(trigger) == {'workflow_dispatch'}
    assert set(trigger['workflow_dispatch']['inputs']) == {'job_id'}
    assert workflow['permissions'] == {'contents': 'read', 'id-token': 'write'}
    assert workflow['jobs']['consume']['timeout-minutes'] == 45
    assert 'environment' not in workflow['jobs']['consume']
    for step in workflow['jobs']['consume']['steps']:
        assert '${{ inputs.' not in step.get('run', '')


@pytest.mark.parametrize('change', ['revision', 'tree', 'truncated', 'link', 'submodule', 'missing',
    'duplicate', 'oversized', 'digest', 'blob', 'lfs'])
def test_source_substitution_and_partial_population_are_never_published(tmp_path, change):
    from nico.assessment_worker_source import acquire_public_github_inputs, MAX_BYTES
    import time
    tmp_path.chmod(0o700)
    raw = b'int main() { return 0; }\n'
    if change == 'lfs': raw = b'version https://git-lfs.github.com/spec/v1\n'
    revision = 'a' * 40
    entry = {'path': 'main.cpp', 'mode': '100644', 'type': 'blob',
        'sha': hashlib.sha1(b'blob ' + str(len(raw)).encode() + b'\0' + raw, usedforsecurity=False).hexdigest(),
        'size': len(raw)}
    if change == 'link': entry['mode'] = '120000'
    if change == 'submodule': entry.update(mode='160000', type='commit')
    if change == 'oversized': entry['size'] = MAX_BYTES + 1
    if change == 'blob': entry['sha'] = 'f' * 40
    requested = []
    def download(url, destination, **kwargs):
        requested.append(url)
        if '/commits/' in url:
            value = {'sha': 'c' * 40 if change == 'revision' else revision, 'tree': {'sha': 'b' * 40}}
        elif '/trees/' in url:
            value = {'sha': 'c' * 40 if change == 'tree' else 'b' * 40, 'truncated': change == 'truncated',
                'tree': [] if change == 'missing' else [entry, entry] if change == 'duplicate' else [entry]}
        else:
            destination.write_bytes(raw)
            return
        destination.write_text(json.dumps(value))
    record = {'identity': {'repository_id': 'https://github.com/owned/control', 'revision': revision},
        'contract': {'targets': {'main.cpp': 'f' * 64 if change == 'digest' else hashlib.sha256(raw).hexdigest()}},
        'deadline_epoch': time.time() + 60, 'source_access': {'mode': 'anonymous_public', 'credential_used': False}}
    with pytest.raises(ValueError):
        acquire_public_github_inputs(record, tmp_path, lambda: None, download=download)
    assert not (tmp_path / 'source').exists()
    assert not list(tmp_path.glob('.nico-source-*'))
    if change not in {'digest', 'blob', 'lfs'}:
        assert all(urlsplit(url).scheme == 'https' and urlsplit(url).netloc == 'api.github.com'
                   for url in requested)


@pytest.mark.parametrize('url', [
    'https://untrusted.invalid/raw.githubusercontent.com/file',
    'https://raw.githubusercontent.com.untrusted.invalid/file',
    'https://raw.githubusercontent.com@untrusted.invalid/file',
    'http://raw.githubusercontent.com/owned/control/file',
])
def test_source_host_lookalikes_are_rejected_before_a_download_starts(monkeypatch, tmp_path, url):
    from nico import assessment_worker_source as source
    import time
    monkeypatch.setattr(source.multiprocessing, 'get_context', lambda *_: pytest.fail('download process reached'))
    with pytest.raises(ValueError, match='worker_source_request_invalid'):
        source.download_public(url, tmp_path / 'blob', limit=64,
            checkpoint=lambda: pytest.fail('checkpoint reached'), deadline=time.monotonic() + 5)
    assert not (tmp_path / 'blob').exists()


def blocked_download(url, destination, limit):
    import os
    import time
    Path(str(destination) + '.pid').write_text(str(os.getpid()))
    Path(destination).write_bytes(b'incomplete')
    time.sleep(100)


def test_blocked_source_download_is_killed_on_lease_loss_and_partial_bytes_removed(monkeypatch, tmp_path):
    from nico import assessment_worker_source as source
    import os
    import time
    monkeypatch.setattr(source, '_download_child', blocked_download)
    destination = tmp_path / 'blob'
    marker = Path(str(destination) + '.pid')
    def checkpoint():
        if marker.exists(): raise ValueError('worker_local_lease_expired')
    with pytest.raises(ValueError, match='lease'):
        source.download_public('https://raw.githubusercontent.com/owned/control/sha/file', destination,
            limit=64, checkpoint=checkpoint, deadline=time.monotonic() + 5)
    assert marker.exists() and not destination.exists()
    with pytest.raises(ProcessLookupError): os.kill(int(marker.read_text()), 0)


def test_image_provisioning_lease_loss_stops_before_source_acquisition(monkeypatch, tmp_path):
    from nico import assessment_worker_launch as launch
    from nico import assessment_worker_source as source
    environment(monkeypatch)
    sequence = []
    def consume(transport, *, acquire):
        sequence.append('claimed')
        def checkpoint(): raise ValueError('worker_local_lease_expired')
        return acquire({'contract': {'image_digest': 'sha256:' + 'd' * 64}}, tmp_path, checkpoint)
    def provision(*args):
        sequence.append('provision')
        args[-1]()
    monkeypatch.setattr(launch, 'consume_one_job', consume)
    monkeypatch.setattr(launch, 'provision_image', provision)
    monkeypatch.setattr(source, 'acquire_public_github_inputs', lambda *args: pytest.fail('source reached'))
    with pytest.raises(ValueError, match='lease'):
        launch.run('workerjob_' + 'a' * 64, 'https://backend.example.invalid',
            'ghcr.io/bonemantgrm/nico/assessment-cppcheck@sha256:' + 'e' * 64)
    assert sequence == ['claimed', 'provision']


def test_production_provisioning_is_bound_to_retained_receipt_not_discarded():
    from dataclasses import asdict
    from nico.assessment_worker_consumer import _receipt
    from nico.assessment_worker_receipts import validate_receipt
    from nico.assessment_worker_jobs import _digest
    from scripts.worker_protocol_fixture import contract, identity, receipt
    plan = contract(); selected = identity(plan); original = receipt()
    job = {'identity': asdict(selected), 'contract': plan, 'lease_id': original['lease_id'],
        'worker_id': original['worker_id']}
    acquisition = {'schema': 'nico.github_https_input_materialization.v1', 'commit_sha': selected.revision,
        'tree_sha': 'b' * 40, 'inputs': plan['targets'], 'population_sha256': _digest(plan['targets']),
        'required_count': len(plan['targets']), 'materialized_count': len(plan['targets']), 'source_bytes': 24,
        'analyzed_count': None, 'authorized': False, 'assessed_code_executed': False,
        'image_manifest': 'ghcr.io/bonemantgrm/nico/assessment-cppcheck@sha256:' + 'e' * 64,
        'image_config_id': plan['image_digest']}
    retained = _receipt(job, {'native': original['native']}, acquisition=acquisition)
    raw, record, _ = validate_receipt(selected, plan, job['lease_id'], job['worker_id'], retained)
    assert json.loads(raw)['provisioning']['image_manifest'] == acquisition['image_manifest']
    assert record['worker_provenance']['provisioning'] == retained['provisioning']
    assert retained['provisioning']['population_sha256'] == _digest(plan['targets'])
    retained['provisioning']['commit_sha'] = 'd' * 40
    with pytest.raises(ValueError, match='provisioning'):
        validate_receipt(selected, plan, job['lease_id'], job['worker_id'], retained)
