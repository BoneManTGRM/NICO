from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import nico.operational_observability as observability
from scripts.build_resilience_proof import (
    ResilienceProofFailure,
    build_resilience_proof,
    prove_event_pipeline_degradation,
    safe_error,
    synthetic_scanner_record,
)


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "resilience-proof.yml"


def test_synthetic_scanner_record_is_authorized_bounded_and_review_blocked() -> None:
    now = datetime(2026, 7, 13, 12, 0, tzinfo=timezone.utc)
    scan_id, run_id, record = synthetic_scanner_record("unit-proof", now=now)

    assert scan_id == "scan_resilience_unitproof"
    assert run_id == "fullrun_resilience_unitproof"
    assert record["scan_id"] == scan_id
    assert record["run_id"] == run_id
    assert record["repository"] == "BoneManTGRM/NICO"
    assert record["authorized"] is True
    assert record["authorized_by"] == "synthetic_resilience_ci"
    assert record["authorization_scope"] == "authorized synthetic scanner recovery proof only"
    assert record["draft_pr_creation_allowed"] is False
    assert record["human_review_required"] is True
    assert record["client_delivery_allowed"] is False
    assert record["synthetic"] is True
    assert record["status"] == "running"
    assert record["updated_at"] == "2026-07-13T10:00:00Z"


def test_event_pipeline_failure_is_degraded_redacted_and_restores_module_state() -> None:
    original_store = observability.STORE
    original_write_failures = observability._EVENT_WRITE_FAILURES
    original_read_failures = observability._EVENT_READ_FAILURES

    result = prove_event_pipeline_degradation()

    assert result == {
        "status": "passed",
        "event_stored": False,
        "safe_read_count": 0,
        "pipeline_status": "degraded",
        "write_failures": 1,
        "read_failures": 1,
        "storage_adapter": "postgres",
        "persistence_available": True,
        "sensitive_metadata_redacted": True,
    }
    assert observability.STORE is original_store
    assert observability._EVENT_WRITE_FAILURES == original_write_failures
    assert observability._EVENT_READ_FAILURES == original_read_failures


def test_database_url_is_required_and_error_output_redacts_credentials() -> None:
    with pytest.raises(ResilienceProofFailure, match="Postgres database URL is required"):
        build_resilience_proof("")

    database_url = "postgresql://nico:super-secret@127.0.0.1:5432/nico"
    rendered = safe_error(f"connection failed for {database_url}", database_url)

    assert "super-secret" not in rendered
    assert "postgresql://" not in rendered
    assert "[DATABASE_URL_REDACTED]" in rendered


def test_workflow_runs_real_postgres_and_uploads_bounded_resilience_evidence() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in source
    assert "push:" in source
    assert "workflow_dispatch:" in source
    assert "postgres:16-alpine" in source
    assert "NICO_TEST_DATABASE_URL" in source
    assert "scripts/build_resilience_proof.py" in source
    assert "audit-results/resilience-proof.json" in source
    assert "actions/upload-artifact@v4" in source
    assert "permissions:\n  contents: read" in source
    assert "NICO_ADMIN_TOKEN" not in source
    assert "postgresql://" in source
