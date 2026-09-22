"""Bounded worker protocol over the existing durable job and scanner stores."""
from __future__ import annotations

import json
import re
import asyncio
from threading import BoundedSemaphore

from fastapi import FastAPI, HTTPException, Request
from starlette.concurrency import run_in_threadpool

from nico.assessment_worker_auth import JOB_ID, verify_worker_token
from nico.assessment_worker_jobs import JobConflict, JobIdentity, WorkerJobs
from nico.storage import STORE, PostgresAdapter

PREFIX = "/internal/assessment-workers"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
_ACTIVE_REQUESTS = BoundedSemaphore(2)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_member")
        result[key] = value
    return result


def _invoke(operation, authority, body):
    if not isinstance(STORE.adapter, PostgresAdapter):
        raise HTTPException(503, "worker_durable_storage_unavailable")
    jobs = WorkerJobs(STORE.adapter)
    job = jobs.get_by_id(authority.job_id)
    if job is None:
        raise HTTPException(404, "worker_job_unavailable")
    if not isinstance(job.get("contract"), dict):
        raise HTTPException(409, "worker_contract_missing")
    identity = JobIdentity(**job["identity"])
    if identity.release_revision != authority.release_revision:
        raise HTTPException(409, "worker_release_mismatch")
    if operation == "claim":
        if body:
            raise ValueError("worker_request_invalid")
        result = jobs.claim(identity, authority.worker_id, claim_nonce=authority.nonce_sha256)
        if result is None:
            raise JobConflict("worker_job_not_claimable")
    else:
        lease = body.get("lease_id")
        if not isinstance(lease, str) or not re.fullmatch(r"[0-9a-f]{32}", lease):
            raise ValueError("worker_lease_invalid")
        if operation == "heartbeat" and set(body) == {"lease_id"}:
            result = jobs.heartbeat(identity, lease, worker_id=authority.worker_id)
        elif operation == "fail" and set(body) == {"lease_id", "failure_code", "retryable"}:
            result = jobs.fail(identity, lease, body["failure_code"], retryable=body["retryable"],
                               worker_id=authority.worker_id)
        elif operation == "receipt" and set(body) == {"lease_id", "receipt"}:
            from nico.assessment_worker_receipts import publish_receipt
            result = publish_receipt(jobs, identity, lease, authority.worker_id, body["receipt"])
        else:
            raise ValueError("worker_request_invalid")
    # Return only the job's immutable dispatch contract, ownership and terminal receipt.
    return {key: result[key] for key in ("job_id", "identity", "contract", "limits", "status",
        "attempts", "deadline_epoch", "lease_id", "lease_until_epoch", "receipt_sha256",
        "worker_id", "source_access") if key in result}


async def _endpoint(request: Request, job_id: str, operation: str):
    if not JOB_ID.fullmatch(job_id) or operation not in {"claim", "heartbeat", "receipt", "fail"}:
        raise HTTPException(404, "worker_route_unavailable")
    authorization = request.headers.get("authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(401, "worker_authentication_required")
    if not _ACTIVE_REQUESTS.acquire(blocking=False):
        raise HTTPException(429, "worker_request_capacity_exhausted")
    try:
        return await _authenticated_request(request, job_id, operation, authorization[7:])
    finally:
        _ACTIVE_REQUESTS.release()


async def _authenticated_request(request, job_id, operation, token):
    try:
        authority = await run_in_threadpool(verify_worker_token, token, job_id)
    except ValueError:
        raise HTTPException(401, "worker_authentication_invalid") from None
    limit = MAX_REQUEST_BYTES if operation == "receipt" else 4096
    declared = request.headers.get("content-length")
    if declared is not None and (len(declared) > 10 or not declared.isdecimal() or int(declared) > limit):
        raise HTTPException(413, "worker_request_too_large")
    if request.headers.get("content-encoding", "identity") != "identity":
        raise HTTPException(415, "worker_request_encoding_unsupported")
    raw = bytearray()
    try:
        async with asyncio.timeout(15):
            async for chunk in request.stream():
                if len(raw) + len(chunk) > limit:
                    raise HTTPException(413, "worker_request_too_large")
                raw.extend(chunk)
    except TimeoutError:
        raise HTTPException(408, "worker_request_body_timeout") from None
    try:
        body = json.loads(raw, object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite_json")))
        if not isinstance(body, dict):
            raise ValueError("worker_request_invalid")
        return await run_in_threadpool(_invoke, operation, authority, body)
    except JobConflict:
        raise HTTPException(409, "worker_job_conflict") from None
    except (ValueError, TypeError, RecursionError):
        raise HTTPException(422, "worker_receipt_or_request_invalid") from None


def install_assessment_worker_api(app: FastAPI):
    path = PREFIX + "/{job_id}/{operation}"
    if not any(getattr(route, "path", "") == path for route in app.routes):
        app.add_api_route(path, _endpoint, methods=["POST"], include_in_schema=False)
