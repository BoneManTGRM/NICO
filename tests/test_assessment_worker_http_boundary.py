from fastapi.testclient import TestClient
import pytest
from test_assessment_worker_auth import signed_worker, JOB


@pytest.mark.parametrize("operation", ["claim", "heartbeat", "receipt", "artifact", "fail"])
def test_production_worker_routes_require_their_own_authentication(operation):
    from nico.api.specialist_ship_ready_bootstrap import app
    with TestClient(app) as client:
        response = client.post(
            "/internal/assessment-workers/workerjob_" + "a" * 64 + "/" + operation,
            headers={"X-NICO-Admin-Token": "not-worker-authority"}, json={},
        )
    assert response.status_code == 401
    assert response.json() == {"detail": "worker_authentication_required"}


@pytest.fixture
def worker_client(signed_worker):
    from nico.api.specialist_ship_ready_bootstrap import app
    sign, _, _ = signed_worker
    with TestClient(app) as client:
        yield client, {"Authorization": "Bearer " + sign()}


@pytest.mark.parametrize("body", [b'{"lease_id":"one","lease_id":"two"}', b'{"x":NaN}', b'[]', b'null', b'\xff'])
def test_authenticated_malformed_body_is_rejected_before_any_storage_operation(worker_client, body):
    client, headers = worker_client
    response = client.post("/internal/assessment-workers/" + JOB + "/heartbeat", headers=headers, content=body)
    assert response.status_code == 422


def test_bounded_stream_and_encoded_body_rejected(worker_client):
    client, headers = worker_client
    path = "/internal/assessment-workers/" + JOB + "/heartbeat"
    assert client.post(path, headers=headers, content=(b"x" * 4097)).status_code == 413
    assert client.post(path, headers={**headers, "Content-Length": "9" * 5000}, content=b"{}").status_code == 413
    assert client.post(path, headers={**headers, "Content-Encoding": "gzip"}, content=b"{}").status_code == 415


def test_job_scoped_worker_token_cannot_call_operator_review_or_approval(worker_client):
    client, headers = worker_client
    for action in ("review", "authorize-delivery"):
        response = client.post("/assessment/comprehensive-run/synthetic-run/" + action, headers=headers, json={})
        assert response.status_code in {401, 403}


def test_worker_http_operations_require_postgres_even_with_valid_signature(worker_client, monkeypatch):
    from nico import assessment_worker_api as api
    from nico.storage import MemoryAdapter
    monkeypatch.setattr(api.STORE, "adapter", MemoryAdapter())
    client, headers = worker_client
    response = client.post("/internal/assessment-workers/" + JOB + "/claim", headers=headers, json={})
    assert response.status_code == 503
    assert response.json() == {"detail": "worker_durable_storage_unavailable"}


def test_artifact_body_has_separate_measured_twelve_mib_ceiling(worker_client):
    client, headers = worker_client
    path = "/internal/assessment-workers/" + JOB + "/artifact"
    oversized = b"x" * (12 * 1024 * 1024 + 1)
    response = client.post(path, headers=headers, content=oversized)
    assert response.status_code == 413


@pytest.mark.parametrize("key", ["project-runtime-evidence", "project-static-evidence"])
def test_runtime_and_static_artifacts_reach_the_same_verified_transport(monkeypatch, key):
    import base64, gzip, hashlib
    from nico.assessment_worker_consumer import WorkerTransport
    from tests.test_assessment_worker_consumer import claimed
    record = claimed()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token',
        session=type('Session', (), {'trust_env': True})())
    calls = []
    raw = b'{"schema":"owned-runtime-transport-control","complete":false}'
    def post(operation, payload):
        calls.append((operation, payload))
        artifact = payload['artifact']
        compressed = base64.b64decode(artifact['compressed'], validate=True)
        assert gzip.decompress(compressed) == raw
        assert artifact['raw_sha256'] == hashlib.sha256(raw).hexdigest()
        assert artifact['gzip_sha256'] == hashlib.sha256(compressed).hexdigest()
        assert payload['lease_id'] == 'e'*32
        return {'artifact': {'artifact_id': 'scanartifact_'+'a'*64, 'key': artifact['key'],
            'sha256': artifact['raw_sha256'], 'gzip_sha256': artifact['gzip_sha256'],
            'retained_bytes': artifact['raw_bytes'], 'gzip_bytes': artifact['gzip_bytes'],
            'storage_backend': 'postgres'}}
    monkeypatch.setattr(client, 'post', post)
    result = client.put_artifact('e'*32, key, raw)
    assert len(calls) == 1 and calls[0][0] == 'artifact'
    assert result['key'] == key and result['sha256'] == hashlib.sha256(raw).hexdigest()


@pytest.mark.parametrize("key", ["project-runtime-evidence-extra", "runtime-evidence", "../project-runtime-evidence"])
def test_runtime_artifact_transport_still_rejects_unknown_keys_before_post(monkeypatch, key):
    from nico.assessment_worker_consumer import WorkerTransport
    from tests.test_assessment_worker_consumer import claimed
    record = claimed()
    client = WorkerTransport('https://backend.example.invalid', record['job_id'],
        record['identity']['release_revision'], lambda: 'synthetic-token',
        session=type('Session', (), {'trust_env': True})())
    monkeypatch.setattr(client, 'post', lambda *a, **k: pytest.fail('unknown key must not post'))
    with pytest.raises(ValueError, match='worker_artifact_request_invalid'):
        client.put_artifact('e'*32, key, b'owned')
