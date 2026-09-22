"""Dispatch transport refusal, narrow authority and ambiguous-response tests."""
import json

import pytest
import requests

from nico.assessment_worker_dispatch import _submit, dispatch_existing_job
from scripts.worker_protocol_fixture import identity


class Response:
    def __init__(self, status, value):
        self.status_code, self.value, self.closed = status, value, False
    def iter_content(self, chunk_size): yield json.dumps(self.value).encode()
    def close(self): self.closed = True


def token_response(**changes):
    return {'token': 'synthetic-installation-token', 'permissions': {'actions': 'write', 'metadata': 'read'},
        'repositories': [{'id': 123456, 'full_name': 'BoneManTGRM/NICO'}], **changes}


def test_dispatch_requests_only_one_repository_actions_write_and_one_job(monkeypatch):
    monkeypatch.setenv('NICO_GITHUB_APP_INSTALLATION_ID', '789')
    calls = []
    class Session:
        def post(self, url, **kwargs):
            assert self.trust_env is False
            calls.append((url, kwargs))
            return Response(201, token_response()) if len(calls) == 1 else Response(200, {'workflow_run_id': 1234})
    result = _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session(), signer=lambda: ('signed-app-jwt', None))
    assert result == {'state': 'accepted', 'run_id': 1234}
    assert calls[0][1]['json'] == {'repository_ids': [123456], 'permissions': {'actions': 'write'}}
    assert calls[1][1]['json'] == {'ref': 'main', 'inputs': {'job_id': identity().job_id}}
    assert calls[1][0].endswith('/actions/workflows/assessment-worker.yml/dispatches')
    assert all(call[1]['allow_redirects'] is False for call in calls)


@pytest.mark.parametrize('change', [
    {'permissions': {'actions': 'write', 'contents': 'write'}},
    {'repositories': [{'id': 123456, 'full_name': 'BoneManTGRM/NICO'}, {'id': 987, 'full_name': 'other/repo'}]},
    {'repositories': [{'id': 987, 'full_name': 'BoneManTGRM/NICO'}]},
    {'repositories': [{'id': 123456, 'full_name': 'other/repo'}]}, {'token': ''},
])
def test_broader_or_wrong_installation_token_never_dispatches(monkeypatch, change):
    monkeypatch.setenv('NICO_GITHUB_APP_INSTALLATION_ID', '789')
    seen = []
    class Session:
        def post(self, url, **kwargs):
            seen.append(url)
            return Response(201, token_response(**change))
    assert _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session(),
                   signer=lambda: ('jwt', None))['state'] == 'rejected'
    assert len(seen) == 1


def test_missing_app_authority_never_uses_existing_personal_tokens(monkeypatch):
    monkeypatch.setenv('NICO_GITHUB_APP_INSTALLATION_ID', '789')
    monkeypatch.setenv('NICO_GITHUB_TOKEN', 'must-not-be-used')
    monkeypatch.setenv('GITHUB_TOKEN', 'must-not-be-used-either')
    class Session:
        def post(self, *args, **kwargs): pytest.fail('fallback authentication used')
    assert _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session(),
                   signer=lambda: (None, 'unavailable'))['state'] == 'rejected'


@pytest.mark.parametrize('outcome,state', [(requests.Timeout, 'unknown'), (503, 'unknown'), (302, 'unknown'),
    (403, 'rejected'), (204, 'accepted')])
def test_no_resubmission_after_lost_or_refused_response(monkeypatch, outcome, state):
    monkeypatch.setenv('NICO_GITHUB_APP_INSTALLATION_ID', '789')
    calls = []
    class Session:
        def post(self, url, **kwargs):
            calls.append(url)
            if len(calls) == 1: return Response(201, token_response())
            if outcome is requests.Timeout: raise requests.Timeout('response lost')
            return Response(outcome, {})
    result = _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session(), signer=lambda: ('jwt', None))
    assert result == {'state': state, 'run_id': None}
    assert len(calls) == 2


def test_pending_reservation_is_not_resubmitted_by_repeated_intake():
    from dataclasses import asdict
    job = {'identity': asdict(identity()), 'deadline_epoch': 12345, 'dispatch': {'state': 'pending'}}
    class Jobs:
        def reserve_dispatch(self, *args, **kwargs): return None
        def get(self, *args): return job
    assert dispatch_existing_job(Jobs(), job, 'BoneManTGRM/NICO', '123456',
        submit=lambda *a, **kw: pytest.fail('ambiguous submission repeated')) is job


def test_transport_failure_is_persisted_against_reserved_identity():
    from dataclasses import asdict
    job = {'identity': asdict(identity()), 'deadline_epoch': 12345}
    events = []
    class Jobs:
        def reserve_dispatch(self, *args, **kwargs): events.append('reserved'); return 'a' * 32
        def finish_dispatch(self, selected, nonce, state, **kwargs):
            assert selected == identity() and nonce == 'a' * 32 and kwargs == {'run_id': None}
            events.append(state)
            return {'dispatch': {'state': state}}
    def submit(*args, **kwargs):
        assert events == ['reserved']
        raise requests.Timeout('may have been accepted')
    assert dispatch_existing_job(Jobs(), job, 'BoneManTGRM/NICO', '123456', submit=submit)['dispatch']['state'] == 'unknown'
    assert events == ['reserved', 'unknown']


def test_existing_backend_token_dispatches_only_after_repository_identity_verification(monkeypatch):
    for key in ('NICO_GITHUB_APP_ID', 'NICO_GITHUB_APP_PRIVATE_KEY', 'NICO_GITHUB_APP_INSTALLATION_ID'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('NICO_GITHUB_TOKEN', 'synthetic-existing-server-token')
    calls = []
    class Session:
        def get(self, url, **kwargs):
            calls.append(('get', url, kwargs))
            return Response(200, {'id': 123456, 'full_name': 'BoneManTGRM/NICO'})
        def post(self, url, **kwargs):
            assert len(calls) == 1
            calls.append(('post', url, kwargs))
            return Response(200, {'workflow_run_id': 7654})
    result = _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session())
    assert result == {'state': 'accepted', 'run_id': 7654}
    assert calls[0][1] == 'https://api.github.com/repos/BoneManTGRM/NICO'
    assert calls[1][1].endswith('/actions/workflows/assessment-worker.yml/dispatches')
    assert calls[1][2]['json'] == {'ref': 'main', 'inputs': {'job_id': identity().job_id}}
    assert all(call[2]['allow_redirects'] is False for call in calls)
    assert all(call[2]['headers']['Authorization'] == 'Bearer synthetic-existing-server-token' for call in calls)


@pytest.mark.parametrize('metadata,status', [
    ({'id': 999, 'full_name': 'BoneManTGRM/NICO'}, 200),
    ({'id': 123456, 'full_name': 'other/repo'}, 200),
    ({'id': 123456, 'full_name': 'BoneManTGRM/NICO'}, 302), ({}, 403),
])
def test_existing_token_cannot_dispatch_cross_repository_or_after_identity_refusal(monkeypatch, metadata, status):
    for key in ('NICO_GITHUB_APP_ID', 'NICO_GITHUB_APP_PRIVATE_KEY', 'NICO_GITHUB_APP_INSTALLATION_ID'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('NICO_GITHUB_TOKEN', 'synthetic-existing-server-token')
    calls = []
    class Session:
        def get(self, *args, **kwargs):
            calls.append('identity')
            return Response(status, metadata)
        def post(self, *args, **kwargs): pytest.fail('dispatch reached')
    assert _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session())['state'] == 'rejected'
    assert calls == ['identity']


def test_existing_server_token_mode_is_frozen_before_submission_and_never_claims_downscoping(monkeypatch):
    from dataclasses import asdict
    for key in ('NICO_GITHUB_APP_ID', 'NICO_GITHUB_APP_PRIVATE_KEY', 'NICO_GITHUB_APP_INSTALLATION_ID'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('NICO_GITHUB_TOKEN', 'synthetic-existing-server-token')
    events = []
    class Jobs:
        def reserve_dispatch(self, selected, repository, *, authentication_mode):
            assert authentication_mode == 'server_token'
            events.append(authentication_mode)
            return 'a' * 32
        def finish_dispatch(self, selected, nonce, state, **kwargs): return {'state': state}
    def submit(*args, **kwargs):
        assert events == ['server_token'] and kwargs['mode'] == 'server_token'
        return {'state': 'accepted', 'run_id': 7654}
    assert dispatch_existing_job(Jobs(), {'identity': asdict(identity()), 'deadline_epoch': 12345},
        'BoneManTGRM/NICO', '123456', submit=submit)['state'] == 'accepted'


def test_existing_token_actions_refusal_does_not_change_permissions_or_credentials(monkeypatch):
    for key in ('NICO_GITHUB_APP_ID', 'NICO_GITHUB_APP_PRIVATE_KEY', 'NICO_GITHUB_APP_INSTALLATION_ID'):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv('NICO_GITHUB_TOKEN', 'synthetic-existing-server-token')
    calls = []
    class Session:
        def get(self, url, **kwargs): return Response(200, {'id': 123456, 'full_name': 'BoneManTGRM/NICO'})
        def post(self, url, **kwargs):
            calls.append((url, kwargs))
            return Response(403, {})
    result = _submit(identity().job_id, 'BoneManTGRM/NICO', '123456', session=Session())
    assert result == {'state': 'rejected', 'run_id': None}
    assert len(calls) == 1 and calls[0][1]['json'] == {'ref': 'main', 'inputs': {'job_id': identity().job_id}}
