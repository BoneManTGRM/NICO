"""Real database proof of worker job ownership; executes no repository code."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from pathlib import Path
from uuid import uuid4

from nico.assessment_worker_jobs import JobConflict, JobIdentity, JobLimits, WorkerJobs
from nico.storage import PostgresAdapter


def run_proof(database_url: str) -> dict:
    adapter = PostgresAdapter(database_url)
    jobs = WorkerJobs(adapter)
    identity = JobIdentity(
        customer_id="worker-proof-" + uuid4().hex,
        project_id="synthetic-project", run_id="synthetic-run", scan_id="synthetic-scan",
        repository_id="generic-repository", revision="a" * 40,
        contract_sha256="b" * 64, release_revision="c" * 40,
    )
    limits = JobLimits(max_attempts=2, wall_seconds=120, lease_seconds=30)
    initial = jobs.enqueue(identity, limits)
    job_id = initial["job_id"]
    assert jobs.enqueue(identity, limits) == initial
    try:
        jobs.enqueue(identity, replace(limits, max_attempts=3))
    except JobConflict:
        pass
    else:
        raise AssertionError("existing job budget overwritten")

    def claim(index: int):
        return WorkerJobs(adapter).claim(identity, f"synthetic-worker-{index}")

    with ThreadPoolExecutor(max_workers=8) as pool:
        claims = list(pool.map(claim, range(8)))
    winners = [value for value in claims if value is not None]
    assert len(winners) == 1
    first = winners[0]
    token = first["lease_id"]
    assert first["attempts"] == 1
    renewed = jobs.heartbeat(identity, token)
    assert renewed["status"] == "running"
    assert renewed["lease_until_epoch"] > first["lease_until_epoch"]
    assert jobs.get(identity)["lease_until_epoch"] == renewed["lease_until_epoch"]
    assert jobs.claim(identity, "competing-worker") is None
    try:
        jobs.complete(identity, "stale-lease", "d" * 64)
    except JobConflict:
        pass
    else:
        raise AssertionError("stale result accepted")

    # Fixture-only clock advancement in this synthetic job, never production state.
    def expire(*, deadline=False):
        field = "deadline_epoch" if deadline else "lease_until_epoch"
        with adapter._connect() as connection:
            connection.execute(
                "UPDATE client_jobs SET payload=jsonb_set(payload, %s, '0'::jsonb) "
                "WHERE job_id=%s AND customer_id=%s",
                ([field], job_id, identity.customer_id),
            )

    expire()
    try:
        jobs.complete(identity, token, "d" * 64)
    except JobConflict:
        pass
    else:
        raise AssertionError("expired result accepted before replacement claim")
    second = jobs.claim(identity, "restarted-worker")
    assert second and second["attempts"] == 2 and second["lease_id"] != token
    for operation in (
        lambda: jobs.heartbeat(identity, token),
        lambda: jobs.complete(identity, token, "d" * 64),
        lambda: jobs.fail(identity, token, "transient_error", retryable=True),
    ):
        try:
            operation()
        except JobConflict:
            pass
        else:
            raise AssertionError("expired owner changed replacement job")
    terminal = jobs.complete(identity, second["lease_id"], "d" * 64)
    assert terminal["status"] == "completed"
    reconnected = WorkerJobs(PostgresAdapter(database_url))
    assert reconnected.get(identity) == terminal
    # A separate interpreter reconstructs the store with no process-local job state.
    child = subprocess.run(
        [sys.executable, "-c", "\n".join([
            "import json, os, sys",
            "from nico.assessment_worker_jobs import JobIdentity, WorkerJobs",
            "from nico.storage import PostgresAdapter",
            "data = json.load(sys.stdin)",
            "jobs = WorkerJobs(PostgresAdapter(os.environ['NICO_TEST_DATABASE_URL']))",
            "assert jobs.get(JobIdentity(**data['identity'])) == data['terminal']",
            "print('fresh_process_receipt_verified')",
        ])],
        input=json.dumps({"identity": asdict(identity), "terminal": terminal}),
        text=True, capture_output=True, timeout=30,
        env={**os.environ, "NICO_TEST_DATABASE_URL": database_url},
    )
    assert child.returncode == 0 and child.stdout.strip() == "fresh_process_receipt_verified", "fresh process proof failed"
    assert reconnected.complete(identity, second["lease_id"], "d" * 64) == terminal
    try:
        reconnected.complete(identity, second["lease_id"], "e" * 64)
    except JobConflict:
        pass
    else:
        raise AssertionError("completed receipt replaced")
    assert reconnected.claim(identity, "late-worker") is None
    assert not reconnected.cancel(identity)
    assert reconnected.get(replace(identity, customer_id="different-tenant")) is None

    cancel_identity = replace(identity, scan_id="cancelled-scan")
    jobs.enqueue(cancel_identity, limits)
    cancelled_lease = jobs.claim(cancel_identity, "cancelled-worker")
    assert jobs.cancel(cancel_identity)
    assert jobs.get(cancel_identity)["status"] == "cancelled"
    try:
        jobs.complete(cancel_identity, cancelled_lease["lease_id"], "d" * 64)
    except JobConflict:
        pass
    else:
        raise AssertionError("cancelled job accepted result")

    retry_identity = replace(identity, scan_id="retry-scan")
    jobs.enqueue(retry_identity, limits)
    attempt = jobs.claim(retry_identity, "retry-worker")
    assert jobs.fail(retry_identity, attempt["lease_id"], "temporary_failure", retryable=True)["status"] == "queued"
    attempt = jobs.claim(retry_identity, "retry-worker-2")
    assert jobs.fail(retry_identity, attempt["lease_id"], "temporary_failure", retryable=True)["status"] == "failed"
    assert jobs.claim(retry_identity, "retry-worker-3") is None

    crash_identity = replace(identity, scan_id="crash-scan")
    job_id = jobs.enqueue(crash_identity, limits)["job_id"]
    assert jobs.claim(crash_identity, "crashed-worker-1")["attempts"] == 1
    expire()
    assert jobs.claim(crash_identity, "crashed-worker-2")["attempts"] == 2
    expire()
    assert jobs.claim(crash_identity, "crashed-worker-3") is None
    assert jobs.get(crash_identity)["failure_code"] == "attempt_budget_exhausted"

    deadline_identity = replace(identity, scan_id="deadline-scan")
    job_id = jobs.enqueue(deadline_identity, limits)["job_id"]
    deadline_lease = jobs.claim(deadline_identity, "deadline-worker")
    expire(deadline=True)
    for operation in (
        lambda: jobs.heartbeat(deadline_identity, deadline_lease["lease_id"]),
        lambda: jobs.complete(deadline_identity, deadline_lease["lease_id"], "d" * 64),
    ):
        try:
            operation()
        except JobConflict:
            pass
        else:
            raise AssertionError("deadline-expired owner changed job")
    assert jobs.claim(deadline_identity, "late-worker") is None
    assert jobs.get(deadline_identity)["status"] == "budget_exhausted"

    # A dispatch reservation survives crashes and concurrent intake. Provider
    # responses merge into the current row without undoing a racing claim.
    dispatch_identity = replace(identity, scan_id='dispatch-scan')
    dispatch_initial = jobs.enqueue(dispatch_identity, limits)
    with ThreadPoolExecutor(max_workers=8) as pool:
        reservations = list(pool.map(lambda _: WorkerJobs(adapter).reserve_dispatch(
            dispatch_identity, 'BoneManTGRM/NICO', authentication_mode='server_token'), range(8)))
    reservations = [value for value in reservations if value is not None]
    assert len(reservations) == 1
    reservation = reservations[0]
    assert WorkerJobs(PostgresAdapter(database_url)).reserve_dispatch(dispatch_identity, 'BoneManTGRM/NICO') is None
    dispatch_claim = jobs.claim(dispatch_identity, 'dispatch-race-worker')
    dispatch_result = jobs.finish_dispatch(dispatch_identity, reservation, 'accepted', run_id=123456)
    for field in ('status', 'lease_id', 'worker_id', 'attempts'):
        assert dispatch_result[field] == dispatch_claim[field]
    assert dispatch_result['deadline_epoch'] == dispatch_initial['deadline_epoch']
    assert dispatch_result['dispatch']['authentication_mode'] == 'server_token'
    assert jobs.finish_dispatch(dispatch_identity, reservation, 'accepted', run_id=123456) == dispatch_result
    try:
        jobs.finish_dispatch(dispatch_identity, reservation, 'unknown')
    except JobConflict:
        pass
    else:
        raise AssertionError('dispatch result replaced')
    rejected_identity = replace(identity, scan_id='dispatch-rejected-scan')
    rejected_initial = jobs.enqueue(rejected_identity, limits)
    rejected_nonce = jobs.reserve_dispatch(rejected_identity, 'BoneManTGRM/NICO')
    rejected = jobs.finish_dispatch(rejected_identity, rejected_nonce, 'rejected')
    assert rejected['status'] == 'failed' and rejected['attempts'] == 0
    assert rejected['deadline_epoch'] == rejected_initial['deadline_epoch']
    assert jobs.claim(rejected_identity, 'late-worker') is None

    return {
        "schema": "nico.worker_job_postgres_proof.v1", "status": "passed",
        "synthetic": True, "live_production_claim": False,
        "checks": {
            "single_claim_owner": True, "immutable_job_budget": True,
            "heartbeat_extends_persisted_lease": True, "expired_owner_fenced": True,
            "reconnect_preserves_terminal_receipt": True,
            "fresh_process_preserves_terminal_receipt": True,
            "idempotent_completion": True, "conflicting_receipt_rejected": True,
            "tenant_identity_separate": True, "cancellation_fences_completion": True,
            "retry_budget_enforced": True, "crash_retry_budget_enforced": True,
            "wall_budget_enforced": True,
            "single_durable_dispatch_reservation": True,
            "crashed_dispatch_not_resubmitted": True,
            "dispatch_response_preserves_racing_claim": True,
            "dispatch_does_not_reset_wall_budget": True,
            "dispatch_rejection_is_terminal": True,
        },
        "repository_executed": False, "human_approval": False,
        "client_delivery_authorized": False,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    result = run_proof(args.database_url)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
