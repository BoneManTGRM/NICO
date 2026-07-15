from __future__ import annotations

from types import SimpleNamespace

from nico import assessment_score_integrity
from nico import express_async_api
from nico import hosted_report_intelligence_enrichment as enrichment
from nico import post_polish_score_reconciliation_patch as post_polish
from nico import report_intelligence_accuracy_patch as accuracy
from nico import report_repair_intelligence as repair_builder
from nico.express_completion_score_binding import (
    bind_api_main_response,
    finalize_report_intelligence_at_response,
    install_express_completion_score_binding,
)


QUALITY_HEADING = "## Repository Quality and Governance Signals"
REPAIR_HEADING = "## Prioritized Repair Intelligence"


def _fake_rebuild(_hosted, value: dict) -> dict:
    rebuilt = dict(value)
    rebuilt["reports"] = {
        "markdown": f"# NICO\n\n{QUALITY_HEADING}\n\nquality\n\n{REPAIR_HEADING}\n\nrepairs\n",
        "html": "<html>quality and repairs</html>",
        "pdf_base64": "cGRm",
    }
    return rebuilt


def test_response_boundary_reconciles_completed_assessment(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_reconcile(value: dict) -> dict:
        reconciled = dict(value)
        reconciled["final_score_reconciliation"] = {
            "status": "reconciled",
            "post_polish_applied": True,
        }
        calls.append(reconciled)
        return reconciled

    monkeypatch.setattr(post_polish, "reconcile_after_polish", fake_reconcile)
    api_main = SimpleNamespace(
        safe_assessment_response_payload=lambda value: dict(value),
    )

    installed = bind_api_main_response(api_main)
    response = api_main.safe_assessment_response_payload(
        {"status": "complete", "maturity_signal": {"score": 92}}
    )

    assert installed["status"] == "installed"
    assert installed["report_intelligence_export_bound"] is True
    assert response["final_score_reconciliation"]["post_polish_applied"] is True
    assert calls and calls[0]["maturity_signal"]["score"] == 92


def test_final_response_attaches_reconciles_and_exports_report_intelligence(monkeypatch) -> None:
    enrich_calls: list[dict] = []
    build_calls: list[tuple[dict, list[dict]]] = []

    def fake_enrich(_hosted, value: dict) -> dict:
        enrich_calls.append(dict(value))
        enriched = dict(value)
        enriched["repository_quality_signals"] = {
            "status": "complete",
            "findings": [
                {
                    "code": "branch_inventory_large",
                    "title": "Large branch inventory",
                    "severity": "high",
                    "category": "repository_hygiene",
                }
            ],
        }
        enriched["repair_intelligence"] = {
            "status": "complete",
            "candidate_count": 3,
            "code_suggestion_count": 2,
            "candidates": [{"title": "early candidate"}],
        }
        return enriched

    def fake_build(payload: dict, *, structured_findings: list[dict] | None = None) -> dict:
        build_calls.append((dict(payload), list(structured_findings or [])))
        return {
            "status": "complete",
            "mode": "report_only",
            "priority_model": "calibrated_weighted_v2",
            "candidate_count": 2,
            "code_suggestion_count": 1,
            "advisories": [{"title": "Repository size context"}],
            "candidates": [
                {
                    "title": "Final verified candidate",
                    "priority_score": 64.2,
                    "recommended_action": "Review the final finding.",
                    "code_suggestion": {"status": "available"},
                }
            ],
        }

    monkeypatch.setattr(enrichment, "enrich_hosted_result", fake_enrich)
    monkeypatch.setattr(repair_builder, "build_report_repair_intelligence", fake_build)
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "sections": [
                {"id": "trust_readiness", "findings": ["workflow state"]},
                {"id": "architecture_debt", "findings": ["final architecture finding"]},
                {"id": "client_acceptance", "findings": ["approval state"]},
            ],
            "human_review_required": True,
            "client_ready": False,
            "reports": {"markdown": "stale report without intelligence"},
        }
    )

    assert len(enrich_calls) == 1
    assert len(build_calls) == 1
    repair_source, structured = build_calls[0]
    assert [section["id"] for section in repair_source["sections"]] == ["architecture_debt"]
    assert structured[0]["code"] == "branch_inventory_large"
    assert response["maturity_signal"]["score"] == 92
    assert response["repair_intelligence"]["candidate_count"] == 2
    assert response["repairs"] == ["Review the final finding."]
    assert response["quick_wins"][0] == "Review the final finding."
    assert response["repair_action_summary"]["immediate_count"] == 1
    assert response["repair_action_summary"]["advisory_count"] == 1
    assert QUALITY_HEADING in response["reports"]["markdown"]
    assert REPAIR_HEADING in response["reports"]["markdown"]
    assert response["repair_intelligence_reconciliation"] == {
        "status": "reconciled",
        "source": "final_reconciled_sections_and_verified_repository_quality_findings",
        "priority_model": "calibrated_weighted_v2",
        "excluded_workflow_only_sections": ["client_acceptance", "trust_readiness"],
        "prior_candidate_count": 3,
        "final_candidate_count": 2,
        "final_code_suggestion_count": 1,
        "final_advisory_count": 1,
        "early_source_regex_candidates_carried_forward": False,
        "superseded_pre_polish_findings_carried_forward": False,
        "repository_size_ranked_as_defect": False,
        "human_review_required": True,
        "automatic_application_allowed": False,
    }
    assert response["report_intelligence_export"] == {
        "status": "complete",
        "final_response_boundary_applied": True,
        "repair_intelligence_reconciled_from_final_findings": True,
        "repository_quality_signals_attached": True,
        "repair_intelligence_attached": True,
        "repository_quality_markdown_exported": True,
        "repair_intelligence_markdown_exported": True,
        "priority_model": "calibrated_weighted_v2",
        "repair_candidate_count": 2,
        "code_suggestion_count": 1,
        "advisory_count": 1,
        "score_before": 92,
        "score_after": 92,
        "score_changed": False,
        "mode": "report_only",
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "automatic_commit_allowed": False,
        "automatic_pull_request_allowed": False,
        "human_review_required": True,
    }
    assert response["human_review_required"] is True
    assert response["client_ready"] is False


def test_clean_dependency_artifacts_remove_contradicted_unavailable_note(monkeypatch) -> None:
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete", "findings": []},
            "sections": [
                {
                    "id": "dependency_health",
                    "status": "green",
                    "score": 90,
                    "evidence": [
                        "Verified score lift: current-run dependency scanner artifacts are clean and bound to this report run.",
                        "Scanner-worker dependency tools completed: pip-audit, npm-audit, osv-scanner.",
                    ],
                    "findings": [],
                    "unavailable": [
                        "Full pip-audit, npm audit, and OSV Scanner CLI artifacts are still required before claiming final scanner-clean dependency status.",
                        "License-policy mapping requires human review.",
                    ],
                }
            ],
        }
    )

    unavailable = response["sections"][0]["unavailable"]
    assert unavailable == ["License-policy mapping requires human review."]
    assert response["repair_action_summary"]["dependency_quick_win_suppressed_because_scanners_clean"] is True


def test_clean_secret_scanners_remove_generic_secret_quick_win(monkeypatch) -> None:
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete", "findings": []},
            "quick_wins": [
                "Address any confirmed secret-pattern hit first and rotate real credentials outside NICO if applicable.",
                "Maintain current CI evidence.",
            ],
            "sections": [
                {
                    "id": "secrets_review",
                    "status": "green",
                    "score": 92,
                    "findings": [],
                    "evidence": [
                        "Parsed Gitleaks and TruffleHog full-history artifacts reported zero credential findings.",
                        "Current-run artifacts are clean.",
                    ],
                }
            ],
        }
    )

    assert not any("secret-pattern" in item.lower() for item in response["quick_wins"])
    assert "Maintain current CI evidence." in response["quick_wins"]
    assert response["repair_action_summary"]["secret_quick_win_suppressed_because_scanners_clean"] is True


def test_final_response_discards_early_regex_secret_candidates(monkeypatch) -> None:
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {
                "status": "complete",
                "findings": [
                    {
                        "code": "runtime_patch_surface",
                        "title": "Large runtime patch surface",
                        "severity": "high",
                        "confidence": 0.99,
                        "category": "runtime_patch_surface",
                        "evidence": ["38 patch modules and 42 installers"],
                        "affected_files": ["nico/__init__.py"],
                        "business_impact": "Import-order defects increase release cost.",
                        "technical_impact": "Runtime installer order is fragile.",
                        "recommendation": "Consolidate installers in stages.",
                        "verification_method": "Run import-order and full regression tests.",
                    }
                ],
            },
            "repair_intelligence": {
                "status": "complete",
                "candidate_count": 12,
                "code_suggestion_count": 12,
                "candidates": [
                    {
                        "title": "Potential secret exposure in config.py",
                        "category": "secret_exposure",
                    }
                ],
            },
            "sections": [
                {
                    "id": "secrets_review",
                    "status": "green",
                    "score": 92,
                    "findings": [],
                    "evidence": [
                        "Parsed Gitleaks and TruffleHog full-history artifacts reported zero credential findings."
                    ],
                },
                {
                    "id": "architecture_debt",
                    "findings": ["At least one function has high complexity."],
                },
            ],
        }
    )

    titles = [item["title"] for item in response["repair_intelligence"]["candidates"]]
    assert not any("secret exposure" in title.lower() for title in titles)
    assert "Large runtime patch surface" in titles
    assert response["repair_intelligence_reconciliation"]["prior_candidate_count"] == 12
    assert response["repair_intelligence_reconciliation"]["early_source_regex_candidates_carried_forward"] is False
    assert response["report_intelligence_export"]["repair_intelligence_reconciled_from_final_findings"] is True


def test_final_response_rebuilds_from_final_findings_without_refetching(monkeypatch) -> None:
    enrich_called = False

    def unexpected_enrich(_hosted, value: dict) -> dict:
        nonlocal enrich_called
        enrich_called = True
        return value

    monkeypatch.setattr(enrichment, "enrich_hosted_result", unexpected_enrich)
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", _fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete", "findings": []},
            "repair_intelligence": {
                "status": "complete",
                "candidate_count": 99,
                "code_suggestion_count": 99,
            },
            "sections": [
                {"id": "ci_cd", "findings": ["Historical failures require review."]},
            ],
            "reports": {"markdown": "old export"},
        }
    )

    assert enrich_called is False
    assert response["report_intelligence_export"]["status"] == "complete"
    assert response["report_intelligence_export"]["repair_candidate_count"] == 1
    assert response["repair_intelligence_reconciliation"]["prior_candidate_count"] == 99
    assert response["repair_intelligence_reconciliation"]["final_candidate_count"] == 1


def test_response_boundary_does_not_reconcile_nonterminal_state(monkeypatch) -> None:
    called = False

    def fake_reconcile(value: dict) -> dict:
        nonlocal called
        called = True
        return value

    monkeypatch.setattr(post_polish, "reconcile_after_polish", fake_reconcile)
    api_main = SimpleNamespace(
        safe_assessment_response_payload=lambda value: dict(value),
    )
    bind_api_main_response(api_main)

    response = api_main.safe_assessment_response_payload({"status": "running"})

    assert response["status"] == "running"
    assert called is False


def test_production_bootstrap_is_the_authoritative_binding() -> None:
    assert callable(express_async_api._execute)
    assert getattr(
        assessment_score_integrity.install_assessment_score_integrity,
        "_nico_express_completion_score_bootstrap_v1",
        False,
    ) is True


def test_installer_is_idempotent() -> None:
    first = install_express_completion_score_binding()
    second = install_express_completion_score_binding()

    assert first["async_execute"]["async_execute_bound"] is True
    assert second["async_execute"]["status"] == "already_installed"
    assert second["production_bootstrap"]["status"] == "already_installed"
    assert second["score_inflation_allowed"] is False
    assert second["report_intelligence_export_bound"] is True
    assert second["repair_intelligence_reconciled_from_final_findings"] is True
    assert second["client_actions_reconciled_from_final_findings"] is True
