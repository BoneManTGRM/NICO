from __future__ import annotations

from nico.candidate_evidence_context_v1 import enrich_canonical_candidate_evidence
from tests.phase1_candidate_fixtures import candidate, lineage_then_triage, register, retained_triage


def test_verified_secret_cannot_be_suppressed_as_fixture() -> None:
    current = candidate("SECRET", category="secret", scanner="trufflehog", rule="token", path="tests/example.env", severity="critical", context={"verified": True, "synthetic": True, "scope": "test"})
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["technical_triage_verdict"] == "confirmed"
    assert finding["rationale_code"] == "verified_secret"
    assert "fixture_or_example_context_does_not_override_verification" in finding["counterevidence"]
    assert finding["review_routing_class"] == "CRITICAL_ATTENTION"


def test_static_analysis_distinguishes_nonexecutable_noise() -> None:
    current = candidate("STATIC", category="static", path="tests/example.py", context={"executable_code": False, "comment_or_string": True, "scope": "test"})
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert finding["rationale_code"] == "static_nonexecutable_noise"


def test_generic_static_hit_is_not_automatically_confirmed() -> None:
    current = candidate("STATIC", category="static", severity="critical", context={})
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["technical_triage_verdict"] == "needs_review"


def test_dependency_context_uses_actual_scanned_package_not_nested_advisory() -> None:
    current = candidate("DEP", category="dependency", scanner="osv-scanner", rule="GHSA-X", path="uv.lock", context={
        "scanned_package": {"name": "actual-lib", "version": "2.0.0", "ecosystem": "PyPI"},
        "installed_version_affected": False,
        "nested_affected_package": "different-advisory-lib",
    })
    finding = lineage_then_triage([current], [])["findings"][0]
    assert finding["dependency_package"] == "actual-lib"
    assert finding["dependency_version"] == "2.0.0"
    assert finding["technical_triage_verdict"] == "not_actionable"
    assert "nested_advisory_package_ignored=different-advisory-lib" in finding["counterevidence"]


def test_context_enrichment_preserves_scanned_identity_without_secret_value() -> None:
    canonical = register([candidate("DEP", category="dependency", scanner="osv-scanner", rule="GHSA-X", path="uv.lock")])
    scan = {"scanner_results": [{"scanner_name": "osv-scanner", "category": "dependency", "findings": [{
        "id": "GHSA-X", "dependency_path": "uv.lock", "line": 10,
        "osv_scanned_package": "actual-lib", "osv_scanned_version": "2.0.0", "osv_scanned_ecosystem": "PyPI",
        "affected": [{"package": {"name": "nested-lib"}}], "secret": "must-not-retain",
    }]}]}
    result = enrich_canonical_candidate_evidence(canonical, scan)
    evidence = result["findings"][0]["deterministic_evidence"]
    assert evidence["scanned_package"]["name"] == "actual-lib"
    assert evidence["advisory_affected_packages"] == ["nested-lib"]
    assert "secret" not in evidence
    assert result["candidate_evidence_context"]["candidate_counts_changed"] is False


def test_clustering_preserves_candidates_counts_and_is_deterministic() -> None:
    first = candidate("A", category="static", path="tests/example.py", context={"executable_code": False, "comment_or_string": True, "scope": "test"}, occurrence_count=2)
    second = candidate("B", category="static", path="tests/example.py", context={"executable_code": False, "comment_or_string": True, "scope": "test"}, occurrence_count=3)
    result1 = lineage_then_triage([first, second], [])
    result2 = lineage_then_triage([second, first], [])
    assert {item["candidate_id"] for item in result1["findings"]} == {"A", "B"}
    assert result1["technical_triage"]["total_candidates"] == 5
    assert result1["technical_triage"]["cluster_count"] == 1
    assert {item["cluster_id"] for item in result1["findings"]} == {item["cluster_id"] for item in result2["findings"]}
    assert all(item["cluster_size"] == 5 for item in result1["findings"])
    assert all(item["grouped_review_eligible"] is True for item in result1["findings"])


def test_workload_metrics_are_exact_and_deterministic() -> None:
    stable_prior = candidate("OLD"); stable = candidate("STABLE")
    uncertain = candidate("REVIEW", category="dependency", scanner="osv-scanner", rule="GHSA-U", context={})
    qc = candidate("QC", category="static", path="tests/example.py", context={"executable_code": False, "comment_or_string": True, "scope": "test"})
    result = lineage_then_triage([stable, uncertain, qc], [stable_prior], source_triage=retained_triage("OLD"))
    metrics = result["technical_triage"]["workload_metrics"]
    assert metrics == {key: result["technical_triage"][key] for key in metrics}
    assert metrics["total_candidates"] == 3
    assert metrics["technical_triage_completed"] == 3
    assert metrics["technical_triage_pending"] == 0
    assert metrics["not_actionable_count"] == 2
    assert metrics["needs_review_count"] == 1
    assert metrics["stable_carry_forward_count"] == 1
    assert metrics["candidates_requiring_individual_human_attention"] == 1
    assert metrics["quality_control_sample_pool"] == 1
