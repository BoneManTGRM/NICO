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
        def reserve_dispatch(self, *args): return None
        def get(self, *args): return job
    assert dispatch_existing_job(Jobs(), job, 'BoneManTGRM/NICO', '123456',
        submit=lambda *a, **kw: pytest.fail('ambiguous submission repeated')) is job


def test_transport_failure_is_persisted_against_reserved_identity():
    from dataclasses import asdict
    job = {'identity': asdict(identity()), 'deadline_epoch': 12345}
    events = []
    class Jobs:
        def reserve_dispatch(self, *args): events.append('reserved'); return 'a' * 32
        def finish_dispatch(self, selected, nonce, state, **kwargs):
            assert selected == identity() and nonce == 'a' * 32 and kwargs == {'run_id': None}
            events.append(state)
            return {'dispatch': {'state': state}}
    def submit(*args, **kwargs):
        assert events == ['reserved']
        raise requests.Timeout('may have been accepted')
    assert dispatch_existing_job(Jobs(), job, 'BoneManTGRM/NICO', '123456', submit=submit)['dispatch']['state'] == 'unknown'
    assert events == ['reserved', 'unknown']
