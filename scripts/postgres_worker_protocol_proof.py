"""Disposable PostgreSQL + HTTP worker protocol proof. All native data is synthetic.

No repository code, analyzer, build, production endpoint or human action executes.
"""
from __future__ import annotations

import argparse
from copy import deepcopy
from dataclasses import asdict, replace
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from types import SimpleNamespace
from uuid import uuid4

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import jwt

from nico import assessment_worker_auth as auth
from nico.assessment_worker_api import PREFIX
from nico.assessment_worker_jobs import JobConflict, JobIdentity, WorkerJobs, _digest
from nico.assessment_worker_receipts import enqueue_snapshot_scan, publish_receipt
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.scanner_raw_artifact_storage_v1 import ScannerArtifactStore, read_scanner_artifact
from nico.scanner_worker import get_scan
from nico.snapshot_scanner_worker import start_snapshot_scan
from nico.storage import PostgresAdapter, STORE
from nico import scanner_recovery as recovery
from nico.snapshot_scanner_resilience_patch import _resume_snapshot_scanner_run
from scripts.worker_protocol_fixture import contract, receipt


def run_proof(database_url):
    adapter = PostgresAdapter(database_url)
    STORE.adapter = adapter
    jobs = WorkerJobs(adapter)
    release = "c" * 40
    os.environ["RAILWAY_GIT_COMMIT_SHA"] = release
    os.environ["NICO_ASSESSMENT_WORKER_REPOSITORY_ID"] = "123456"
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    auth._jwk_client = lambda: SimpleNamespace(get_signing_key_from_jwt=lambda _: SimpleNamespace(key=key.public_key()))
    from nico.api.specialist_ship_ready_bootstrap import app
    client = TestClient(app)
    worker = "github:123456:12345678:1"
    checks = {}

    def enqueue(label):
        run = "synthetic-protocol-" + uuid4().hex
        payload = {"authorized": True, "authorized_by": "owned_synthetic_protocol_fixture",
            "authorization_scope": "transport fixture only; no repository execution",
            "customer_id": run, "project_id": "synthetic-project", "run_id": run,
            "repository": "example/owned-control", "snapshot_id": "fixture-" + label,
            "snapshot_commit_sha": "a" * 40, "provider_access_mode": "anonymous_public",
            "provider_credential_used": False}
        scan = start_snapshot_scan(payload, worker_contract=contract())
        repeated = start_snapshot_scan(payload, worker_contract=contract())
        assert scan == repeated
        assert scan["status"] == "queued" and "cppcheck" in scan["tools_requested"]
        return JobIdentity(**jobs.get_by_id(scan["worker_job_id"])["identity"])

    def token(job, *, nonce=None, run_id="12345678"):
        now = int(time.time())
        claims = {"iss": auth.ISSUER, "aud": auth.AUDIENCE + "/" + job.job_id,
            "sub": "repo:BoneManTGRM/NICO:ref:refs/heads/main", "iat": now, "nbf": now,
            "exp": now + 300, "jti": nonce or uuid4().hex, "repository": "BoneManTGRM/NICO",
            "repository_id": "123456", "ref": "refs/heads/main", "sha": release,
            "workflow_sha": release, "workflow_ref": "BoneManTGRM/NICO/" + auth.WORKFLOW + "@refs/heads/main",
            "event_name": "workflow_dispatch", "run_id": run_id, "run_attempt": "1", "runner_environment": "github-hosted"}
        return jwt.encode(claims, key, algorithm="RS256")

    def post(job, operation, body, *, credential=None, expected=200):
        response = client.post(f"{PREFIX}/{job.job_id}/{operation}", json=body,
                               headers={"Authorization": "Bearer " + (credential or token(job))})
        assert response.status_code == expected, (operation, response.status_code, response.text)
        return response.json()

    first = enqueue("normal")
    credential = token(first)
    claimed = post(first, "claim", {}, credential=credential)
    assert post(first, "claim", {}, credential=credential) == claimed
    checks["atomic_enqueue_and_lost_claim_response"] = True
    different = {**get_scan(first.scan_id), "status": "queued", "tools_requested": ["cppcheck"]}
    alternative = enqueue_snapshot_scan(different, contract(), adapter)
    assert alternative["scan_id"] != first.scan_id and alternative["tools_requested"] == ["cppcheck"]
    assert enqueue_snapshot_scan(different, contract(), adapter) == alternative
    checks["requested_tool_population_has_distinct_immutable_dispatch"] = True
    assert get_scan(first.scan_id)["status"] == "running"
    beat = post(first, "heartbeat", {"lease_id": claimed["lease_id"]})
    assert beat["lease_until_epoch"] > claimed["lease_until_epoch"]
    checks["authenticated_claim_heartbeat_and_durable_poll"] = True
    post(first, "heartbeat", {"lease_id": claimed["lease_id"]}, credential=token(first, run_id="98765432"), expected=409)
    checks["different_worker_cannot_use_current_lease"] = True

    before = jobs.get(first)
    assert client.get("/client-job/" + first.job_id).json()["status"] == "not_found"
    assert client.get("/client-job/" + first.job_id + "/exports").json()["status"] == "not_found"
    assert client.post("/client-job/package", json={"job_id": first.job_id}).json()["status"] == "blocked"
    assert client.post("/client-job/export", json={"job_id": first.job_id, "format": "json"}).json()["status"] == "not_found"
    assert jobs.get(first) == before
    checks["public_client_job_namespace_isolated"] = True

    # Native SQL must exclude worker records before the bounded inventory limit,
    # and inside compare-and-set, including rows left by older buggy recovery.
    with adapter._connect() as connection:
        connection.execute("UPDATE scanner_runs SET updated_at=clock_timestamp()-interval '1 hour' WHERE scan_id=%s", (first.scan_id,))
    assert first.scan_id not in {row["scan_id"] for row in recovery._bounded_scanner_records(STORE, statuses={"running"})}
    recovery.reconcile_interrupted_scanner_runs(store=STORE)
    assert get_scan(first.scan_id)["status"] == "running"
    assert recovery.atomic_scanner_transition(first.scan_id, {"running"}, "recovery_required", {}, store=STORE) is None
    with adapter._connect() as connection:
        connection.execute("UPDATE scanner_runs SET status='recovery_required',payload=jsonb_set(payload,'{status}','\"recovery_required\"'::jsonb) WHERE scan_id=%s", (first.scan_id,))
    launched = []
    def capture(**kwargs):
        return SimpleNamespace(start=lambda: launched.append(kwargs))
    for resume in (recovery.resume_interrupted_scanner_run, _resume_snapshot_scanner_run):
        assert resume(first.scan_id, actor="synthetic-operator", store=STORE, thread_factory=capture)["code"] == "worker_lifecycle_requires_dedicated_job"
    assert recovery.close_interrupted_scanner_run(first.scan_id, actor="synthetic-operator",
        reason_code="no_longer_required", store=STORE)["code"] == "worker_lifecycle_requires_dedicated_job"
    assert not launched and get_scan(first.scan_id)["status"] == "recovery_required" and jobs.get(first) == before
    with adapter._connect() as connection:
        connection.execute("UPDATE scanner_runs SET status='running',payload=jsonb_set(payload,'{status}','\"running\"'::jsonb),updated_at=clock_timestamp() WHERE scan_id=%s", (first.scan_id,))
    checks["legacy_recovery_cannot_mutate_or_execute_worker_scans"] = True

    native = receipt(first, claimed["lease_id"], worker)
    wrong = deepcopy(native)
    wrong["identity"]["customer_id"] = "different-tenant"
    post(first, "receipt", {"lease_id": claimed["lease_id"], "receipt": wrong}, expected=422)
    assert get_scan(first.scan_id)["status"] == "running"
    checks["cross_tenant_receipt_rejected_without_publication"] = True

    encoded_secret = deepcopy(native)
    encoded_secret["native"]["xml"] = encoded_secret["native"]["xml"].replace("Synthetic protocol fixture", "gh&#112;_" + "x" * 36)
    encoded_secret["native_sha256"] = _digest(encoded_secret["native"])
    post(first, "receipt", {"lease_id": claimed["lease_id"], "receipt": encoded_secret}, expected=422)
    with adapter._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM scanner_raw_artifacts WHERE scan_id=%s", (first.scan_id,)).fetchone()["n"] == 0
    assert get_scan(first.scan_id)["status"] == "running" and jobs.get(first) == before
    checks["decoded_xml_secret_rejected_before_storage"] = True

    # Real transaction failure after immutable insertion must roll back all records.
    original_put = ScannerArtifactStore.put_in_transaction
    def fail_after_insert(self, connection, *args):
        original_put(self, connection, *args)
        raise RuntimeError("synthetic_transaction_failure")
    ScannerArtifactStore.put_in_transaction = fail_after_insert
    try:
        try:
            publish_receipt(jobs, first, claimed["lease_id"], worker, native)
        except RuntimeError as exc:
            assert str(exc) == "synthetic_transaction_failure"
        else:
            raise AssertionError("publication rollback was not exercised")
    finally:
        ScannerArtifactStore.put_in_transaction = original_put
    with adapter._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM scanner_raw_artifacts WHERE scan_id=%s",
                                  (first.scan_id,)).fetchone()["n"] == 0
    assert jobs.get(first)["status"] == "running"
    assert get_scan(first.scan_id)["status"] == "running"
    checks["artifact_scan_job_publication_rollback"] = True

    result = post(first, "receipt", {"lease_id": claimed["lease_id"], "receipt": native})
    repeated = post(first, "receipt", {"lease_id": claimed["lease_id"], "receipt": native})
    assert result == repeated and result["status"] == "completed"
    scan = get_scan(first.scan_id)
    assert scan["status"] == "complete" and scan["scanner_results"][0]["finding_count"] == 1
    record = scan["scanner_results"][0]
    binding = {key: record[key] for key in ("run_id", "scan_id", "customer_id", "project_id", "repository", "commit_sha", "scanner_name")}
    first_read = read_scanner_artifact(record, binding=binding)
    second_read = read_scanner_artifact(record, binding=binding)
    assert first_read.metadata["availability"] == "verified" and first_read.raw == second_read.raw
    assert hashlib.sha256(first_read.raw).hexdigest() == result["receipt_sha256"]
    checks["verified_native_bytes_and_idempotent_retrieval"] = True
    compact = compact_scanner_records(scan, commit_sha=first.revision)
    cpp = next(row for row in compact if row["scanner_name"] == "cppcheck")
    assert cpp["worker_provenance"]["job_id"] == first.job_id
    assert cpp["finding_count"] == 1 and not cpp["findings"]
    assert cpp["cppcheck_source_coverage"]["configuration_aware"] is False
    assert set(scan["tools_requested"]) == {row["tool"] for row in scan["scanner_results"]}
    assert all(row["completed"] is False for row in compact if row["scanner_name"] != "cppcheck")
    assert scan["human_review_required"] is True and scan["client_delivery_allowed"] is False
    checks["existing_compact_projection_preserves_identity_and_limits"] = True

    child = subprocess.run([sys.executable, "-c", "\n".join([
        "import json, os, sys", "from nico.storage import PostgresAdapter, STORE",
        "from nico.assessment_worker_jobs import JobIdentity, WorkerJobs",
        "from nico.scanner_worker import get_scan", "data=json.load(sys.stdin)",
        "STORE.adapter=PostgresAdapter(os.environ['NICO_TEST_DATABASE_URL'])",
        "identity=JobIdentity(**data['identity'])", "job=WorkerJobs(STORE.adapter).get(identity)",
        "assert job['status']=='completed' and job['receipt_sha256']==data['receipt_sha256']",
        "assert get_scan(identity.scan_id)['receipt_sha256']==data['receipt_sha256']",
        "print('fresh_process_protocol_verified')",
    ])], input=json.dumps({"identity": asdict(first), "receipt_sha256": result["receipt_sha256"]}),
        text=True, capture_output=True, timeout=30,
        env={**os.environ, "NICO_TEST_DATABASE_URL": database_url})
    assert child.returncode == 0 and child.stdout.strip() == "fresh_process_protocol_verified"
    checks["fresh_process_job_scan_recovery"] = True

    second = enqueue("stale")
    old_token = token(second)
    old = post(second, "claim", {}, credential=old_token)
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{lease_until_epoch}','0'::jsonb) WHERE job_id=%s",
                           (second.job_id,))
    post(second, "claim", {}, credential=old_token, expected=409)
    replacement = post(second, "claim", {})
    assert replacement["lease_id"] != old["lease_id"] and replacement["attempts"] == 2
    post(second, "receipt", {"lease_id": old["lease_id"], "receipt": receipt(second, old["lease_id"], worker)}, expected=409)
    with adapter._connect() as connection:
        assert connection.execute("SELECT count(*) AS n FROM scanner_raw_artifacts WHERE scan_id=%s", (second.scan_id,)).fetchone()["n"] == 0
    valid = receipt(second, replacement["lease_id"], worker)
    assert post(second, "receipt", {"lease_id": replacement["lease_id"], "receipt": valid})["status"] == "completed"
    checks["replay_and_stale_owner_cannot_poison_artifact_slot"] = True
    post(second, "heartbeat", {"lease_id": replacement["lease_id"]}, credential=credential, expected=401)
    checks["cross_job_token_substitution_rejected"] = True

    cancelled = enqueue("cancelled")
    owner = post(cancelled, "claim", {})
    assert jobs.cancel(cancelled)
    post(cancelled, "receipt", {"lease_id": owner["lease_id"], "receipt": receipt(cancelled, owner["lease_id"], worker)}, expected=409)
    assert get_scan(cancelled.scan_id)["status"] == "cancelled"
    checks["cancellation_fences_receipt_and_updates_polling"] = True

    failed = enqueue("retry")
    owner = post(failed, "claim", {})
    post(failed, "fail", {"lease_id": owner["lease_id"], "failure_code": "synthetic_failure", "retryable": True})
    retry = post(failed, "claim", {})
    result = post(failed, "fail", {"lease_id": retry["lease_id"], "failure_code": "synthetic_failure", "retryable": True})
    assert result["status"] == "failed" and get_scan(failed.scan_id)["status"] == "failed"
    checks["bounded_retry_terminal_state_reaches_polling"] = True

    exhausted = enqueue("deadline")
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{deadline_epoch}','0'::jsonb) WHERE job_id=%s", (exhausted.job_id,))
    post(exhausted, "claim", {}, expected=409)
    assert jobs.get(exhausted)["status"] == "budget_exhausted" and get_scan(exhausted.scan_id)["status"] == "failed"
    checks["server_deadline_exhaustion_reaches_polling"] = True

    # A vanished worker must not leave an assessment running forever. These
    # transitions are driven by polling alone, without a replacement claim.
    queued_expired = enqueue("poll-queued-deadline")
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{deadline_epoch}','0'::jsonb) WHERE job_id=%s", (queued_expired.job_id,))
    assert get_scan(queued_expired.scan_id)["status"] == "failed"
    assert jobs.get(queued_expired)["status"] == "budget_exhausted"
    checks["poll_expires_undispatched_job_without_claim"] = True

    vanished = enqueue("poll-vanished")
    owner = post(vanished, "claim", {})
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{lease_until_epoch}','0'::jsonb) WHERE job_id=%s", (vanished.job_id,))
    assert get_scan(vanished.scan_id)["status"] == "queued"
    recovered = jobs.get(vanished)
    assert recovered["attempts"] == owner["attempts"] and recovered["deadline_epoch"] == owner["deadline_epoch"]
    assert get_scan(vanished.scan_id)["status"] == "queued" and jobs.get(vanished) == recovered
    post(vanished, "heartbeat", {"lease_id": owner["lease_id"]}, expected=409)
    post(vanished, "receipt", {"lease_id": owner["lease_id"], "receipt": receipt(vanished, owner["lease_id"], worker)}, expected=409)
    checks["poll_preserves_retry_budget_and_fences_vanished_owner"] = True
    post(vanished, "claim", {})
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{lease_until_epoch}','0'::jsonb) WHERE job_id=%s", (vanished.job_id,))
    assert get_scan(vanished.scan_id)["status"] == "failed"
    assert jobs.get(vanished)["failure_code"] == "attempt_budget_exhausted"
    checks["poll_exhausted_attempts_are_terminal_without_new_claim"] = True

    deadline = enqueue("poll-running-deadline")
    owner = post(deadline, "claim", {})
    with adapter._connect() as connection:
        connection.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{deadline_epoch}','0'::jsonb) WHERE job_id=%s", (deadline.job_id,))
    assert get_scan(deadline.scan_id)["status"] == "failed"
    assert jobs.get(deadline)["status"] == "budget_exhausted"
    post(deadline, "heartbeat", {"lease_id": owner["lease_id"]}, expected=409)
    checks["poll_expires_running_job_without_replacement"] = True
    terminal = jobs.get(first)
    assert get_scan(first.scan_id)["receipt_sha256"] == terminal["receipt_sha256"]
    assert jobs.get(first) == terminal
    checks["poll_preserves_completed_receipt"] = True
    assert len(checks) == 22 and all(checks.values())
    return {"schema": "nico.worker-protocol-postgres-proof.v1", "synthetic": True,
        "live_production": False, "repository_executed": False, "analyzer_executed": False,
        "human_approval_proven": False, "client_delivery_allowed": False, "checks": checks,
        "fixture_job_id": first.job_id, "receipt_sha256": scan["receipt_sha256"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    args = parser.parse_args()
    evidence = run_proof(os.environ["NICO_TEST_DATABASE_URL"])
    args.evidence.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n")
    print(json.dumps(evidence, sort_keys=True))
