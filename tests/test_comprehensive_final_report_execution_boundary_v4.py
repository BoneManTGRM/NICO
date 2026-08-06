from __future__ import annotations

import base64
import time

from nico import comprehensive_final_report_execution_boundary_v4 as boundary
from nico.comprehensive_final_report_execution_boundary_v4 import (
    DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS,
    MAX_FINAL_REPORT_TIMEOUT_SECONDS,
    MIN_CONFIGURED_FINAL_REPORT_TIMEOUT_SECONDS,
    execute_final_report_stage,
)


def _context() -> dict:
    return {
        "run_id": "comprun_atomic_report",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_atomic_report",
        "customer_id": "customer_atomic_report",
        "project_id": "project_atomic_report",
        "prior_stage_results": {},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _report(context: dict) -> dict:
    identity = {
        key: context[key]
        for key in ("run_id", "repository", "commit_sha", "evidence_ledger_id")
    }
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": "report_atomic_exact",
            "markdown": (
                "# NICO Comprehensive Technical Assessment\n"
                "CLIENT DELIVERY NOT AUTHORIZED"
            ),
            "html": (
                "<html><body>NICO Comprehensive Technical Assessment</body></html>"
            ),
            "pdf_base64": base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii"),
            "pdf_page_count": 1,
            "json": {"identity": identity},
            "canonical_truth_sha256": "b" * 64,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_default_final_report_timeout_supports_large_evidence_packages(
    monkeypatch,
) -> None:
    monkeypatch.delenv("NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS", raising=False)
    assert DEFAULT_FINAL_REPORT_TIMEOUT_SECONDS == 600
    assert boundary._timeout_seconds(None) == 600

    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS", "invalid")
    assert boundary._timeout_seconds(None) == 600

    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS", "5")
    assert boundary._timeout_seconds(None) == MIN_CONFIGURED_FINAL_REPORT_TIMEOUT_SECONDS

    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_TIMEOUT_SECONDS", "5000")
    assert boundary._timeout_seconds(None) == MAX_FINAL_REPORT_TIMEOUT_SECONDS


def test_atomic_final_report_validates_and_retains_exact_artifacts() -> None:
    result = execute_final_report_stage(_report, _context(), timeout_seconds=5)

    assert result["status"] == "complete"
    assert result["artifacts_available"] is True
    assert result["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["stage_execution"]["full_context_deepcopy_skipped"] is True
    assert result["stage_execution"]["artifact_validation_complete"] is True
    assert result["stage_execution"]["canonical_run_written_only_by_request_thread"] is True
    assert result["evidence"]["pdf_valid"] is True
    assert result["evidence"]["exact_run_identity_verified"] is True
    assert result["evidence"]["exact_evidence_ledger_identity_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_atomic_final_report_times_out_fail_closed_and_is_recoverable() -> None:
    def slow(_context: dict) -> dict:
        time.sleep(2)
        return {"status": "complete"}

    started = time.monotonic()
    result = execute_final_report_stage(slow, _context(), timeout_seconds=1)

    assert time.monotonic() - started < 1.6
    assert result["status"] == "blocked"
    assert result["reason"] == "final_report_execution_timeout"
    assert result.get("reason") != "background_stage_execution_in_progress"
    assert result["recovery_supported"] is True
    assert result["recovery_scope"] == "final_report_only"
    assert result["stage_execution"]["execution_timeout_seconds"] == 1
    assert result["stage_execution"]["recovery_supported"] is True
    assert result["stage_execution"]["recovery_scope"] == "final_report_only"
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_atomic_final_report_rejects_identity_drift() -> None:
    def drift(context: dict) -> dict:
        result = _report(context)
        result["report_package"]["json"]["identity"]["commit_sha"] = "c" * 40
        return result

    result = execute_final_report_stage(drift, _context(), timeout_seconds=5)

    assert result["status"] == "blocked"
    assert result["reason"] == "final_report_identity_mismatch"
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_atomic_final_report_rejects_missing_identity_and_hash() -> None:
    def missing_identity(context: dict) -> dict:
        result = _report(context)
        result["report_package"]["json"]["identity"].pop("evidence_ledger_id")
        return result

    identity_result = execute_final_report_stage(
        missing_identity,
        _context(),
        timeout_seconds=5,
    )
    assert identity_result["status"] == "blocked"
    assert identity_result["reason"] == "final_report_identity_mismatch"

    def missing_hash(context: dict) -> dict:
        result = _report(context)
        result["report_package"].pop("canonical_truth_sha256")
        return result

    hash_result = execute_final_report_stage(missing_hash, _context(), timeout_seconds=5)
    assert hash_result["status"] == "blocked"
    assert hash_result["reason"] == "final_report_canonical_hash_missing"


def test_atomic_final_report_does_not_copy_large_context_again() -> None:
    context = _context()
    huge = [
        {"path": f"file_{index}", "values": list(range(20))}
        for index in range(20_000)
    ]
    context["prior_stage_results"] = {
        "repository_and_delivery_evidence": {"huge": huge}
    }
    observed: dict = {}

    def provider(payload: dict) -> dict:
        observed.update(payload)
        assert (
            payload["prior_stage_results"]["repository_and_delivery_evidence"]["huge"]
            is huge
        )
        return _report(payload)

    result = execute_final_report_stage(provider, context, timeout_seconds=5)

    assert result["status"] == "complete"
    assert observed["prior_stage_results"]["repository_and_delivery_evidence"]["huge"] is huge
