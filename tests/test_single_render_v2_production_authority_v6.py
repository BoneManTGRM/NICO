from __future__ import annotations

from typing import Any

from nico.comprehensive_canonical_report_source_v1 import (
    build_canonical_report_source,
)
from nico import v2_production_authority as authority


def _context() -> dict[str, Any]:
    return {
        "run_id": "comprun_single_render",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_single_render",
        "customer_id": "customer",
        "project_id": "project",
        "report_language": "en",
        "prior_stage_results": {
            "authorization_and_scope": {
                "status": "complete",
                "evidence": {"authorized": True},
            },
            "evidence_reconciliation_and_scoring": {
                "status": "complete",
                "assessment": {
                    "technical_score": 92,
                    "canonical_evidence_adjusted_score": 90,
                    "maturity_signal": {
                        "technical_score": 92,
                        "canonical_evidence_adjusted_score": 90,
                        "presented_score": 92,
                    },
                    "sections": [],
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "evidence": {},
            },
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_canonical_source_contains_truth_without_legacy_artifacts() -> None:
    source = build_canonical_report_source(_context())

    assert source["status"] == "complete"
    package = source["report_package"]
    assert package["canonical_only_source"] is True
    assert package["legacy_markdown_rendered"] is False
    assert package["legacy_html_rendered"] is False
    assert package["legacy_pdf_rendered"] is False
    assert "markdown" not in package
    assert "html" not in package
    assert "pdf_base64" not in package
    assert package["json"]["identity"]["run_id"] == "comprun_single_render"
    assert package["canonical_truth_sha256"]
    assert source["human_review_required"] is True
    assert source["client_delivery_allowed"] is False


def test_empty_stage_context_is_not_treated_as_production_canonical_source() -> None:
    context = _context()
    context["prior_stage_results"] = {}

    source = build_canonical_report_source(context)

    assert source["status"] == "blocked"
    assert source["reason"] == "canonical_report_stage_results_unavailable"
    assert source["human_review_required"] is True
    assert source["client_delivery_allowed"] is False


def test_v2_authority_skips_legacy_delegate_and_renders_once(monkeypatch) -> None:
    delegate_calls = 0
    observed_source: dict[str, Any] = {}

    def delegate(context: dict[str, Any]) -> dict[str, Any]:
        nonlocal delegate_calls
        delegate_calls += 1
        raise AssertionError("legacy delegate must not render production artifacts")

    def finalize(source: dict[str, Any]) -> dict[str, Any]:
        observed_source.update(source)
        package = source["report_package"]
        assert package["canonical_only_source"] is True
        assert "pdf_base64" not in package
        return {
            "status": "review_required",
            "report_package": {
                "json": package["json"],
                "report_id": package["report_id"],
                "markdown": "# NICO Comprehensive Technical Assessment",
                "html": "<html><body>NICO Comprehensive Technical Assessment</body></html>",
                "pdf_base64": "JVBERi0xLjQKJSVFT0YK",
                "canonical_truth_sha256": package["canonical_truth_sha256"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "canonical_truth_sha256": package["canonical_truth_sha256"],
            "report_language": "en",
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    monkeypatch.setattr(authority, "finalize_report_package", finalize)
    wrapped = authority.wrap_final_report_publication(delegate)
    result = wrapped(_context())

    assert delegate_calls == 0
    assert observed_source["canonical_only_source"] is True
    contract = result["v2_production_authority"]
    assert contract["canonical_only_source_used"] is True
    assert contract["legacy_delegate_render_skipped"] is True
    assert contract["legacy_pdf_rendered"] is False
    assert contract["all_artifacts_rendered_once_after_canonicalization"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False


def test_delegate_fallback_remains_for_noncanonical_synthetic_callers(monkeypatch) -> None:
    calls = 0

    def delegate(context: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"status": "blocked", "reason": "synthetic_fallback"}

    wrapped = authority.wrap_final_report_publication(delegate)
    result = wrapped({"run_id": "synthetic"})

    assert calls == 1
    assert result["status"] == "blocked"
    assert result["reason"] == "synthetic_fallback"


def test_delegate_fallback_remains_for_identity_complete_empty_stage_context(monkeypatch) -> None:
    calls = 0

    def delegate(context: dict[str, Any]) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {
            "status": "complete",
            "report_package": {
                "json": {"identity": {"run_id": context["run_id"]}},
                "report_id": "synthetic-report",
            },
        }

    context = _context()
    context["prior_stage_results"] = {}
    wrapped = authority.wrap_final_report_publication(delegate)
    result = wrapped(context)

    assert calls == 1
    assert result["v2_production_authority"]["canonical_only_source_used"] is False
    assert result["v2_production_authority"]["legacy_delegate_render_skipped"] is False
