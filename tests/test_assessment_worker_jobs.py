from dataclasses import replace

import pytest

from nico.assessment_worker_jobs import JobIdentity, JobLimits, WorkerJobs
from nico.storage import MemoryAdapter


def identity():
    return JobIdentity("tenant", "project", "run", "scan", "generic-repository",
                       "a" * 40, "b" * 64, "c" * 40)


@pytest.mark.parametrize("field", ["customer_id", "project_id", "run_id", "scan_id",
                                    "repository_id", "revision", "contract_sha256", "release_revision"])
def test_each_bound_identity_changes_job_id(field):
    original = identity()
    value = "d" * len(getattr(original, field))
    assert replace(original, **{field: value}).job_id != original.job_id
    assert identity().job_id == original.job_id


@pytest.mark.parametrize("changes", [
    {"max_attempts": 0}, {"max_attempts": 11}, {"max_attempts": True},
    {"wall_seconds": 0}, {"wall_seconds": 21601}, {"wall_seconds": "120"},
    {"wall_seconds": float("inf")}, {"wall_seconds": float("nan")},
    {"lease_seconds": 0}, {"lease_seconds": 301}, {"lease_seconds": 121},
])
def test_invalid_limits_rejected_without_coercion(changes):
    values = dict(max_attempts=2, wall_seconds=120, lease_seconds=30)
    values.update(changes)
    with pytest.raises(ValueError, match="worker_job_limits_invalid"):
        JobLimits(**values)


@pytest.mark.parametrize("changes", [
    {"run_id": ""}, {"run_id": " run"}, {"run_id": "x" * 513},
    {"repository_id": None}, {"revision": "main"},
    {"contract_sha256": "b" * 63}, {"release_revision": "c" * 39},
])
def test_invalid_identity_rejected(changes):
    with pytest.raises(ValueError):
        replace(identity(), **changes)


def test_volatile_storage_is_not_accepted_as_durable():
    with pytest.raises(TypeError, match="require_durable_postgres"):
        WorkerJobs(MemoryAdapter())


def test_configure_first_native_artifact_is_lease_bound_hash_verified_and_idempotent(monkeypatch):
    import base64
    import gzip
    import hashlib
    from nico import assessment_worker_jobs as module
    from nico.scanner_raw_artifact_storage_v1 import ScannerArtifactStore
    from nico.storage import PostgresAdapter

    jobs = object.__new__(module.WorkerJobs)
    jobs.adapter = object.__new__(PostgresAdapter)
    payload = {
        'status': 'running', 'lease_id': 'e' * 32, 'worker_id': 'github:1:2:3',
        'deadline_epoch': 200, 'lease_until_epoch': 150,
        'contract': {'profile': 'cpp-configure-first-v2'},
    }
    connection = object()
    jobs._change = lambda ident, operation: operation(payload, 100, connection)[0]
    stored = []
    def put(_self, actual_connection, binding, compressed, raw_sha256):
        assert actual_connection is connection
        stored.append((binding, compressed, raw_sha256))
        return 'scanartifact_' + 'a' * 64
    monkeypatch.setattr(ScannerArtifactStore, 'put_in_transaction', put)

    raw = b'{"native":"synthetic large-project evidence"}' * 100
    compressed = gzip.compress(raw, mtime=0)
    artifact = {
        'key': 'project-compiler-evidence',
        'raw_sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
        'gzip_sha256': hashlib.sha256(compressed).hexdigest(), 'gzip_bytes': len(compressed),
        'compressed': base64.b64encode(compressed).decode('ascii'),
    }
    result = jobs.put_artifact(identity(), 'e' * 32, 'github:1:2:3', artifact)
    assert result['artifact_id'].startswith('scanartifact_')
    assert result['sha256'] == artifact['raw_sha256']
    assert payload['native_artifacts']['project-compiler-evidence'] == result
    assert stored[0][0]['scanner_name'] == 'cppcheck:project-compiler-evidence'
    assert jobs.put_artifact(identity(), 'e' * 32, 'github:1:2:3', artifact) == result

    changed = {**artifact, 'raw_sha256': '0' * 64}
    with pytest.raises(ValueError, match='raw_digest'):
        jobs.put_artifact(identity(), 'e' * 32, 'github:1:2:3', changed)


def test_artifact_upload_rejects_wrong_profile_and_wrong_lease(monkeypatch):
    import base64
    import gzip
    import hashlib
    from nico import assessment_worker_jobs as module
    from nico.storage import PostgresAdapter

    jobs = object.__new__(module.WorkerJobs)
    jobs.adapter = object.__new__(PostgresAdapter)
    payload = {'status':'running','lease_id':'e'*32,'worker_id':'github:1:2:3',
               'deadline_epoch':200,'lease_until_epoch':150,
               'contract':{'profile':'cppcheck-standalone-v1'}}
    jobs._change = lambda ident, operation: operation(payload, 100, object())[0]
    raw=b'owned'; compressed=gzip.compress(raw,mtime=0)
    artifact={'key':'project-static-evidence','raw_sha256':hashlib.sha256(raw).hexdigest(),
              'raw_bytes':len(raw),'gzip_sha256':hashlib.sha256(compressed).hexdigest(),
              'gzip_bytes':len(compressed),'compressed':base64.b64encode(compressed).decode()}
    with pytest.raises(module.JobConflict, match='profile'):
        jobs.put_artifact(identity(),'e'*32,'github:1:2:3',artifact)
    payload['contract']['profile']='cpp-configure-first-v2'
    with pytest.raises(module.JobConflict, match='lease'):
        jobs.put_artifact(identity(),'f'*32,'github:1:2:3',artifact)
