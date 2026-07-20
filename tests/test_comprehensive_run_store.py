from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES
from nico.comprehensive_run_record import apply_comprehensive_stage_result, create_comprehensive_run_record
from nico.comprehensive_run_store import (
    ComprehensiveRunConflict,
    ComprehensiveRunNotFound,
    ComprehensiveRunStore,
)


def _store(tmp_path: Path) -> ComprehensiveRunStore:
    database = tmp_path / "comprehensive.sqlite3"
    store = ComprehensiveRunStore(lambda: sqlite3.connect(database), dialect="sqlite")
    store.ensure_schema()
    return store


def _record(run_id: str = "comprun_001") -> dict:
    return create_comprehensive_run_record(
        run_id=run_id,
        repository="BoneManTGRM/NICO",
        commit_sha="a" * 40,
        evidence_ledger_id=f"ledger_{run_id}",
        customer_id="customer_acme",
        project_id="project_nico",
        authorized=True,
        now=datetime(2026, 7, 20, 12, 0, tzinfo=UTC),
    )


def test_create_and_load_round_trip_preserves_integrity(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created = store.create(_record())
    loaded = store.load("comprun_001")

    assert loaded == created
    assert loaded["human_review_required"] is True
    assert loaded["client_delivery_allowed"] is False


def test_duplicate_run_identity_is_rejected(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = _record()
    store.create(record)

    with pytest.raises(ComprehensiveRunConflict, match="run_already_exists"):
        store.create(record)


def test_save_uses_optimistic_revision_control(tmp_path: Path) -> None:
    store = _store(tmp_path)
    original = store.create(_record())
    advanced = apply_comprehensive_stage_result(
        original,
        stage_id=COMPREHENSIVE_STAGES[0],
        result={"status": "complete"},
        now=datetime(2026, 7, 20, 12, 1, tzinfo=UTC),
    )

    store.save(advanced, expected_revision=1)
    loaded = store.load("comprun_001")
    assert loaded["revision"] == 2
    assert loaded["completed_stages"] == [COMPREHENSIVE_STAGES[0]]

    with pytest.raises(ComprehensiveRunConflict, match="stale_revision"):
        store.save(advanced, expected_revision=1)


def test_revision_must_advance_exactly_once(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = store.create(_record())

    with pytest.raises(ComprehensiveRunConflict, match="revision_must_advance_once"):
        store.save(record, expected_revision=1)


def test_tampered_payload_is_rejected_before_write(tmp_path: Path) -> None:
    store = _store(tmp_path)
    record = _record()
    record["client_delivery_allowed"] = True

    with pytest.raises(ValueError, match="invalid_run_record"):
        store.create(record)


def test_missing_run_is_explicit(tmp_path: Path) -> None:
    store = _store(tmp_path)

    with pytest.raises(ComprehensiveRunNotFound):
        store.load("comprun_missing")


def test_recent_runs_are_scoped_to_customer_and_project(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.create(_record("comprun_001"))
    second = _record("comprun_002")
    second["identity"]["customer_id"] = "customer_other"
    # Identity changes require rebuilding the integrity-bound record.
    second = create_comprehensive_run_record(
        run_id="comprun_002",
        repository="BoneManTGRM/NICO",
        commit_sha="b" * 40,
        evidence_ledger_id="ledger_002",
        customer_id="customer_other",
        project_id="project_nico",
        authorized=True,
        now=datetime(2026, 7, 20, 12, 2, tzinfo=UTC),
    )
    store.create(second)

    records = store.list_recent(customer_id="customer_acme", project_id="project_nico")
    assert [item["identity"]["run_id"] for item in records] == ["comprun_001"]


def test_postgres_dialect_uses_psycopg_placeholders() -> None:
    store = ComprehensiveRunStore(lambda: None, dialect="postgres")  # type: ignore[arg-type]
    assert store.placeholder == "%s"


def test_unknown_dialect_is_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported_dialect"):
        ComprehensiveRunStore(lambda: None, dialect="mysql")  # type: ignore[arg-type]
