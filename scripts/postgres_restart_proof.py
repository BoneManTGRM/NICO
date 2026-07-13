from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol
from uuid import uuid4

from nico.storage import PostgresAdapter


class RestartProofFailure(RuntimeError):
    """Raised when a durable-storage assertion cannot be proved."""


class Adapter(Protocol):
    def status(self) -> dict[str, Any]: ...
    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...
    def get(self, table: str, item_id: str) -> dict[str, Any] | None: ...
    def list(
        self,
        table: str,
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]: ...


AdapterFactory = Callable[[str], Adapter]


@dataclass(frozen=True)
class ProofIdentity:
    suffix: str
    customer_id: str
    project_id: str
    repository_id: str
    run_id: str
    scan_id: str
    evidence_id: str
    report_id: str
    approval_id: str
    audit_id: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def build_identity(suffix: str | None = None) -> ProofIdentity:
    token = (suffix or uuid4().hex[:12]).replace("-", "_")
    return ProofIdentity(
        suffix=token,
        customer_id=f"restart_customer_{token}",
        project_id=f"restart_project_{token}",
        repository_id=f"restart_repository_{token}",
        run_id=f"restart_run_{token}",
        scan_id=f"restart_scan_{token}",
        evidence_id=f"restart_evidence_{token}",
        report_id=f"restart_report_{token}",
        approval_id=f"restart_approval_{token}",
        audit_id=f"restart_audit_{token}",
    )


def _record_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _records(identity: ProofIdentity) -> dict[str, tuple[str, dict[str, Any]]]:
    scope = {
        "customer_id": identity.customer_id,
        "project_id": identity.project_id,
    }
    return {
        "repositories": (
            identity.repository_id,
            {
                **scope,
                "repository": "BoneManTGRM/NICO",
                "authorization_scope": "synthetic CI restart proof only",
            },
        ),
        "assessment_runs": (
            identity.run_id,
            {
                **scope,
                "workflow": "full",
                "status": "pending_review",
                "repository": "BoneManTGRM/NICO",
                "assessment_mode": "full",
                "human_review_required": True,
                "client_ready": False,
                "proof_marker": identity.suffix,
            },
        ),
        "scanner_runs": (
            identity.scan_id,
            {
                **scope,
                "run_id": identity.run_id,
                "status": "complete",
                "tools_requested": ["gitleaks"],
                "tools_run": ["gitleaks"],
                "human_review_required": True,
            },
        ),
        "evidence_items": (
            identity.evidence_id,
            {
                **scope,
                "run_id": identity.run_id,
                "filename": "restart-proof.json",
                "content_type": "application/json",
                "size_bytes": 128,
                "evidence_kind": "synthetic_restart_proof",
            },
        ),
        "reports": (
            identity.report_id,
            {
                **scope,
                "run_id": identity.run_id,
                "format": "package",
                "status": "draft",
                "report_path": "full_run",
                "human_review_required": True,
                "client_ready": False,
            },
        ),
        "approvals": (
            identity.approval_id,
            {
                **scope,
                "run_id": identity.run_id,
                "report_id": identity.report_id,
                "requested_action": "final_report_approval",
                "status": "pending",
                "human_review_required": True,
            },
        ),
        "audit_log": (
            identity.audit_id,
            {
                **scope,
                "run_id": identity.run_id,
                "action": "restart_proof.seeded",
                "synthetic": True,
            },
        ),
    }


def _id_key(table: str) -> str:
    return {
        "repositories": "repository_id",
        "assessment_runs": "run_id",
        "scanner_runs": "scan_id",
        "evidence_items": "evidence_id",
        "reports": "report_id",
        "approvals": "approval_id",
        "audit_log": "audit_id",
    }[table]


def _validate_record(
    table: str,
    item_id: str,
    value: dict[str, Any] | None,
    identity: ProofIdentity,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise RestartProofFailure(f"{table}:{item_id} was missing after adapter restart.")
    observed_id = str(value.get(_id_key(table)) or value.get("id") or "")
    if observed_id != item_id:
        raise RestartProofFailure(
            f"{table}:{item_id} returned a conflicting identity={observed_id or 'missing'}."
        )
    if str(value.get("customer_id") or "") != identity.customer_id:
        raise RestartProofFailure(f"{table}:{item_id} lost customer scope after restart.")
    if str(value.get("project_id") or "") != identity.project_id:
        raise RestartProofFailure(f"{table}:{item_id} lost project scope after restart.")
    if table in {"scanner_runs", "evidence_items", "reports", "approvals", "audit_log"}:
        if str(value.get("run_id") or "") != identity.run_id:
            raise RestartProofFailure(f"{table}:{item_id} lost exact run identity after restart.")
    return value


def run_restart_proof(
    database_url: str,
    *,
    adapter_factory: AdapterFactory = PostgresAdapter,
    identity: ProofIdentity | None = None,
) -> dict[str, Any]:
    if not str(database_url or "").strip():
        raise RestartProofFailure("A Postgres database URL is required.")
    proof_identity = identity or build_identity()
    records = _records(proof_identity)

    writer = adapter_factory(database_url)
    writer_status = writer.status()
    if writer_status.get("adapter") != "postgres" or not writer_status.get("persistence_available"):
        raise RestartProofFailure("The configured adapter did not report active Postgres persistence.")

    seeded_hashes: dict[str, str] = {}
    for table, (item_id, payload) in records.items():
        seeded = writer.put(table, item_id, payload)
        seeded_hashes[table] = _record_hash(seeded)

    del writer

    reader = adapter_factory(database_url)
    reader_status = reader.status()
    if reader_status.get("adapter") != "postgres" or not reader_status.get("persistence_available"):
        raise RestartProofFailure("The fresh adapter did not reconnect to Postgres persistence.")

    restored_hashes: dict[str, str] = {}
    for table, (item_id, _payload) in records.items():
        restored = _validate_record(
            table,
            item_id,
            reader.get(table, item_id),
            proof_identity,
        )
        restored_hashes[table] = _record_hash(restored)
        scoped_ids = {
            str(item.get(_id_key(table)) or item.get("id") or "")
            for item in reader.list(
                table,
                customer_id=proof_identity.customer_id,
                project_id=proof_identity.project_id,
            )
        }
        if item_id not in scoped_ids:
            raise RestartProofFailure(f"{table}:{item_id} was not visible through exact tenant scope.")
        cross_tenant = reader.list(
            table,
            customer_id=f"other_{proof_identity.customer_id}",
            project_id=proof_identity.project_id,
        )
        if cross_tenant:
            raise RestartProofFailure(f"{table} leaked records across customer scope.")

    updated_run = dict(reader.get("assessment_runs", proof_identity.run_id) or {})
    updated_run["status"] = "complete_after_restart"
    updated_run["restart_verified"] = True
    reader.put("assessment_runs", proof_identity.run_id, updated_run)

    del reader

    verifier = adapter_factory(database_url)
    final_run = _validate_record(
        "assessment_runs",
        proof_identity.run_id,
        verifier.get("assessment_runs", proof_identity.run_id),
        proof_identity,
    )
    if final_run.get("status") != "complete_after_restart" or not final_run.get("restart_verified"):
        raise RestartProofFailure("A post-restart update did not survive a second adapter restart.")
    approval = verifier.get("approvals", proof_identity.approval_id) or {}
    if approval.get("status") != "pending":
        raise RestartProofFailure("The restart proof changed a human approval decision.")

    return {
        "schema_version": 1,
        "evidence_kind": "synthetic_postgres_restart_proof",
        "synthetic": True,
        "live_production_claim": False,
        "status": "passed",
        "started_and_finished_at": utc_now(),
        "identity": {
            "suffix": proof_identity.suffix,
            "customer_id": proof_identity.customer_id,
            "project_id": proof_identity.project_id,
            "run_id": proof_identity.run_id,
            "scan_id": proof_identity.scan_id,
            "report_id": proof_identity.report_id,
            "approval_id": proof_identity.approval_id,
        },
        "proof": {
            "fresh_adapter_reconnected": True,
            "critical_records_restored": sorted(records),
            "exact_tenant_scope_preserved": True,
            "exact_run_links_preserved": True,
            "post_restart_update_survived_second_restart": True,
            "human_approval_unchanged": True,
        },
        "writer_status": {
            "adapter": writer_status.get("adapter"),
            "persistence_available": bool(writer_status.get("persistence_available")),
        },
        "reader_status": {
            "adapter": reader_status.get("adapter"),
            "persistence_available": bool(reader_status.get("persistence_available")),
        },
        "seeded_record_hashes": seeded_hashes,
        "restored_record_hashes": restored_hashes,
    }


def write_evidence(path: str, payload: dict[str, Any]) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Prove NICO critical Postgres records survive fresh adapter instances and remain tenant-bound."
    )
    parser.add_argument("--database-url", default=os.getenv("NICO_TEST_DATABASE_URL", ""))
    parser.add_argument("--output", default="audit-results/postgres-restart-proof.json")
    args = parser.parse_args()
    try:
        evidence = run_restart_proof(args.database_url)
        write_evidence(args.output, evidence)
        print(json.dumps({"status": "passed", "output": args.output}, sort_keys=True))
        return 0
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "evidence_kind": "synthetic_postgres_restart_proof",
            "synthetic": True,
            "live_production_claim": False,
            "status": "failed",
            "error": str(exc)[:500],
            "finished_at": utc_now(),
        }
        write_evidence(args.output, failure)
        print(json.dumps({"status": "failed", "output": args.output, "error": str(exc)[:500]}, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
