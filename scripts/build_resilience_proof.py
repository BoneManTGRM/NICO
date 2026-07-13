from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

import nico.operational_observability as observability
from nico.scanner_recovery import (
    RECOVERY_REQUIRED_STATUS,
    reconcile_interrupted_scanner_runs,
    resume_interrupted_scanner_run,
)
from nico.scanner_recovery_status import scanner_recovery_status
from nico.storage import Storage


class ResilienceProofFailure(RuntimeError):
    """Raised when a resilience assertion cannot be proved safely."""


class _FailingEventStore:
    def status(self) -> dict[str, Any]:
        return {
            "adapter": "postgres",
            "persistence_available": True,
            "database_url_configured": True,
        }

    def audit(self, *_args: Any, **_kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("synthetic event write failure")

    def list(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        raise RuntimeError("synthetic event read failure")


class _NoopThread:
    starts = 0

    def __init__(self, *, target: Callable[..., Any], args: tuple[Any, ...], daemon: bool) -> None:
        self.target = target
        self.args = args
        self.daemon = daemon

    def start(self) -> None:
        type(self).starts += 1


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def safe_error(value: Any, database_url: str = "") -> str:
    text = str(value or "")[:1000]
    if database_url:
        text = text.replace(database_url, "[DATABASE_URL_REDACTED]")
    text = re.sub(r"postgres(?:ql)?://[^\s'\"]+", "[DATABASE_URL_REDACTED]", text, flags=re.IGNORECASE)
    return text[:500]


def synthetic_scanner_record(suffix: str, *, now: datetime) -> tuple[str, str, dict[str, Any]]:
    token = re.sub(r"[^A-Za-z0-9]", "", suffix)[:24] or uuid4().hex[:12]
    scan_id = f"scan_resilience_{token}"
    run_id = f"fullrun_resilience_{token}"
    stale_at = (now - timedelta(hours=2)).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    return scan_id, run_id, {
        "scan_id": scan_id,
        "run_id": run_id,
        "customer_id": f"resilience_customer_{token}",
        "project_id": f"resilience_project_{token}",
        "repository": "BoneManTGRM/NICO",
        "status": "running",
        "created_at": stale_at,
        "updated_at": stale_at,
        "authorized": True,
        "authorized_by": "synthetic_resilience_ci",
        "authorization_scope": "authorized synthetic scanner recovery proof only",
        "tools_requested": ["gitleaks"],
        "draft_pr_creation_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "synthetic": True,
    }


def prove_event_pipeline_degradation() -> dict[str, Any]:
    original_store = observability.STORE
    original_write_failures = observability._EVENT_WRITE_FAILURES
    original_read_failures = observability._EVENT_READ_FAILURES
    try:
        observability.STORE = _FailingEventStore()
        observability._EVENT_WRITE_FAILURES = 0
        observability._EVENT_READ_FAILURES = 0
        emitted = observability.emit_operational_event(
            correlation_id="resilience-event-12345678",
            event_name="resilience.synthetic_failure",
            severity="p2",
            outcome="degraded",
            metadata={
                "safe": "retained",
                "api_key": "must-not-appear",
                "authorization": "Bearer must-not-appear",
            },
        )
        events = observability.recent_operational_events(limit=10)
        pipeline = observability.event_pipeline_status()
        rendered = repr(emitted)
        if emitted.get("stored") is not False:
            raise ResilienceProofFailure("Synthetic event write failure was not disclosed.")
        if events != []:
            raise ResilienceProofFailure("Synthetic event read failure did not return a safe empty inventory.")
        if pipeline.get("status") != "degraded":
            raise ResilienceProofFailure("Event pipeline did not report degraded status after read/write failure.")
        if pipeline.get("write_failures") != 1 or pipeline.get("read_failures") != 1:
            raise ResilienceProofFailure("Event pipeline failure counters were not preserved.")
        if "must-not-appear" in rendered:
            raise ResilienceProofFailure("Sensitive event metadata was not redacted.")
        return {
            "status": "passed",
            "event_stored": False,
            "safe_read_count": len(events),
            "pipeline_status": pipeline.get("status"),
            "write_failures": pipeline.get("write_failures"),
            "read_failures": pipeline.get("read_failures"),
            "storage_adapter": pipeline.get("storage_adapter"),
            "persistence_available": pipeline.get("persistence_available"),
            "sensitive_metadata_redacted": True,
        }
    finally:
        observability.STORE = original_store
        observability._EVENT_WRITE_FAILURES = original_write_failures
        observability._EVENT_READ_FAILURES = original_read_failures


def _postgres_storage(database_url: str) -> Storage:
    os.environ["DATABASE_URL"] = database_url
    os.environ["NICO_DISABLE_POSTGRES"] = "false"
    storage = Storage()
    status = storage.status()
    if status.get("adapter") != "postgres" or status.get("persistence_available") is not True:
        raise ResilienceProofFailure("Configured storage did not start durable Postgres persistence.")
    return storage


def _memory_storage() -> Storage:
    prior_url = os.environ.pop("DATABASE_URL", None)
    prior_disable = os.environ.get("NICO_DISABLE_POSTGRES")
    try:
        os.environ["NICO_DISABLE_POSTGRES"] = "false"
        storage = Storage()
    finally:
        if prior_url is not None:
            os.environ["DATABASE_URL"] = prior_url
        if prior_disable is None:
            os.environ.pop("NICO_DISABLE_POSTGRES", None)
        else:
            os.environ["NICO_DISABLE_POSTGRES"] = prior_disable
    return storage


def build_resilience_proof(database_url: str, *, suffix: str = "") -> dict[str, Any]:
    if not str(database_url or "").strip():
        raise ResilienceProofFailure("A Postgres database URL is required for the resilience proof.")
    now = datetime.now(timezone.utc).replace(microsecond=0)
    scan_id, run_id, scanner_record = synthetic_scanner_record(suffix or uuid4().hex[:12], now=now)

    writer = _postgres_storage(database_url)
    writer.put("scanner_runs", scan_id, scanner_record)
    reconciliation = reconcile_interrupted_scanner_runs(
        store=writer,
        stale_seconds=60,
        now=now,
    )
    if reconciliation.get("reconciled") != 1 or reconciliation.get("recovery_required") != 1:
        raise ResilienceProofFailure("Stale scanner run was not reconciled to recovery-required state.")
    if reconciliation.get("automatic_resume") is not False:
        raise ResilienceProofFailure("Scanner reconciliation incorrectly allowed automatic resume.")

    reader = _postgres_storage(database_url)
    recovered = reader.get("scanner_runs", scan_id)
    if not isinstance(recovered, dict) or recovered.get("status") != RECOVERY_REQUIRED_STATUS:
        raise ResilienceProofFailure("Recovery-required state did not survive a fresh storage adapter.")
    if recovered.get("scan_id") != scan_id or recovered.get("run_id") != run_id:
        raise ResilienceProofFailure("Scanner or parent-run identity changed during restart recovery.")
    recovery_status = scanner_recovery_status(reader)
    if recovery_status.get("status") != "attention_required" or recovery_status.get("recovery_required") != 1:
        raise ResilienceProofFailure("Recovery status did not expose the persisted interrupted scanner run.")

    _NoopThread.starts = 0
    resume = resume_interrupted_scanner_run(
        scan_id,
        actor="synthetic_ci_operator",
        store=reader,
        thread_factory=_NoopThread,
    )
    if resume.get("status") != "queued" or resume.get("idempotent_reuse") is not False:
        raise ResilienceProofFailure("Explicit same-ID scanner resume was not claimed exactly once.")
    if (resume.get("resume") or {}).get("same_scan_id") is not True:
        raise ResilienceProofFailure("Scanner resume did not preserve the exact scan identity.")
    if _NoopThread.starts != 1:
        raise ResilienceProofFailure("Explicit scanner resume did not start exactly one continuation worker.")
    duplicate = resume_interrupted_scanner_run(
        scan_id,
        actor="synthetic_ci_operator",
        store=reader,
        thread_factory=_NoopThread,
    )
    if duplicate.get("status") != "queued" or duplicate.get("idempotent_reuse") is not True:
        raise ResilienceProofFailure("Duplicate scanner resume did not reuse the existing same-ID continuation.")
    if _NoopThread.starts != 1:
        raise ResilienceProofFailure("Duplicate scanner resume started an additional continuation worker.")

    verifier = _postgres_storage(database_url)
    persisted = verifier.get("scanner_runs", scan_id)
    if not isinstance(persisted, dict) or persisted.get("status") != "queued":
        raise ResilienceProofFailure("Explicit resume state did not survive a second fresh storage adapter.")
    if persisted.get("scan_id") != scan_id or persisted.get("run_id") != run_id:
        raise ResilienceProofFailure("Persisted resume state changed scanner or parent-run identity.")
    if persisted.get("human_review_required") is not True or persisted.get("client_delivery_allowed") is not False:
        raise ResilienceProofFailure("Recovery transition weakened review or delivery boundaries.")

    memory = _memory_storage()
    memory_reconciliation = reconcile_interrupted_scanner_runs(store=memory, stale_seconds=60, now=now)
    memory_status = scanner_recovery_status(memory)
    if memory_reconciliation.get("status") != "blocked":
        raise ResilienceProofFailure("Memory fallback did not block durable scanner recovery.")
    if "durable_postgres_required" not in (memory_reconciliation.get("blockers") or []):
        raise ResilienceProofFailure("Memory fallback did not disclose the durable-Postgres blocker.")
    if memory_status.get("status") != "unavailable" or memory_status.get("clear") is not False:
        raise ResilienceProofFailure("Memory fallback incorrectly reported scanner recovery as clear.")

    event_degradation = prove_event_pipeline_degradation()
    proof = {
        "durable_postgres_active": True,
        "stale_scanner_reconciled_same_id": True,
        "recovery_state_survived_fresh_adapter": True,
        "recovery_inventory_requires_attention": True,
        "explicit_operator_resume_only": True,
        "duplicate_resume_reused_same_id": True,
        "post_resume_state_survived_second_restart": True,
        "memory_fallback_blocks_durable_recovery": True,
        "telemetry_write_failure_degrades_safely": True,
        "telemetry_read_failure_degrades_safely": True,
        "sensitive_telemetry_metadata_redacted": True,
        "human_review_boundary_preserved": True,
        "client_delivery_remains_blocked": True,
    }
    return {
        "artifact_schema": "nico.resilience_proof.v1",
        "status": "passed",
        "evidence_kind": "synthetic_restart_recovery_observability_proof",
        "synthetic": True,
        "live_production_claim": False,
        "generated_at": utc_now(),
        "identity": {
            "scan_id": scan_id,
            "run_id": run_id,
            "customer_id": scanner_record["customer_id"],
            "project_id": scanner_record["project_id"],
        },
        "reconciliation": {
            "status": reconciliation.get("status"),
            "reconciled": reconciliation.get("reconciled"),
            "recovery_required": reconciliation.get("recovery_required"),
            "automatic_resume": reconciliation.get("automatic_resume"),
            "human_review_required": reconciliation.get("human_review_required"),
            "client_delivery_allowed": reconciliation.get("client_delivery_allowed"),
        },
        "resume": {
            "status": resume.get("status"),
            "same_scan_id": (resume.get("resume") or {}).get("same_scan_id"),
            "attempt": (resume.get("resume") or {}).get("attempt"),
            "duplicate_status": duplicate.get("status"),
            "duplicate_idempotent_reuse": duplicate.get("idempotent_reuse"),
            "continuation_thread_starts": _NoopThread.starts,
            "automatic_resume": resume.get("automatic_resume"),
            "human_review_required": resume.get("human_review_required"),
            "client_delivery_allowed": resume.get("client_delivery_allowed"),
        },
        "memory_fallback": {
            "adapter": memory.status().get("adapter"),
            "persistence_available": memory.status().get("persistence_available"),
            "reconciliation_status": memory_reconciliation.get("status"),
            "blockers": memory_reconciliation.get("blockers"),
            "recovery_status": memory_status.get("status"),
            "clear": memory_status.get("clear"),
        },
        "event_pipeline_degradation": event_degradation,
        "proof": proof,
        "guardrail": "This synthetic proof exercises durable restart recovery and bounded degradation behavior. It is not a live production restart, assessment result, automatic repair approval, or client-delivery authorization.",
    }


def write_evidence(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a bounded synthetic NICO restart, recovery, observability, and graceful-degradation proof.")
    parser.add_argument("--database-url", default=os.getenv("NICO_TEST_DATABASE_URL", ""))
    parser.add_argument("--suffix", default="")
    parser.add_argument("--output", default="audit-results/resilience-proof.json")
    args = parser.parse_args()
    try:
        payload = build_resilience_proof(args.database_url, suffix=args.suffix)
        write_evidence(Path(args.output), payload)
        print(json.dumps({"status": "passed", "output": args.output}, sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "artifact_schema": "nico.resilience_proof.v1",
            "status": "failed",
            "evidence_kind": "synthetic_restart_recovery_observability_proof",
            "synthetic": True,
            "live_production_claim": False,
            "error_type": type(exc).__name__[:120],
            "error": safe_error(exc, args.database_url),
            "generated_at": utc_now(),
        }
        write_evidence(Path(args.output), failure)
        print(json.dumps({"status": "failed", "output": args.output, "error_type": type(exc).__name__}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
