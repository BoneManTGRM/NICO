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

    def enqueue(self, identity: JobIdentity, limits: JobLimits) -> dict:
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
            connection.execute(
                "INSERT INTO client_jobs(job_id,customer_id,project_id,status,payload,created_at,updated_at) "
                "VALUES(%s,%s,%s,%s,%s,clock_timestamp(),clock_timestamp()) "
                "ON CONFLICT(job_id) DO NOTHING",
                (identity.job_id, identity.customer_id, identity.project_id, "queued", self.adapter._jsonb(payload)),
            )
            existing = self._read(connection, identity, lock=True)
            if existing is None or existing["limits"] != asdict(limits):
                raise JobConflict("worker_job_enqueue_conflict")
            return existing

    def _change(self, identity: JobIdentity, operation: Callable):
        with self.adapter._connect() as connection:
            payload = self._read(connection, identity, lock=True)
            if payload is None:
                raise JobConflict("worker_job_missing")
            # Read database time after acquiring ownership lock, not before waiting.
            result, changed = operation(payload, self._now(connection))
            if changed:
                connection.execute(
                    "UPDATE client_jobs SET status=%s,payload=%s,updated_at=clock_timestamp() "
                    "WHERE job_id=%s AND customer_id=%s AND project_id=%s AND payload->>'workflow'=%s",
                    (payload["status"], self.adapter._jsonb(payload), *self._scope(identity)),
                )
            return result

    def claim(self, identity: JobIdentity, worker_id: str) -> dict | None:
        if not isinstance(worker_id, str) or not worker_id.strip() or len(worker_id) > 256:
            raise ValueError("worker_id_invalid")

        def operation(payload, now):
            if payload["status"] in TERMINAL:
                return None, False
            if now >= payload["deadline_epoch"]:
                payload["status"] = "budget_exhausted"
                return None, True
            if payload["status"] == "running" and now < payload["lease_until_epoch"]:
                return None, False
            if payload["attempts"] >= payload["limits"]["max_attempts"]:
                payload["status"] = "failed"
                payload["failure_code"] = "attempt_budget_exhausted"
                return None, True
            if payload["status"] not in {"running", "queued"}:
                raise JobConflict("worker_job_status_invalid")
            payload.update(status="running", attempts=payload["attempts"] + 1,
                           worker_id=worker_id, lease_id=uuid4().hex,
                           lease_until_epoch=min(now + payload["limits"]["lease_seconds"], payload["deadline_epoch"]))
            return payload, True

        return self._change(identity, operation)

    @staticmethod
    def _owned(payload, lease_id, now):
        if (not lease_id or payload["status"] != "running" or payload["lease_id"] != lease_id
                or now >= min(payload["lease_until_epoch"], payload["deadline_epoch"])):
            raise JobConflict("worker_job_lease_conflict")

    def heartbeat(self, identity: JobIdentity, lease_id: str) -> dict:
        def operation(payload, now):
            self._owned(payload, lease_id, now)
            payload["lease_until_epoch"] = min(now + payload["limits"]["lease_seconds"], payload["deadline_epoch"])
            return payload, True
        return self._change(identity, operation)

    def complete(self, identity: JobIdentity, lease_id: str, receipt_sha256: str) -> dict:
        """Bind an already retained/validated receipt; does not validate its bytes."""
        if not isinstance(receipt_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", receipt_sha256):
            raise ValueError("worker_job_receipt_digest_invalid")

        def operation(payload, now):
            if (payload["status"] == "completed" and payload["lease_id"] == lease_id
                    and payload["receipt_sha256"] == receipt_sha256):
                return payload, False
            self._owned(payload, lease_id, now)
            payload.update(status="completed", receipt_sha256=receipt_sha256)
            return payload, True
        return self._change(identity, operation)

    def fail(self, identity: JobIdentity, lease_id: str, failure_code: str, *, retryable: bool) -> dict:
        if not isinstance(failure_code, str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", failure_code):
            raise ValueError("worker_job_failure_code_invalid")
        if type(retryable) is not bool:
            raise ValueError("worker_job_retryability_invalid")

        def operation(payload, now):
            self._owned(payload, lease_id, now)
            payload.update(status=("queued" if retryable and payload["attempts"] < payload["limits"]["max_attempts"] else "failed"),
                           failure_code=failure_code, lease_until_epoch=0)
            return payload, True
        return self._change(identity, operation)

    def cancel(self, identity: JobIdentity) -> bool:
        def operation(payload, _now):
            if payload["status"] in TERMINAL:
                return payload["status"] == "cancelled", False
            payload.update(status="cancelled", lease_until_epoch=0)
            return True, True
        return self._change(identity, operation)
