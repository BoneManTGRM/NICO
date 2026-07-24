from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_repository_evidence_is_wrapped_with_classified_run_history() -> None:
    source = _read("nico/ci_run_classification_v1.py")

    assert "snapshot_evidence._workflow_summary = workflow_summary_with_classification" in source
    assert 'summary["raw_non_success_runs"]' in source
    assert 'summary["actionable_non_success_runs"]' in source
    assert 'summary["unclassified_non_success_runs"]' in source
    assert 'summary["expected_or_informational_non_success_runs"]' in source
    assert 'summary["classified_release_success_rate"]' in source
    assert "Expected cancellations and informational outcomes are excluded" in source


def test_canonical_scoring_uses_classified_ci_result_not_raw_non_success_count() -> None:
    source = _read("nico/comprehensive_decision_grade_v5.py")

    assert "scoring_provider_with_ci_classification" in source
    assert "providers.canonical_scoring_provider = scoring_provider_with_ci_classification" in source
    assert '"non_success_runs_classified"' in source
    assert '"expected_cancellations_excluded_from_reliability"' in source
    assert '"unclassified_runs_remain_review_limited"' in source


def test_classified_ci_ledger_is_exported_and_hashed_without_raw_logs() -> None:
    source = _read("nico/canonical_ci_report_binding_v1.py")
    binding = _read("nico/comprehensive_decision_grade_v5.py")

    assert "install_canonical_ci_report_binding_v1" in binding
    assert 'package["ci_run_classification_json"]' in source
    assert 'package["ci_run_classification_sha256"]' in source
    assert 'exports["ci_run_classification_json_sha256"]' in source
    assert 'item["status"] = "ready"' in source
    assert '"raw_ci_logs_exported": False' in source
    assert '"unclassified_ci_runs_disclosed": True' in source
