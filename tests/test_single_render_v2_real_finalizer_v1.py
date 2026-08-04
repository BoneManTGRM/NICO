from __future__ import annotations

import base64

from nico.v2_production_authority import wrap_final_report_publication


GENERATED_AT = "2026-08-04T16:15:00Z"


def _context() -> dict:
    return {
        "run_id": "comprun_real_single_render",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_real_single_render",
        "customer_id": "customer",
        "project_id": "project",
        "generated_at": GENERATED_AT,
        "report_language": "en",
        "prior_stage_results": {
            "authorization_and_scope": {
                "status": "complete",
                "summary": "Authorized read-only assessment.",
                "evidence": {"authorization_confirmed": True},
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "immutable_repository_snapshot": {
                "status": "complete",
                "summary": "Immutable repository snapshot captured.",
                "evidence": {"commit_sha": "a" * 40},
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "evidence_reconciliation_and_scoring": {
                "status": "complete",
                "assessment": {
                    "technical_score": 92,
                    "evidence_adjusted_score": 90,
                    "canonical_evidence_adjusted_score": 90,
                    "maturity_signal": {
                        "level": "Exceptional",
                        "score": 92,
                        "technical_score": 92,
                        "source_score": 92,
                        "presented_score": 92,
                        "evidence_adjusted_score": 90,
                        "canonical_evidence_adjusted_score": 90,
                    },
                    "sections": [],
                    "human_review_required": True,
                    "client_delivery_allowed": False,
                },
                "evidence": {
                    "technical_score": 92,
                    "evidence_adjusted_score": 90,
                },
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
            "risk_reduction_and_executive_briefing": {
                "status": "complete",
                "summary": "Evidence-bound risk reduction plan prepared.",
                "evidence": {},
                "human_review_required": True,
                "client_delivery_allowed": False,
            },
        },
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def test_real_v2_finalizer_renders_once_from_canonical_source() -> None:
    delegate_calls = 0

    def legacy_delegate(_context: dict) -> dict:
        nonlocal delegate_calls
        delegate_calls += 1
        raise AssertionError("legacy renderer must be skipped")

    result = wrap_final_report_publication(legacy_delegate)(_context())

    assert delegate_calls == 0
    assert result["status"] == "complete", result
    package = result["report_package"]
    assert package["markdown"]
    assert package["html"]
    assert package["json"]["identity"]["run_id"] == "comprun_real_single_render"
    assert package["json"]["identity"]["generated_at"] == GENERATED_AT
    assert base64.b64decode(package["pdf_base64"]).startswith(b"%PDF")
    assert package["canonical_truth_sha256"]
    contract = result["v2_production_authority"]
    assert contract["canonical_only_source_used"] is True
    assert contract["legacy_delegate_render_skipped"] is True
    assert contract["all_artifacts_rendered_once_after_canonicalization"] is True
    assert result["human_review_required"] is True
    assert result["client_delivery_allowed"] is False
