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
