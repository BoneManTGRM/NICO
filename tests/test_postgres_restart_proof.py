from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from scripts.postgres_restart_proof import (
    ProofIdentity,
    RestartProofFailure,
    build_identity,
    run_restart_proof,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "postgres-restart-proof.yml"


class SharedFakeAdapter:
    tables: dict[str, dict[str, dict[str, Any]]] = {}

    def __init__(self, _database_url: str) -> None:
        self.tables.setdefault("repositories", {})
        self.tables.setdefault("assessment_runs", {})
        self.tables.setdefault("scanner_runs", {})
        self.tables.setdefault("evidence_items", {})
        self.tables.setdefault("reports", {})
        self.tables.setdefault("approvals", {})
        self.tables.setdefault("audit_log", {})

    def status(self) -> dict[str, Any]:
        return {"adapter": "postgres", "persistence_available": True}

    def put(self, table: str, item_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = deepcopy(payload)
        item.setdefault("id", item_id)
        item.setdefault(
            {
                "repositories": "repository_id",
                "assessment_runs": "run_id",
                "scanner_runs": "scan_id",
                "evidence_items": "evidence_id",
                "reports": "report_id",
                "approvals": "approval_id",
                "audit_log": "audit_id",
            }[table],
            item_id,
        )
        self.tables[table][item_id] = deepcopy(item)
        return deepcopy(item)

    def get(self, table: str, item_id: str) -> dict[str, Any] | None:
        item = self.tables.get(table, {}).get(item_id)
        return deepcopy(item) if item is not None else None

    def list(
        self,
        table: str,
        customer_id: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        items = list(self.tables.get(table, {}).values())
        if customer_id:
            items = [item for item in items if item.get("customer_id") == customer_id]
        if project_id:
            items = [item for item in items if item.get("project_id") == project_id]
        return deepcopy(items)


@pytest.fixture(autouse=True)
def clear_fake_tables() -> None:
    SharedFakeAdapter.tables = {}


def test_restart_proof_restores_critical_records_and_preserves_human_approval() -> None:
    identity = build_identity("unit_restart")

    result = run_restart_proof(
        "postgresql://synthetic.invalid/nico",
        adapter_factory=SharedFakeAdapter,
        identity=identity,
    )

    assert result["status"] == "passed"
    assert result["synthetic"] is True
    assert result["live_production_claim"] is False
    assert result["identity"]["run_id"] == identity.run_id
    assert result["proof"] == {
        "fresh_adapter_reconnected": True,
        "critical_records_restored": [
            "approvals",
            "assessment_runs",
            "audit_log",
            "evidence_items",
            "reports",
            "repositories",
            "scanner_runs",
        ],
        "exact_tenant_scope_preserved": True,
        "exact_run_links_preserved": True,
        "post_restart_update_survived_second_restart": True,
        "human_approval_unchanged": True,
    }
    assert SharedFakeAdapter.tables["assessment_runs"][identity.run_id]["status"] == "complete_after_restart"
    assert SharedFakeAdapter.tables["approvals"][identity.approval_id]["status"] == "pending"
    assert "database_url" not in repr(result).lower()
    assert "postgresql://" not in repr(result)


def test_restart_proof_fails_when_a_fresh_adapter_cannot_restore_a_record() -> None:
    identity = build_identity("missing_record")
    creations = 0

    class DroppingAdapter(SharedFakeAdapter):
        def __init__(self, database_url: str) -> None:
            nonlocal creations
            super().__init__(database_url)
            creations += 1
            if creations == 2:
                self.tables["reports"].pop(identity.report_id, None)

    with pytest.raises(RestartProofFailure, match="reports:.*missing after adapter restart"):
        run_restart_proof(
            "postgresql://synthetic.invalid/nico",
            adapter_factory=DroppingAdapter,
            identity=identity,
        )


def test_restart_proof_fails_on_cross_tenant_leakage() -> None:
    identity = build_identity("tenant_leak")

    class LeakingAdapter(SharedFakeAdapter):
        def list(
            self,
            table: str,
            customer_id: str | None = None,
            project_id: str | None = None,
        ) -> list[dict[str, Any]]:
            return deepcopy(list(self.tables.get(table, {}).values()))

    with pytest.raises(RestartProofFailure, match="leaked records across customer scope"):
        run_restart_proof(
            "postgresql://synthetic.invalid/nico",
            adapter_factory=LeakingAdapter,
            identity=identity,
        )


def test_restart_proof_requires_real_persistence_status() -> None:
    class MemoryLikeAdapter(SharedFakeAdapter):
        def status(self) -> dict[str, Any]:
            return {"adapter": "memory", "persistence_available": False}

    with pytest.raises(RestartProofFailure, match="active Postgres persistence"):
        run_restart_proof(
            "postgresql://synthetic.invalid/nico",
            adapter_factory=MemoryLikeAdapter,
            identity=build_identity("memory_fallback"),
        )


def test_identity_is_unique_and_bounded() -> None:
    first = build_identity()
    second = build_identity()

    assert first != second
    assert first.run_id.startswith("restart_run_")
    assert len(first.suffix) == 12


def test_restart_workflow_runs_real_postgres_and_uploads_bounded_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in source
    assert "push:" in source
    assert "workflow_dispatch:" in source
    assert "postgres:16-alpine" in source
    assert "NICO_TEST_DATABASE_URL" in source
    assert "scripts/postgres_restart_proof.py" in source
    assert "audit-results/postgres-restart-proof.json" in source
    assert "actions/upload-artifact@v7" in source
    assert "permissions:\n  contents: read" in source
    assert "NICO_ADMIN_TOKEN" not in source
