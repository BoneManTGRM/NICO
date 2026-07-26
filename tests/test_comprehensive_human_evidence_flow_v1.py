from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from nico.comprehensive_run_record import (
    LEGACY_VERSION,
    VERSION,
    create_comprehensive_run_record,
    restore_comprehensive_run_record,
)
from nico.comprehensive_run_service import ComprehensiveRunService
from nico.comprehensive_run_store import ComprehensiveRunStore


def _store(path: Path) -> ComprehensiveRunStore:
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path), dialect="sqlite")
    store.ensure_schema()
    return store


def _complete_qa() -> dict:
    return {
        "functional_qa": {
            "evidence": {
                "test_cases": [{"scenario": "sign-in", "expected": "success"}],
                "observed_results": [{"scenario": "sign-in", "actual": "success"}],
            },
            "reviewer": "QA lead",
            "observed_at": "2026-07-25T23:00:00Z",
            "source_reference": "evidence://qa/sign-in",
        }
    }


def test_run_identity_binds_depth_locale_and_human_evidence() -> None:
    record = create_comprehensive_run_record(
        run_id="comprun_human_001",
        repository="owner/repo",
        commit_sha="a" * 40,
        evidence_ledger_id="ledger_human_001",
        customer_id="customer_001",
        project_id="project_001",
        authorized=True,
        assessment_depth="strategic",
        report_language="es-MX",
        human_evidence={
            "stakeholder_context": {
                "evidence": {
                    "objectives": ["Release by October 1"],
                    "constraints": ["One mobile engineer available"],
                },
                "reviewer": "Product owner",
                "observed_at": "2026-07-25T23:00:00Z",
                "source_reference": "interview://product-owner/001",
            }
        },
    )

    assert record["artifact_schema"] == VERSION
    assert record["identity"]["assessment_depth"] == "strategic"
    assert record["identity"]["report_language"] == "es-MX"
    assert record["human_evidence"]["complete_modules"] == [
        "stakeholder_context"
    ]


def test_stage_executor_receives_exact_persisted_human_evidence(tmp_path: Path) -> None:
    observed: dict = {}

    def authorization(context: dict) -> dict:
        observed.update(context)
        return {"status": "complete"}

    service = ComprehensiveRunService(
        _store(tmp_path / "human-flow.db"),
        {"authorization": authorization},
    )
    created = service.start(
        run_id="comprun_human_flow",
        repository="owner/repo",
        commit_sha="b" * 40,
        evidence_ledger_id="ledger_human_flow",
        customer_id="customer_flow",
        project_id="project_flow",
        authorized=True,
        assessment_depth="strategic",
        report_language="en",
        human_evidence=_complete_qa(),
    )

    service.resume(created["identity"]["run_id"], max_stages=1)

    assert observed["assessment_depth"] == "strategic"
    assert observed["report_language"] == "en"
    assert observed["human_evidence"]["complete_modules"] == ["functional_qa"]
    assert observed["human_evidence"]["modules"]["functional_qa"]["evidence"][
        "observed_results"
    ][0]["scenario"] == "sign-in"


def test_legacy_record_is_verified_then_upgraded_without_inventing_context() -> None:
    record = create_comprehensive_run_record(
        run_id="comprun_legacy",
        repository="owner/repo",
        commit_sha="c" * 40,
        evidence_ledger_id="ledger_legacy",
        customer_id="customer_legacy",
        project_id="project_legacy",
        authorized=True,
    )
    record["artifact_schema"] = LEGACY_VERSION
    record["identity"].pop("assessment_depth")
    record["identity"].pop("report_language")
    record.pop("human_evidence")

    payload = dict(record)
    payload.pop("integrity_sha256", None)
    record["integrity_sha256"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    restored = restore_comprehensive_run_record(record)

    assert restored["artifact_schema"] == VERSION
    assert restored["identity"]["assessment_depth"] == "not_recorded"
    assert restored["identity"]["report_language"] == "not_recorded"
    assert restored["human_evidence"]["status"] == "review_limited"
    assert restored["human_evidence"]["status_counts"]["not_assessed"] == 10
