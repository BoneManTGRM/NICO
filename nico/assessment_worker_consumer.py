"""Consume one already-authorized durable job through its dedicated HTTP API.

Source provisioning and dispatch authority are separate from this consumer.
The local Git adapter reads preprovisioned objects only. It never fetches,
checks out or executes repository commands, and does not activate intake.
"""
from __future__ import annotations

from copy import deepcopy
import base64
import gzip
import hashlib
import json
import math
import multiprocessing
from pathlib import Path
import re
import tempfile
import time
from urllib.parse import urlsplit

import requests

from nico.assessment_worker_auth import JOB_ID
from nico.assessment_worker_container import run_isolated_cppcheck
from nico.assessment_worker_jobs import JobIdentity, _digest
from nico.assessment_worker_receipts import canonical_bytes, validate_contract, validate_receipt

TRANSPORT_SECONDS = 12
ARTIFACT_TRANSPORT_SECONDS = 30
MAX_ARTIFACT_REQUEST_BYTES = 12 * 1024 * 1024
MAX_RESPONSE_BYTES = 5 * 1024 * 1024


def _transport_child(destination, transport, operation, payload):
    """Only bounded JSON results cross back; credentials/errors are never logged."""
    try:
        value = {"ok": True, "response": transport._post_inline(operation, payload)}
    except Exception as error:
        code = str(error)
        if not re.fullmatch(r"worker_[a-z_]{1,80}", code):
            code = "worker_transport_unavailable"
        value = {"ok": False, "error": code}
    raw = canonical_bytes(value)
    if len(raw) > MAX_RESPONSE_BYTES:
        raw = b'{"ok":false,"error":"worker_response_size_invalid"}'
    Path(destination).write_bytes(raw)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("worker_response_duplicate_member")
        result[key] = value
    return result


class WorkerTransport:
    """Each HTTP operation runs in a spawned, killable process.

    The dedicated worker supplies a picklable token provider and optional
    requests session. No redirects, ambient credentials or response logging.
    """

    def __init__(self, backend, job_id, release_revision, token_provider, *, session=None):
        parsed = urlsplit(backend)
        if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
                or parsed.query or parsed.fragment or parsed.path not in {"", "/"}
                or any(char.isspace() for char in backend)
                or not JOB_ID.fullmatch(job_id)
                or not re.fullmatch(r"(?:[0-9a-f]{40}|[0-9a-f]{64})", release_revision)):
            raise ValueError("worker_transport_binding_invalid")
        self.url = backend.rstrip("/") + "/internal/assessment-workers/" + job_id
        self.job_id, self.release_revision = job_id, release_revision
        self.token_provider = token_provider
        self.session = session if session is not None else requests.Session()
        self.session.trust_env = False

    def post(self, operation, payload, *, deadline=None):
        seconds = ARTIFACT_TRANSPORT_SECONDS if operation == "artifact" else TRANSPORT_SECONDS
        limit = time.monotonic() + seconds
        if deadline is not None:
            limit = min(limit, deadline)
        if time.monotonic() >= limit:
            raise ValueError("worker_response_deadline")
        # A file is read only after child exit; a partial IPC frame cannot block
        # the parent. The private directory and output are always removed.
        with tempfile.TemporaryDirectory(prefix="nico-worker-http-") as temporary:
            destination = Path(temporary) / "response.json"
            process = multiprocessing.get_context("spawn").Process(
                target=_transport_child, args=(destination, self, operation, payload))
            try:
                process.start()
                process.join(max(0, limit - time.monotonic()))
                if process.is_alive() or time.monotonic() >= limit:
                    raise ValueError("worker_response_deadline")
                if process.exitcode != 0 or not destination.is_file():
                    raise ValueError("worker_transport_unavailable")
                with destination.open("rb") as handle:
                    raw = handle.read(MAX_RESPONSE_BYTES + 1)
                if len(raw) > MAX_RESPONSE_BYTES:
                    raise ValueError("worker_response_size_invalid")
                result = json.loads(raw)
                if time.monotonic() >= limit:
                    raise ValueError("worker_response_deadline")
                if not result["ok"]:
                    raise ValueError(result["error"])
                return result["response"]
            finally:
                if process.pid is not None:
                    if process.is_alive():
                        process.terminate()
                        process.join(0.25)
                    if process.is_alive():
                        process.kill()
                    process.join(1)
                    process.close()

    def put_artifact(self, lease_id, key, raw):
        if (not isinstance(lease_id, str) or re.fullmatch(r"[0-9a-f]{32}", lease_id) is None
                or key not in {"project-compilation-database", "project-generated-context", "project-compiler-evidence",
                    "project-static-environment", "project-static-evidence", "project-static-clang-fallback"}
                or not isinstance(raw, bytes) or not 1 <= len(raw) <= 64 * 1024 * 1024):
            raise ValueError("worker_artifact_request_invalid")
        compressed = gzip.compress(raw, compresslevel=9, mtime=0)
        if len(compressed) > 8 * 1024 * 1024:
            raise ValueError("worker_artifact_compressed_limit")
        artifact = {"key": key, "raw_sha256": hashlib.sha256(raw).hexdigest(), "raw_bytes": len(raw),
            "gzip_sha256": hashlib.sha256(compressed).hexdigest(), "gzip_bytes": len(compressed),
            "compressed": base64.b64encode(compressed).decode("ascii")}
        response = self.post("artifact", {"lease_id": lease_id, "artifact": artifact})
        reference = response.get("artifact") if isinstance(response, dict) else None
        expected = {"key": key, "sha256": artifact["raw_sha256"], "gzip_sha256": artifact["gzip_sha256"],
                    "retained_bytes": len(raw), "gzip_bytes": len(compressed), "storage_backend": "postgres"}
        if (not isinstance(reference, dict) or any(reference.get(k) != v for k, v in expected.items())
                or not isinstance(reference.get("artifact_id"), str)
                or not reference["artifact_id"].startswith("scanartifact_")):
            raise ValueError("worker_artifact_reference_invalid")
        return reference

    def _post_inline(self, operation, payload):
        if operation not in {"claim", "heartbeat", "receipt", "artifact", "fail"} or not isinstance(payload, dict):
            raise ValueError("worker_operation_invalid")
        body = canonical_bytes(payload)
        maximum = (MAX_ARTIFACT_REQUEST_BYTES if operation == "artifact" else
                   8 * 1024 * 1024 if operation == "receipt" else 4096)
        if len(body) > maximum:
            raise ValueError("worker_request_size_invalid")
        token = self.token_provider()
        if not isinstance(token, str) or not token or len(token) > 16384 or any(c.isspace() for c in token):
            raise ValueError("worker_credential_invalid")
        arguments = {"data": body, "headers": {"Authorization": "Bearer " + token,
            "Content-Type": "application/json", "Accept": "application/json"},
            "allow_redirects": False, "stream": True, "timeout": (2, 5)}
        deadline = time.monotonic() + (ARTIFACT_TRANSPORT_SECONDS if operation == "artifact" else TRANSPORT_SECONDS)
        # Lost claim/receipt response: retain exactly the same token, body and
        # nonce for one transport retry. HTTP refusals are never retried.
        for attempt in range(2):
            response = None
            try:
                if time.monotonic() >= deadline:
                    raise ValueError("worker_response_deadline")
                response = self.session.post(self.url + "/" + operation, **arguments)
                if response.status_code != 200:
                    raise ValueError("worker_http_rejected")
                raw = bytearray()
                for chunk in response.iter_content(chunk_size=65536):
                    if time.monotonic() >= deadline:
                        raise ValueError("worker_response_deadline")
                    if len(raw) + len(chunk) > MAX_RESPONSE_BYTES:
                        raise ValueError("worker_response_size_invalid")
                    raw.extend(chunk)
                if time.monotonic() >= deadline:
                    raise ValueError("worker_response_deadline")
                value = json.loads(raw, object_pairs_hook=_unique_object,
                    parse_constant=lambda _: (_ for _ in ()).throw(ValueError("worker_response_nonfinite")))
                if not isinstance(value, dict):
                    raise ValueError("worker_response_invalid")
                return value
            except (requests.ConnectionError, requests.Timeout, requests.exceptions.ChunkedEncodingError):
                if attempt:
                    raise ValueError("worker_transport_unavailable") from None
            finally:
                if response is not None:
                    response.close()
        raise ValueError("worker_transport_unavailable")


def validate_claim(record, *, job_id, release_revision):
    try:
        identity = JobIdentity(**record["identity"])
        contract = validate_contract(record["contract"])
        if (identity.job_id != job_id or record["job_id"] != job_id
                or identity.release_revision != release_revision
                or identity.contract_sha256 != _digest(contract)
                or record["limits"] != contract["limits"]
                or record["source_access"] != {"mode": "anonymous_public", "credential_used": False}
                or record["source_access"]["credential_used"] is not False
                or not re.fullmatch(r"github:[1-9][0-9]{0,19}:[1-9][0-9]{0,19}:[1-9][0-9]{0,19}", record["worker_id"])
                or not re.fullmatch(r"[0-9a-f]{32}", record["lease_id"])
                or record["status"] != "running" or record.get("receipt_sha256") != ""
                or type(record["attempts"]) is not int
                or not 1 <= record["attempts"] <= contract["limits"]["max_attempts"]):
            raise ValueError("worker_claim_binding_invalid")
        now = time.time()
        for key in ("deadline_epoch", "lease_until_epoch"):
            if type(record[key]) not in {int, float} or not math.isfinite(record[key]):
                raise ValueError("worker_claim_deadline_invalid")
        if not now < record["lease_until_epoch"] <= record["deadline_epoch"] <= now + contract["limits"]["wall_seconds"] + 2:
            raise ValueError("worker_claim_deadline_invalid")
    except (KeyError, TypeError, AttributeError):
        raise ValueError("worker_claim_binding_invalid") from None
    return deepcopy(record)


def local_git_inputs(git_dir: Path, expected_tree_sha: str):
    """Trusted caller provisions the Git database/tree; no target network here."""
    git_dir = Path(git_dir).resolve(strict=True)

    def acquire(job, root, checkpoint):
        from nico.snapshot_repository_evidence import materialize_exact_git_inputs
        remaining = int(job["deadline_epoch"] - time.time())
        if remaining < 1:
            raise ValueError("worker_local_deadline")
        destination = root / "source"
        evidence = materialize_exact_git_inputs(git_dir=git_dir, commit_sha=job["identity"]["revision"],
            expected_tree_sha=expected_tree_sha, inputs=job["contract"]["targets"], destination=destination,
            max_files=20000, max_file_bytes=16 * 1024 * 1024,
            max_total_bytes=(job['contract']['configuration']['source_byte_limit']
                if job['contract']['profile'] == 'cpp-full-project-v1' else 16 * 1024 * 1024),
            timeout_seconds=min(300, remaining), checkpoint=checkpoint)
        return destination, evidence
    return acquire


def _receipt(job, result, *, acquisition=None):
    native = result.get("native")
    targets = job["contract"]["targets"]
    schema = "nico.worker-native-receipt.v1"
    if job['contract']['profile'] == 'cpp-configure-first-v2':
        schema = 'nico.worker-native-receipt.v7'
        targets = result.get("derived_targets")
        if not isinstance(targets, dict) or not targets:
            raise ValueError("worker_configure_first_population_missing")
    elif job['contract']['profile'] == 'cpp-full-project-v1':
        schema = 'nico.worker-native-receipt.v6'
    elif job['contract']['profile'] == 'cpp-runtime-cases-v1':
        schema = 'nico.worker-native-receipt.v5'
    elif job['contract']['profile'] == 'cpp-sanitized-v1':
        schema = 'nico.worker-native-receipt.v4'
    elif job['contract']['profile'] == 'cpp-configured-v1':
        schema = 'nico.worker-native-receipt.v3'
    elif isinstance(result.get("raw_streams"), dict):
        schema = "nico.worker-native-receipt.v2"
        native = {**result["execution"], **result["raw_streams"], "encoding": "base64"}
    elif result.get("native_decoding_failed"):
        raise ValueError("worker_native_failure_evidence_missing")
    plan = job["contract"]
    receipt = {"schema": schema, "identity": job["identity"], "lease_id": job["lease_id"],
        "worker_id": job["worker_id"], "image_digest": plan["image_digest"],
        "tool_version": plan["tool_version"], "configuration_sha256": _digest(plan["configuration"]),
        "target_hashes": targets, "native": native, "native_sha256": _digest(native)}
    if isinstance(acquisition, dict) and acquisition.get('schema') == 'nico.github_https_tree_materialization.v2':
        excluded=acquisition.get('excluded_entries') or []
        receipt['provisioning']={'schema':'nico.worker-provisioning.v2','source_method':acquisition['schema'],
            'commit_sha':acquisition['commit_sha'],'tree_sha':acquisition['tree_sha'],
            'population_sha256':acquisition['population_sha256'],'required_count':acquisition['required_count'],
            'materialized_count':acquisition['materialized_count'],'source_bytes':acquisition['source_bytes'],
            'freeze_point':acquisition['freeze_point'],'excluded_count':len(excluded),
            'excluded_sha256':hashlib.sha256(canonical_bytes(excluded)).hexdigest(),
            'image_manifest':acquisition['image_manifest'],'image_config_id':acquisition['image_config_id']}
    elif isinstance(acquisition, dict) and acquisition.get('schema') == 'nico.github_https_input_materialization.v1':
        receipt['provisioning'] = {key: acquisition[key] for key in (
            'commit_sha', 'tree_sha', 'population_sha256', 'required_count', 'materialized_count',
            'source_bytes', 'image_manifest', 'image_config_id')}
        receipt['provisioning'].update(schema='nico.worker-provisioning.v1', source_method=acquisition['schema'])
    return receipt


def consume_one_job(transport, *, acquire, execute=run_isolated_cppcheck, configure_execute=None):
    job = validate_claim(transport.post("claim", {}), job_id=transport.job_id,
                         release_revision=transport.release_revision)
    identity = JobIdentity(**job["identity"])
    initial = time.monotonic()
    deadline = initial + max(0, job["deadline_epoch"] - time.time())
    lease_deadline = initial + max(0, job["lease_until_epoch"] - time.time())
    next_heartbeat = initial + min(5, job["limits"]["lease_seconds"] / 3)
    owned = True
    immutable = ("job_id", "identity", "contract", "limits", "attempts", "deadline_epoch",
                 "lease_id", "worker_id", "source_access")

    def checkpoint(force=False):
        nonlocal next_heartbeat, lease_deadline, owned
        now = time.monotonic()
        if now >= deadline:
            owned = False
            raise ValueError("worker_local_deadline")
        if now >= lease_deadline:
            owned = False
            raise ValueError("worker_local_lease_expired")
        if force or now >= next_heartbeat:
            try:
                beat = validate_claim(transport.post("heartbeat", {"lease_id": job["lease_id"]},
                    deadline=min(deadline, lease_deadline)),
                    job_id=transport.job_id, release_revision=transport.release_revision)
                if any(beat[key] != job[key] for key in immutable):
                    raise ValueError("worker_heartbeat_binding_invalid")
                lease_deadline = min(deadline, time.monotonic() + max(0, beat["lease_until_epoch"] - time.time()))
                next_heartbeat = time.monotonic() + min(5, job["limits"]["lease_seconds"] / 3)
            except Exception:
                owned = False
                raise

    try:
        with tempfile.TemporaryDirectory(prefix="nico-worker-job-") as temporary:
            checkpoint()
            source, acquisition = acquire(deepcopy(job), Path(temporary), checkpoint)
            checkpoint()
            configure_first = job["contract"]["profile"] == "cpp-configure-first-v2"
            remaining = int(min(2400 if configure_first else 300, deadline - time.monotonic() - 2))
            if remaining < 1:
                raise ValueError("worker_local_deadline")
            if configure_first:
                if configure_execute is None:
                    from nico.assessment_cpp_configure_first_execution import run_configure_first
                    configure_execute = run_configure_first
                result = configure_execute(job["contract"], source, acquisition,
                    checkpoint=checkpoint, timeout_seconds=remaining,
                    retain_artifact=lambda key, raw: transport.put_artifact(job["lease_id"], key, raw))
            else:
                result = execute(job["contract"], source, checkpoint=checkpoint, timeout_seconds=remaining)
            checkpoint(force=True)
            receipt = _receipt(job, result, acquisition=acquisition)
            raw, record, _ = validate_receipt(identity, job["contract"], job["lease_id"], job["worker_id"], receipt)
            receipt_hash = hashlib.sha256(raw).hexdigest()
            terminal = transport.post("receipt", {"lease_id": job["lease_id"], "receipt": receipt},
                                      deadline=min(deadline, lease_deadline))
            if (terminal.get("status") != "completed" or terminal.get("receipt_sha256") != receipt_hash
                    or any(terminal.get(key) != job[key] for key in immutable)):
                owned = False
                raise ValueError("worker_terminal_binding_invalid")
            return {"job_id": job["job_id"], "receipt_sha256": receipt_hash, "scanner_status": record["status"],
                    "receipt": receipt, "canonical_record": record, "acquisition": acquisition}
    except Exception:
        if owned and time.monotonic() < min(deadline, lease_deadline):
            try:
                transport.post("fail", {"lease_id": job["lease_id"], "failure_code": "worker_consumer_failed",
                                        "retryable": False}, deadline=min(deadline, lease_deadline))
            except Exception:
                pass  # original failure is authoritative; server lease still fences this owner
        raise
