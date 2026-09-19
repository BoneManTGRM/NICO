"""Synthetic truth contracts; never live authorization or production acceptance."""
from types import SimpleNamespace

import pytest

from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical

SHA = "a" * 40


@pytest.mark.parametrize("execution", ["unavailable", "failed", "partial"])
def test_missing_inventory_does_not_turn_execution_into_inapplicability(execution):
    result = normalize_scanner_applicability_canonical({
        "identity": {"commit_sha": SHA},
        "scanner_execution_records": [{"scanner_name": "npm-audit", "commit_sha": SHA,
            "status": execution, "state": execution, "completed": False,
            "failure_reason": "No package-lock.json with an adjacent package.json was found."}],
    })
    record = result["requested_scanner_records"][0]
    assert record["applicability_state"] == "applicability_unproven"
    assert record["execution_state"] == execution
    assert record["applicability_reason"]
    assert result["not_applicable_scanner_records"] == []
    assert result["assessment"]["scanner_applicability_summary"]["applicability_unproven_scanners"] == 1


def test_size_limited_checkout_keeps_identity_without_scanner_completion(monkeypatch):
    from nico import scanner_worker as base, snapshot_scanner_worker as worker
    from nico.scanner_determinism_v1 import clone_repository_at_snapshot
    from nico.storage import MemoryAdapter

    def fake_git(command, **kwargs):
        return SimpleNamespace(returncode=0, stderr="", stdout=SHA if command[:3] == ["git", "rev-parse", "HEAD"] else "")

    monkeypatch.setattr(worker, "_git", fake_git)
    monkeypatch.setattr(worker, "clone_repository_at_snapshot", clone_repository_at_snapshot)
    monkeypatch.setattr(base, "directory_size", lambda path: 291563274)
    monkeypatch.setattr(worker, "STORE", MemoryAdapter())
    monkeypatch.setattr(base, "SCAN_JOBS", {"synthetic_size_limit": {}})
    monkeypatch.setattr(worker.tool_runners, "run_scanner_tool", lambda *args: pytest.fail("oversized checkout must not execute scanners"))
    worker._run_snapshot_scan("synthetic_size_limit", {
        "repository": "example/authorized-fixture", "snapshot_commit_sha": SHA,
        "snapshot_id": "synthetic_snapshot", "run_id": "synthetic_run", "tools": ["bandit", "npm-audit"],
    })
    result = base.SCAN_JOBS["synthetic_size_limit"]
    assert result["snapshot_match"] is True
    assert result["actual_commit_sha"] == SHA
    assert result["status"] in {"unavailable", "partial", "failed"}
    assert result["execution_limit"]["reason"] == "repository_size_limit_exceeded"
    assert result["execution_limit"]["observed_bytes"] == 291563274
    assert result["execution_limit"]["limit_bytes"] == base.MAX_REPO_BYTES
    assert result["evidence_summary"]["repo_size_bytes"] == 291563274
    assert result["tools_run"] == []
    assert set(result["unavailable_tools"]) == {"bandit", "npm-audit"}
    assert all(row["execution_state"] == "unavailable" for row in result["scanner_results"])
    assert all(row["applicability_state"] == "applicability_unproven" for row in result["scanner_results"])


def test_requester_attestation_is_not_independent_permission_verification():
    from nico.comprehensive_production_capabilities import _authorization_provider
    result = _authorization_provider({"service_id": "comprehensive", "run_id": "synthetic_run",
        "repository": "example/authorized-fixture", "commit_sha": SHA,
        "evidence_ledger_id": "synthetic_ledger", "authorization_confirmed": True})
    assert result["authorization_confirmed"] is True  # existing gate meaning preserved
    assert result["evidence"]["requester_authorization_attestation"] == "confirmed"
    assert result["evidence"]["independent_authorization_verification"] == "not_established"
    assert "Ownership or explicit authorization" not in result["summary"]
    assert result["client_delivery_allowed"] is False


def test_coverage_projection_keeps_both_existing_denominators():
    from nico.repository_profile_coverage_v1 import profile_coverage
    from nico.comprehensive_report_package import _source_tables
    eligible = [f"src/module_{i}.py" for i in range(137)]
    excluded = [f"tests/test_module_{i}.py" for i in range(347)]
    coverage = profile_coverage({"tree_paths": eligible + excluded,
        "files": {p: "pass\n" for p in eligible[:5]},
        "tree_collection_succeeded": True, "tree_truncated": False}, {"files_analyzed": 5})
    assert coverage["eligible_source_coverage_percent"] == 3.65
    assert coverage["whole_repository_coverage_percent"] == 1.03
    rows = dict(_source_tables({"profile_coverage": coverage})[0]["rows"])
    assert rows["Eligible-source analysis coverage (%)"] == 3.65
    assert rows["Whole supported-source coverage (%)"] == 1.03
    assert rows["Eligible-source coverage fraction"] == "5 / 137"
    assert rows["Observed supported-source coverage fraction"] == "5 / 484"
    metrics = coverage["coverage_metrics"]
    assert metrics["eligible_source_analysis"]["numerator"] == 5
    assert metrics["eligible_source_analysis"]["denominator"] == 137
    assert metrics["observed_supported_source_analysis"]["denominator"] == 484
    assert metrics["eligible_source_analysis"]["denominator_population"] != metrics["observed_supported_source_analysis"]["denominator_population"]


def test_empty_scanner_ledger_cannot_establish_verified_assurance():
    from nico.express_score_assurance_ledger_v45 import _normalize_scanner_section
    section = {}
    _normalize_scanner_section({}, section)
    assert section["scanner_execution_denominator"] == 0
    assert section["assurance_status"] == "unverified"


def _limited_scan():
    return {"scan_id": "synthetic_scan", "status": "unavailable", "snapshot_match": True,
        "actual_commit_sha": SHA, "tools_requested": ["bandit"], "tools_run": [],
        "unavailable_tools": ["bandit"], "execution_limit": {
            "reason": "repository_size_limit_exceeded", "commit_sha": SHA,
            "observed_bytes": 291563274, "limit_bytes": 100000000,
            "scanner_execution_permitted": False},
        "scanner_results": [{"tool": "bandit", "status": "unavailable", "commit_sha": SHA,
            "execution_state": "unavailable", "execution_reason": "repository_size_limit_exceeded",
            "applicability_state": "applicability_unproven", "completed": False}]}


def test_verified_size_limit_continues_as_limited_evidence_without_execution_credit(monkeypatch):
    from nico import comprehensive_native_providers as native
    from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records, retained_scanner_payload
    context = {"run_id": "synthetic_run", "repository": "example/authorized-fixture", "commit_sha": SHA,
        "evidence_ledger_id": "synthetic_ledger", "customer_id": "synthetic_customer", "project_id": "synthetic_project",
        "prior_stage_results": {"immutable_repository_snapshot": {"snapshot": {"status": "attached", "commit_sha": SHA}}}}
    scan = _limited_scan()
    monkeypatch.setattr(native, "start_snapshot_scan", lambda payload: scan)
    monkeypatch.setattr(native, "get_scan", lambda scan_id: scan)
    stage = native.scanner_suite_provider(context)
    assert stage["status"] == "complete"  # evidence collection stage, not scanner execution
    assert stage["scanner"]["status"] == "unavailable"
    assert stage["scanner"]["tools_run"] == []
    assert stage["scanner"]["execution_limit"] == scan["execution_limit"]
    stage["scanner_execution_records"] = compact_scanner_records(scan, commit_sha=SHA)
    context["prior_stage_results"]["dependency_security_static_analysis"] = stage
    retained = retained_scanner_payload(context)
    assert retained["execution_limit"] == scan["execution_limit"]
    assert retained["scanner_execution_records"][0]["execution_state"] == "unavailable"
    assert retained["scanner_execution_records"][0]["applicability_state"] == "applicability_unproven"
    for invalid in ({"commit_sha": "b" * 40}, {"observed_bytes": 1}, {"scanner_execution_permitted": True}):
        scan["execution_limit"] = {**_limited_scan()["execution_limit"], **invalid}
        assert native.scanner_suite_provider(context)["status"] == "blocked"


@pytest.mark.parametrize("analyzed,expected", [(5, "limited"), (137, "supported_scope")])
def test_assurance_preserves_score_and_distinguishes_supported_control(analyzed, expected):
    from nico.comprehensive_score_assurance_ledger_v45 import bind_source_security_assurance
    coverage = {"version": "nico.repository_profile_coverage.v1", "inventory_complete": True,
        "observed_source_files": 484, "eligible_source_files": 137, "analyzed_source_files": analyzed,
        "unsampled_eligible_source_files": 137-analyzed, "eligible_source_coverage_percent": round(100*analyzed/137, 2),
        "whole_repository_coverage_percent": round(100*analyzed/484, 2)}
    original = {"assessment": {"maturity_signal": {"score": 74, "evidence_readiness_score": 62}},
        "stage_summaries": [{"profile_coverage": coverage}],
        "requested_scanner_records": [{"applicable": True, "applicability_state": "applicable",
            "completed": True, "verified_complete": True, "execution_state": "complete"}]}
    result = bind_source_security_assurance(original)
    assert result["assessment"]["maturity_signal"] == original["assessment"]["maturity_signal"]
    assurance = result["source_security_assurance"]
    assert assurance["status"] == expected
    assert assurance["repository_wide_security_rating"] is False
    assert assurance["coverage_metrics"]["observed_supported_source_analysis"]["denominator"] == 484
    assert original.get("source_security_assurance") is None
    assert bind_source_security_assurance({})["source_security_assurance"]["status"] == "unverified"


def test_reconciliation_keeps_unproven_applicability_out_of_applicable_counts():
    from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth
    result = reconcile_authoritative_scanner_truth({"identity": {"commit_sha": SHA},
        "scanner_execution_records": [{"scanner_name": "bandit", "status": "unavailable", "commit_sha": SHA}]})
    summary = result["assessment"]["scanner_applicability_summary"]
    assert summary["applicable_scanners"] == summary["incomplete_applicable_scanners"] == 0
    assert summary["applicability_unproven_scanners"] == 1
    assert result["client_readiness_contract"]["applicable_exact_run_scanners"] == []
    assert result["client_readiness_contract"]["applicability_unproven_scanners"] == ["bandit"]
    assert result["delivery_gate"]["analyzer_evidence_ready"] is False


def test_completed_execution_cannot_resolve_unproven_applicability_in_prerender():
    from nico.comprehensive_pre_render_scanner_truth_v65 import derive_authoritative_scanner_truth
    record = {"scanner_name": "bandit", "status": "completed", "completed": True, "verified": True,
        "artifact_hash": "c" * 64, "exact_commit_match": True,
        "applicable": None, "applicability_state": "applicability_unproven"}
    truth = derive_authoritative_scanner_truth({"dependency_security_static_analysis": {"scanner_execution_records": [record]}})
    assert truth["completed"] == ["bandit"]
    assert truth["applicability_unproven"] == ["bandit"]
    assert truth["applicable"] == []


def test_applicability_normalization_is_idempotent_and_javascript_does_not_prove_typescript():
    original = {"repository_evidence": {"file_evidence": {"sampled_paths": ["app.js", "package.json"]}},
        "scanner_execution_records": [{"scanner_name": "typescript", "status": "failed", "failure_reason": "Process failed."}]}
    first = normalize_scanner_applicability_canonical(original)
    second = normalize_scanner_applicability_canonical(first)
    assert first["requested_scanner_records"] == second["requested_scanner_records"]
    assert first["requested_scanner_records"][0]["applicability_state"] == "applicability_unproven"
