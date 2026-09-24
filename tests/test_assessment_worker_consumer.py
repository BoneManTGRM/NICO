"""Job-consumer protocol tests; native execution is separately qualified in CI."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import time

import pytest

from nico import assessment_worker_receipts
from scripts.worker_protocol_fixture import contract, identity, receipt


def claimed():
    plan = contract(); job = identity(plan)
    return {'job_id': job.job_id, 'identity': asdict(job), 'contract': plan, 'limits': plan['limits'],
        'status': 'running', 'attempts': 1, 'deadline_epoch': time.time()+120,
        'lease_id': 'e'*32, 'lease_until_epoch': time.time()+30, 'receipt_sha256': '',
        'worker_id': 'github:123456:12345678:1',
        'source_access': {'mode': 'anonymous_public', 'credential_used': False}}


def test_consumer_retains_native_receipt_and_requires_matching_terminal_hash(tmp_path):
    from nico.assessment_worker_consumer import consume_one_job
    record = claimed(); sent = []
    class Transport:
        job_id = record['job_id']; release_revision = record['identity']['release_revision']
        def post(self, operation, payload, **kwargs):
            sent.append((operation, deepcopy(payload)))
            if operation == 'receipt':
                raw, _, _ = assessment_worker_receipts.validate_receipt(identity(), record['contract'],
                    record['lease_id'], record['worker_id'], payload['receipt'])
                return {**record, 'status': 'completed', 'receipt_sha256': hashlib.sha256(raw).hexdigest()}
            return deepcopy(record)
    def acquire(job, root, checkpoint):
        checkpoint(); return root, {'source_bytes': 24, 'synthetic': True}
    def execute(plan, source, **kwargs):
        kwargs['checkpoint'](); return {'native': receipt()['native'], 'native_decoding_failed': False}
    result = consume_one_job(Transport(), acquire=acquire, execute=execute)
    assert result['job_id'] == record['job_id'] and result['receipt_sha256']
    assert [op for op, _ in sent].count('receipt') == 1
    assert sent[0] == ('claim', {})


@pytest.mark.parametrize('change', [
    {'job_id': 'workerjob_'+'f'*64}, {'worker_id': ''}, {'lease_id': 'bad'},
    {'source_access': {'mode': 'authenticated_read_only', 'credential_used': True}},
    {'source_access': {'mode': 'anonymous_public', 'credential_used': None}},
    {'deadline_epoch': 1}, {'deadline_epoch': float('nan')},
    {'limits': {'max_attempts': 1, 'wall_seconds': 1, 'lease_seconds': 1}},
])
def test_invalid_claim_never_acquires_or_executes(change):
    from nico.assessment_worker_consumer import consume_one_job
    record = claimed(); wrong = {**record, **change}; called = []
    class Transport:
        job_id = record['job_id']; release_revision = record['identity']['release_revision']
        def post(self, operation, payload, **kwargs): return wrong
    with pytest.raises(ValueError):
        consume_one_job(Transport(), acquire=lambda *a, **kw: called.append('acquire'),
                        execute=lambda *a, **kw: called.append('execute'))
    assert called == []


def test_cross_release_claim_is_rejected():
    from nico.assessment_worker_consumer import validate_claim
    record = claimed()
    with pytest.raises(ValueError, match='binding'):
        validate_claim(record, job_id=record['job_id'], release_revision='d'*40)


def test_lost_claim_response_reuses_exact_body_and_credential():
    import requests
    from nico.assessment_worker_consumer import WorkerTransport
    record = claimed(); requests_seen = []; tokens = []
    class Response:
        status_code = 200
        headers = {'content-type': 'application/json'}
        def iter_content(self, chunk_size): yield json.dumps(record).encode()
        def close(self): pass
    class Session:
        def post(self, url, **kwargs):
            requests_seen.append((url, kwargs))
            if len(requests_seen) == 1: raise requests.ConnectionError('response lost')
            return Response()
    def token(): tokens.append(True); return 'synthetic-scoped-token'
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
                             record['identity']['release_revision'], token, session=Session())
    assert client._post_inline('claim', {}) == record
    assert len(tokens) == 1 and len(requests_seen) == 2
    assert requests_seen[0] == requests_seen[1]
    assert requests_seen[0][1]['allow_redirects'] is False


def test_redirect_never_receives_worker_credential_followup():
    from nico.assessment_worker_consumer import WorkerTransport
    record = claimed(); calls = []
    class Response:
        status_code = 302
        headers = {'Location': 'https://untrusted.example.invalid'}
        def close(self): pass
    class Session:
        def post(self, url, **kwargs): calls.append(url); return Response()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
                             record['identity']['release_revision'], lambda: 'synthetic-token', session=Session())
    with pytest.raises(ValueError, match='http'):
        client._post_inline('claim', {})
    assert len(calls) == 1


@pytest.mark.parametrize('body', [b'{"x":1,"x":2}', b'{"x":NaN}', b'[]', b'\xff'])
def test_transport_rejects_ambiguous_or_non_object_response(body):
    from nico.assessment_worker_consumer import WorkerTransport
    record = claimed()
    class Response:
        status_code = 200
        def iter_content(self, chunk_size): yield body
        def close(self): pass
    class Session:
        def post(self, *args, **kwargs): return Response()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token', session=Session())
    with pytest.raises(ValueError): client._post_inline('claim', {})


@pytest.mark.parametrize('url', ['http://backend.example.invalid', 'https://u:p@host.invalid',
    'https://host.invalid/path', 'https://host.invalid?query=1', 'https://host.invalid/#fragment'])
def test_worker_transport_rejects_unsafe_destination(url):
    from nico.assessment_worker_consumer import WorkerTransport
    record = claimed()
    with pytest.raises(ValueError):
        WorkerTransport(url, record['job_id'], record['identity']['release_revision'], lambda: 'unused')


def test_terminal_substitution_is_not_reported_as_success():
    from nico.assessment_worker_consumer import consume_one_job
    record = claimed()
    class Transport:
        job_id = record['job_id']; release_revision = record['identity']['release_revision']
        def post(self, operation, payload, **kwargs):
            if operation == 'receipt': return {**record, 'status': 'completed', 'receipt_sha256': '0'*64}
            return deepcopy(record)
    with pytest.raises(ValueError, match='terminal'):
        consume_one_job(Transport(), acquire=lambda job, root, check: (root, {}),
            execute=lambda *args, **kwargs: {'native': receipt()['native'], 'native_decoding_failed': False})


def test_fenced_heartbeat_stops_execution_and_does_not_publish(monkeypatch):
    from nico import assessment_worker_consumer as consumer
    record = claimed(); sent = []; clock = [100.0]
    monkeypatch.setattr(consumer.time, 'monotonic', lambda: clock[0])
    class Transport:
        job_id = record['job_id']; release_revision = record['identity']['release_revision']
        def post(self, operation, payload, **kwargs):
            sent.append(operation)
            if operation == 'heartbeat': raise ValueError('worker_job_conflict')
            return deepcopy(record)
    def acquire(job, root, checkpoint):
        clock[0] += 12; checkpoint()
        pytest.fail('acquisition continued after lost lease')
    with pytest.raises(ValueError, match='conflict'):
        consumer.consume_one_job(Transport(), acquire=acquire,
            execute=lambda *args, **kwargs: pytest.fail('execution reached after lost lease'))
    assert 'receipt' not in sent


def test_local_aggregate_deadline_stops_before_native_execution(monkeypatch):
    from nico import assessment_worker_consumer as consumer
    record = claimed(); clock = [100.0]
    monkeypatch.setattr(consumer.time, 'monotonic', lambda: clock[0])
    class Transport:
        job_id = record['job_id']; release_revision = record['identity']['release_revision']
        def post(self, operation, payload, **kwargs): return deepcopy(record)
    def acquire(job, root, checkpoint):
        clock[0] += 130; checkpoint()
    with pytest.raises(ValueError, match='deadline'):
        consumer.consume_one_job(Transport(), acquire=acquire,
            execute=lambda *args, **kwargs: pytest.fail('execution reached after deadline'))


def test_transport_rejects_response_finishing_after_deadline(monkeypatch):
    from nico import assessment_worker_consumer as consumer
    clock = [100.0]
    monkeypatch.setattr(consumer.time, 'monotonic', lambda: clock[0])
    class Response:
        status_code = 200
        def iter_content(self, chunk_size):
            yield b'{}'
            clock[0] += 20
        def close(self): pass
    class Session:
        def post(self, *args, **kwargs): return Response()
    record = claimed()
    client = consumer.WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token', session=Session())
    with pytest.raises(ValueError, match='deadline'):
        client._post_inline('claim', {})


class BlockingToken:
    def __init__(self, marker): self.marker = marker
    def __call__(self):
        import ctypes
        import os
        from pathlib import Path
        Path(self.marker).write_text(str(os.getpid()))
        # POSIX C blocking call: Python signal handlers cannot guarantee escape.
        libc = ctypes.CDLL(None)
        mutex = ctypes.create_string_buffer(128)
        libc.pthread_mutex_init(ctypes.byref(mutex), None)
        libc.pthread_mutex_lock(ctypes.byref(mutex))
        libc.pthread_mutex_lock(ctypes.byref(mutex))
        return 'unreachable'


def test_transport_kills_and_reaps_blocking_credential_process(tmp_path, monkeypatch):
    import multiprocessing
    import os
    from nico import assessment_worker_consumer as consumer
    monkeypatch.setattr(consumer, 'TRANSPORT_SECONDS', 2)
    marker = tmp_path / 'child-pid'
    record = claimed()
    client = consumer.WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], BlockingToken(str(marker)))
    started = time.monotonic()
    with pytest.raises(ValueError, match='deadline'):
        client.post('claim', {})
    assert time.monotonic() - started < 3.5
    child_pid = int(marker.read_text())
    assert child_pid not in {p.pid for p in multiprocessing.active_children()}
    with pytest.raises(ProcessLookupError): os.kill(child_pid, 0)


class SyntheticToken:
    def __call__(self): return 'owned-transport-fixture'


def test_spawned_transport_replays_lost_response_over_verified_loopback_tls():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from nico.assessment_worker_consumer import WorkerTransport
    from scripts.qualify_cppcheck_worker_control import owned_tls_api
    app = FastAPI()
    @app.post('/internal/assessment-workers/{job_id}/receipt')
    def accept(job_id: str): return {}
    record = claimed(); calls = []
    with TestClient(app) as client, owned_tls_api(client, calls) as (backend, session):
        transport = WorkerTransport(backend, record['job_id'], record['identity']['release_revision'],
            SyntheticToken(), session=session)
        assert transport.post('receipt', {}) == {}
    assert len(calls) == 2 and calls[0] == calls[1]


def test_artifact_payload_uses_measured_bound_and_verifies_backend_reference(monkeypatch):
    from nico.assessment_worker_consumer import WorkerTransport, MAX_ARTIFACT_REQUEST_BYTES
    record = claimed()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token',
        session=type('Session', (), {'trust_env': True})())
    seen = []
    def post(operation, payload, **kwargs):
        seen.append((operation, payload))
        artifact = payload['artifact']
        return {'artifact': {'artifact_id':'scanartifact_'+'a'*64, 'key':artifact['key'],
            'sha256':artifact['raw_sha256'], 'gzip_sha256':artifact['gzip_sha256'],
            'retained_bytes':artifact['raw_bytes'], 'gzip_bytes':artifact['gzip_bytes'],
            'storage_backend':'postgres'}}
    monkeypatch.setattr(client, 'post', post)
    raw = b'compressible-native-evidence-' * 50000
    reference = client.put_artifact('e'*32, 'project-static-environment', raw)
    assert reference['storage_backend'] == 'postgres'
    assert seen[0][0] == 'artifact'
    assert len(assessment_worker_receipts.canonical_bytes(seen[0][1])) < MAX_ARTIFACT_REQUEST_BYTES


def test_artifact_payload_rejects_compressed_transport_over_eight_mib(monkeypatch):
    import os
    from nico.assessment_worker_consumer import WorkerTransport
    record = claimed()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token',
        session=type('Session', (), {'trust_env': True})())
    monkeypatch.setattr(client, 'post', lambda *args, **kwargs: pytest.fail('oversized artifact must not post'))
    raw = os.urandom(9 * 1024 * 1024)
    with pytest.raises(ValueError, match='compressed_limit'):
        client.put_artifact('e'*32, 'project-static-evidence', raw)
