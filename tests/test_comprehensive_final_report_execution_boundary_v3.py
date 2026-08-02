from __future__ import annotations

import base64
from copy import deepcopy

from nico.comprehensive_final_report_execution_boundary_v3 import (
    FINAL_REPORT_STAGE_ID,
    execute_final_report_stage,
)


def _context() -> dict:
    return {
        "run_id": "comprun_atomic_report",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_atomic_report",
        "customer_id": "customer",
        "project_id": "project",
        "prior_stage_results": {"risk_reduction_and_executive_briefing": {"status": "complete"}},
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _valid_result(context: dict) -> dict:
    identity = {
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": context["commit_sha"],
        "evidence_ledger_id": context["evidence_ledger_id"],
    }
    return {
        "status": "complete",
        **identity,
        "report_package": {
            "report_id": "report_atomic",
            "markdown": "# NICO Comprehensive Technical Assessment\n",
            "html": "<html><body>NICO Comprehensive Technical Assessment</body></html>",
            "pdf_base64": base64.b64encode(b"%PDF-1.4\n%%EOF\n").decode("ascii"),
            "pdf_page_count": 1,
            "json": {"identity": identity},
            "canonical_truth_sha256": "b" * 64,
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_valid_final_report_is_returned_for_canonical_run_write() -> None:
    source = _context()
    original = deepcopy(source)

    result = execute_final_report_stage(lambda context: _valid_result(context), source)

    assert result["status"] == "complete"
    assert result["artifacts_available"] is True
    assert result["report_package"]["report_id"] == "report_atomic"
    assert result["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert result["stage_execution"]["canonical_run_written_only_by_request_thread"] is True
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["stage_execution"]["artifact_validation_complete"] is True
    assert result["evidence"]["exact_run_identity_verified"] is True
    assert result["evidence"]["exact_evidence_ledger_identity_verified"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
    assert source == original


def test_final_report_cannot_return_generic_background_running_state() -> None:
    result = execute_final_report_stage(
        lambda context: {
            "status": "running",
            "reason": "background_stage_execution_in_progress",
        },
        _context(),
    )

    assert result["status"] != "complete"
    assert result["stage_execution"]["mode"] == "atomic_final_report_publication"
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_missing_or_mismatched_artifacts_fail_closed() -> None:
    missing = execute_final_report_stage(
        lambda context: {"status": "complete"},
        _context(),
    )
    assert missing["status"] == "blocked"
    assert missing["reason"] == "final_report_package_missing"

    def mismatched(context: dict) -> dict:
        result = _valid_result(context)
        result["report_package"]["json"]["identity"]["commit_sha"] = "different"
        return result

    mismatch = execute_final_report_stage(mismatched, _context())
    assert mismatch["status"] == "blocked"
    assert mismatch["reason"] == "final_report_identity_mismatch"
    assert mismatch["client_delivery_allowed"] is False


def test_missing_identity_or_canonical_hash_fails_closed() -> None:
    def missing_identity(context: dict) -> dict:
        result = _valid_result(context)
        result["report_package"]["json"]["identity"].pop("evidence_ledger_id")
        return result

    identity_result = execute_final_report_stage(missing_identity, _context())
    assert identity_result["status"] == "blocked"
    assert identity_result["reason"] == "final_report_identity_mismatch"

    def missing_hash(context: dict) -> dict:
        result = _valid_result(context)
        result["report_package"].pop("canonical_truth_sha256")
        return result

    hash_result = execute_final_report_stage(missing_hash, _context())
    assert hash_result["status"] == "blocked"
    assert hash_result["reason"] == "final_report_canonical_hash_missing"


def test_nonreturning_provider_becomes_explicit_timeout(monkeypatch) -> None:
    from nico import comprehensive_final_report_execution_boundary_v3 as boundary

    def timed_out(executor, context, *, stage_id, timeout_seconds=None):
        assert stage_id == FINAL_REPORT_STAGE_ID
        return {
            "status": "blocked",
            "reason": "stage_execution_timeout",
            "error_code": "stage_execution_timeout",
            "stage_execution": {"timed_out": True},
        }

    monkeypatch.setattr(boundary, "execute_stage_with_timeout", timed_out)
    result = boundary.execute_final_report_stage(lambda context: None, _context())

    assert result["status"] == "blocked"
    assert result["reason"] == "stage_execution_timeout"
    assert result["stage_execution"]["timed_out"] is True
    assert result["stage_execution"]["detached_background_execution"] is False
    assert result["client_delivery_allowed"] is False
