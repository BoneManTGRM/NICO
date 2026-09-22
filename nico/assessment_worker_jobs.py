"""Internal durable worker ownership, using the existing client_jobs table.

Callers must authorize intake and validate retained artifacts independently.
Completion here records a worker receipt reference, not assessment qualification.
No public endpoint or execution path is enabled by importing this module.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Callable
from uuid import uuid4

from nico.storage import PostgresAdapter

WORKFLOW = "assessment_worker_job.v1"
TERMINAL = frozenset({"completed", "failed", "cancelled", "budget_exhausted"})


class JobConflict(RuntimeError):
    """A job identity, lease or immutable result no longer matches."""


def _digest(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class JobIdentity:
    customer_id: str
    project_id: str
    run_id: str
    scan_id: str
    repository_id: str
    revision: str
    contract_sha256: str
    release_revision: str

    def __post_init__(self):
        for value in asdict(self).values():
            if not isinstance(value, str) or not value or len(value) > 512 or value != value.strip():
                raise ValueError("worker_job_identity_invalid")
        for value in (self.revision, self.release_revision):
            if not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", value):
                raise ValueError("worker_job_revision_invalid")
        if not re.fullmatch(r"[0-9a-f]{64}", self.contract_sha256):
            raise ValueError("worker_job_contract_digest_invalid")

    @property
    def job_id(self) -> str:
        return "workerjob_" + _digest(asdict(self))


@dataclass(frozen=True)
class JobLimits:
    max_attempts: int
    wall_seconds: int
    lease_seconds: int

    def __post_init__(self):
        # API ceilings, not a grant of mission spending or execution resources.
        if any(type(value) is not int for value in asdict(self).values()):
            raise ValueError("worker_job_limits_invalid")
        bounds = ((self.max_attempts, 1, 10), (self.wall_seconds, 1, 21600),
                  (self.lease_seconds, 1, min(300, self.wall_seconds)))
        if any(type(value) is not int or not lower <= value <= upper for value, lower, upper in bounds):
            raise ValueError("worker_job_limits_invalid")


class WorkerJobs:
    def __init__(self, adapter: PostgresAdapter):
        if not isinstance(adapter, PostgresAdapter):
            raise TypeError("worker_jobs_require_durable_postgres")
        self.adapter = adapter

    @staticmethod
    def _now(connection) -> float:
        return float(connection.execute("SELECT extract(epoch FROM clock_timestamp()) AS epoch").fetchone()["epoch"])

    @staticmethod
    def _scope(identity: JobIdentity) -> tuple:
        return (identity.job_id, identity.customer_id, identity.project_id, WORKFLOW)

    def _read(self, connection, identity: JobIdentity, *, lock=False):
        row = connection.execute(
            "SELECT payload FROM client_jobs WHERE job_id=%s AND customer_id=%s "
            "AND project_id=%s AND payload->>'workflow'=%s" + (" FOR UPDATE" if lock else ""),
            self._scope(identity),
        ).fetchone()
        if row is None:
            return None
        payload = row["payload"]
        if payload.get("identity") != asdict(identity) or payload.get("job_id") != identity.job_id:
            raise JobConflict("worker_job_identity_conflict")
        return payload

    def get(self, identity: JobIdentity) -> dict | None:
        with self.adapter._connect() as connection:
            return self._read(connection, identity)

    def get_by_id(self, job_id: str) -> dict | None:
        """Lookup only after authenticating the token's exact job audience."""
        if not re.fullmatch(r"workerjob_[0-9a-f]{64}", job_id):
            raise ValueError("worker_job_id_invalid")
        stored = self.adapter.get("client_jobs", job_id)
        if stored is None or stored.get("workflow") != WORKFLOW:
            return None
        identity = JobIdentity(**stored["identity"])
        if identity.job_id != job_id:
            raise JobConflict("worker_job_identity_conflict")
        return self.get(identity)

    def enqueue(self, identity: JobIdentity, limits: JobLimits, *, contract=None, scan=None) -> dict:
        if contract is not None and (not isinstance(contract, dict) or _digest(contract) != identity.contract_sha256):
            raise ValueError("worker_job_contract_mismatch")
        if scan is not None:
            if contract is None or any(scan.get(key) != value for key, value in {
                "scan_id": identity.scan_id, "customer_id": identity.customer_id,
                "project_id": identity.project_id, "run_id": identity.run_id,
                "repository": identity.repository_id, "snapshot_commit_sha": identity.revision,
                "worker_job_id": identity.job_id, "status": "queued",
            }.items()):
                raise ValueError("worker_job_scan_mismatch")
        with self.adapter._connect() as connection:
            now = self._now(connection)
            payload = {
                "job_id": identity.job_id, "workflow": WORKFLOW,
                "identity": asdict(identity), "limits": asdict(limits),
                "customer_id": identity.customer_id, "project_id": identity.project_id,
                "status": "queued", "attempts": 0,
                "deadline_epoch": now + limits.wall_seconds,
                "lease_id": "", "lease_until_epoch": 0, "worker_id": "",
                "receipt_sha256": "", "failure_code": "",
            }
            if contract is not None:
                payload["contract"] = contract
            if scan is not None:
                payload["source_access"] = {"mode": scan.get("provider_access_mode"),
                                            "credential_used": scan.get("provider_credential_used")}
            connection.execute(
                "INSERT INTO client_jobs(job_id,customer_id,project_id,status,payload,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
                "ON CONFLICT(job_id) DO NOTHING",
                (identity.job_id, identity.customer_id, identity.project_id, "queued", self.adapter._jsonb(payload)),
            )
            existing = self._read(connection, identity, lock=True)
            if (existing is None or existing["limits"] != asdict(limits)
                    or existing.get("contract") != contract
                    or existing.get("source_access") != payload.get("source_access")):
                raise JobConflict("worker_job_enqueue_conflict")
            if scan is not None:
                connection.execute(
                    "INSERT INTO scanner_runs(scan_id,customer_id,project_id,status,payload,created_at,updated_at) "
                    "VALUES(%s,%s,%s,'queued',%s,clock_timestamp(),clock_timestamp()) ON CONFLICT DO NOTHING",
                    (identity.scan_id, identity.customer_id, identity.project_id, self.adapter._jsonb(scan)),
                )
                stored = connection.execute("SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE",
                                            (identity.scan_id,)).fetchone()
                if stored is None or stored["payload"].get("worker_job_id") != identity.job_id:
                    raise JobConflict("worker_job_scan_conflict")
            return existing

    def _change(self, identity: JobIdentity, operation: Callable):
        with self.adapter._connect() as connection:
            payload = self._read(connection, identity, lock=True)
            if payload is None:
                raise JobConflict("worker_job_missing")
            # Read database time after acquiring ownership lock, not before waiting.
            result, changed = operation(payload, self._now(connection), connection)
            if changed:
                connection.execute(
                    "UPDATE client_jobs SET status=%s,payload=%s,updated_at=clock_timestamp() "
                    "WHERE job_id=%s AND customer_id=%s AND project_id=%s AND payload->>'workflow'=%s",
                    (payload["status"], self.adapter._jsonb(payload), *self._scope(identity)),
                )
                if payload.get("contract") and payload["status"] != "completed":
                    row = connection.execute("SELECT payload FROM scanner_runs WHERE scan_id=%s FOR UPDATE",
                                             (identity.scan_id,)).fetchone()
                    scan = row["payload"] if row else None
                    if scan is None or scan.get("worker_job_id") != identity.job_id:
                        raise JobConflict("worker_job_scan_conflict")
                    scan.update(status=("failed" if payload["status"] == "budget_exhausted" else payload["status"]),
                                current_stage="worker_" + payload["status"],
                                worker_failure_code=payload.get("failure_code", ""))
                    connection.execute("UPDATE scanner_runs SET status=%s,payload=%s,updated_at=clock_timestamp() "
                                       "WHERE scan_id=%s", (scan["status"], self.adapter._jsonb(scan), identity.scan_id))
            return result

    def reserve_dispatch(self, identity: JobIdentity, repository: str) -> str | None:
        """Commit one launch reservation before any external submission.

        A crashed pending reservation is ambiguous, never permission to resend.
        Explicit operator recovery must reconcile the provider run first.
        """
        if not isinstance(repository, str) or not re.fullmatch(r'[A-Za-z0-9_-]+/[A-Za-z0-9_.-]+', repository):
            raise ValueError('worker_dispatch_repository_invalid')

        def operation(payload, now, _connection):
            if (payload.get('dispatch') is not None or payload['status'] != 'queued'
                    or now >= payload['deadline_epoch']):
                return None, False
            nonce = uuid4().hex
            payload['dispatch'] = {'nonce': nonce, 'repository': repository,
                'state': 'pending', 'reserved_epoch': now, 'run_id': None}
            return nonce, True
        return self._change(identity, operation)

    def finish_dispatch(self, identity: JobIdentity, nonce: str, state: str, *, run_id=None) -> dict:
        if (not isinstance(nonce, str) or not re.fullmatch(r'[0-9a-f]{32}', nonce)
                or state not in {'accepted', 'rejected', 'unknown'}
                or (run_id is not None and (type(run_id) is not int or not 1 <= run_id < 10**20))
                or (run_id is not None and state != 'accepted')):
            raise ValueError('worker_dispatch_result_invalid')

        def operation(payload, now, _connection):
            dispatch = payload.get('dispatch') or {}
            if dispatch.get('nonce') != nonce:
                raise JobConflict('worker_dispatch_reservation_conflict')
            if dispatch.get('state') != 'pending':
                if dispatch.get('state') == state and dispatch.get('run_id') == run_id:
                    return payload, False
                raise JobConflict('worker_dispatch_result_conflict')
            # Mutate the freshly locked row; never replace a racing lease or receipt.
            payload['dispatch'] = {**dispatch, 'state': state, 'finished_epoch': now, 'run_id': run_id}
            if state == 'rejected' and payload['status'] == 'queued' and payload['attempts'] == 0:
                payload.update(status='failed', failure_code='worker_dispatch_rejected')
            return payload, True
        return self._change(identity, operation)

    def claim(self, identity: JobIdentity, worker_id: str, *, claim_nonce: str | None = None) -> dict | None:
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 256:
            raise ValueError("worker_id_invalid")

        if claim_nonce is not None and not re.fullmatch(r"[0-9a-f]{64}", claim_nonce):
            raise ValueError("worker_nonce_invalid")

        def operation(payload, now, _connection):
            if payload["status"] in TERMINAL:
                return None, False
            if now >= payload["deadline_epoch"]:
                payload["status"] = "budget_exhausted"
                return None, True
            if payload["status"] == "running" and now < payload["lease_until_epoch"]:
                if (claim_nonce and payload.get("claim_nonce") == claim_nonce
                        and payload["worker_id"] == worker_id):
                    return payload, False  # lost claim response; same active ownership
                return None, False
            if claim_nonce and claim_nonce in payload.get("used_claim_nonces", []):
                raise JobConflict("worker_claim_replay")
            if payload["attempts"] >= payload["limits"]["max_attempts"]:
                payload["status"] = "failed"
                payload["failure_code"] = "attempt_budget_exhausted"
                return None, True
            if payload["status"] not in {"running", "queued"}:
                raise JobConflict("worker_job_status_invalid")
            payload.update(status="running", attempts=payload["attempts"] + 1,
                           worker_id=worker_id, lease_id=uuid4().hex,
                           lease_until_epoch=min(now + payload["limits"]["lease_seconds"], payload["deadline_epoch"]))
            if claim_nonce:
                payload["claim_nonce"] = claim_nonce
                payload["used_claim_nonces"] = [*payload.get("used_claim_nonces", []), claim_nonce]
            return payload, True

        return self._change(identity, operation)

    def poll(self, identity: JobIdentity) -> dict:
        """Reconcile a vanished owner without dispatching or resetting budgets."""
        def operation(payload, now, _connection):
            if payload["status"] in TERMINAL:
                return payload, False
            if now >= payload["deadline_epoch"]:
                payload.update(status="budget_exhausted", failure_code="wall_budget_exhausted",
                               lease_until_epoch=0)
            elif payload["status"] == "running" and now >= payload["lease_until_epoch"]:
                exhausted = payload["attempts"] >= payload["limits"]["max_attempts"]
                payload.update(status="failed" if exhausted else "queued", lease_until_epoch=0,
                               failure_code="attempt_budget_exhausted" if exhausted else "worker_lease_expired")
            else:
                return payload, False
            return payload, True
        return self._change(identity, operation)

    @staticmethod
    def _owned(payload, lease_id, now, worker_id=None):
        if (not lease_id or payload["status"] != "running" or payload["lease_id"] != lease_id
                or now >= min(payload["lease_until_epoch"], payload["deadline_epoch"])
                or (payload.get("contract") is not None and worker_id is None)
                or (worker_id is not None and payload["worker_id"] != worker_id)):
            raise JobConflict("worker_job_lease_conflict")

    def heartbeat(self, identity: JobIdentity, lease_id: str, *, worker_id=None) -> dict:
        def operation(payload, now, _connection):
            self._owned(payload, lease_id, now, worker_id)
            payload["lease_until_epoch"] = min(now + payload["limits"]["lease_seconds"], payload["deadline_epoch"])
            return payload, True
        return self._change(identity, operation)

    def complete(self, identity: JobIdentity, lease_id: str, receipt_sha256: str, *, worker_id=None, publish=None) -> dict:
        """Bind an already retained/validated receipt; does not validate its bytes."""
        if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
            raise ValueError("worker_job_receipt_digest_invalid")

        def operation(payload, now, connection):
            if payload.get("contract") is not None and (worker_id is None or publish is None):
                raise JobConflict("worker_job_verified_publication_required")
            if (payload["status"] == "completed" and payload["lease_id"] == lease_id
                    and payload["receipt_sha256"] == receipt_sha256
                    and (worker_id is None or payload["worker_id"] == worker_id)):
                return payload, False
            self._owned(payload, lease_id, now, worker_id)
            if publish is not None:
                # The caller validates bytes before this transaction. Publication
                # shares the locked job's transaction and rolls back on any error.
                publish(connection, payload)
                self._owned(payload, lease_id, self._now(connection), worker_id)
            payload.update(status="completed", receipt_sha256=receipt_sha256)
            return payload, True
        return self._change(identity, operation)

    def fail(self, identity: JobIdentity, lease_id: str, failure_code: str, *, retryable: bool, worker_id=None) -> dict:
        if not isinstance(failure_code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", failure_code):
            raise ValueError("worker_job_failure_code_invalid")
        if type(retryable) is not bool:
            raise ValueError("worker_job_retryability_invalid")

        def operation(payload, now, _connection):
            self._owned(payload, lease_id, now, worker_id)
            payload.update(status=("queued" if retryable and payload["attempts"] < payload["limits"]["max_attempts"] else "failed"),
                           failure_code=failure_code, lease_until_epoch=0)
            return payload, True
        return self._change(identity, operation)

    def cancel(self, identity: JobIdentity) -> bool:
        def operation(payload, _now, _connection):
            if payload["status"] in TERMINAL:
                return payload["status"] == "cancelled", False
            payload.update(status="cancelled", lease_until_epoch=0)
            return True, True
        return self._change(identity, operation)
