from __future__ import annotations

from types import SimpleNamespace

from nico import assessment_score_integrity
from nico import express_async_api
from nico import hosted_report_intelligence_enrichment as enrichment
from nico import post_polish_score_reconciliation_patch as post_polish
from nico import report_intelligence_accuracy_patch as accuracy
from nico.express_completion_score_binding import (
    bind_api_main_response,
    finalize_report_intelligence_at_response,
    install_express_completion_score_binding,
)


QUALITY_HEADING = "## Repository Quality and Governance Signals"
REPAIR_HEADING = "## Prioritized Repair Intelligence"


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


def test_final_response_attaches_and_exports_report_intelligence(monkeypatch) -> None:
    enrich_calls: list[dict] = []
    rebuild_calls: list[dict] = []

    def fake_enrich(_hosted, value: dict) -> dict:
        enrich_calls.append(dict(value))
        enriched = dict(value)
        enriched["repository_quality_signals"] = {
            "status": "complete",
            "findings": [{"title": "Large branch inventory"}],
        }
        enriched["repair_intelligence"] = {
            "status": "complete",
            "mode": "report_only",
            "candidate_count": 3,
            "code_suggestion_count": 1,
            "candidates": [],
        }
        return enriched

    def fake_rebuild(_hosted, value: dict) -> dict:
        rebuild_calls.append(dict(value))
        rebuilt = dict(value)
        rebuilt["reports"] = {
            "markdown": f"# NICO\n\n{QUALITY_HEADING}\n\nquality\n\n{REPAIR_HEADING}\n\nrepairs\n",
            "html": "<html>quality and repairs</html>",
            "pdf_base64": "cGRm",
        }
        return rebuilt

    monkeypatch.setattr(enrichment, "enrich_hosted_result", fake_enrich)
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "human_review_required": True,
            "client_ready": False,
            "reports": {"markdown": "stale report without intelligence"},
        }
    )

    assert len(enrich_calls) == 1
    assert len(rebuild_calls) == 1
    assert response["maturity_signal"]["score"] == 92
    assert QUALITY_HEADING in response["reports"]["markdown"]
    assert REPAIR_HEADING in response["reports"]["markdown"]
    assert response["report_intelligence_export"] == {
        "status": "complete",
        "final_response_boundary_applied": True,
        "repository_quality_signals_attached": True,
        "repair_intelligence_attached": True,
        "repository_quality_markdown_exported": True,
        "repair_intelligence_markdown_exported": True,
        "repair_candidate_count": 3,
        "code_suggestion_count": 1,
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


def test_final_response_rebuilds_stale_export_without_refetching(monkeypatch) -> None:
    enrich_called = False

    def unexpected_enrich(_hosted, value: dict) -> dict:
        nonlocal enrich_called
        enrich_called = True
        return value

    def fake_rebuild(_hosted, value: dict) -> dict:
        rebuilt = dict(value)
        rebuilt["reports"] = {
            "markdown": f"{QUALITY_HEADING}\n\n{REPAIR_HEADING}\n",
        }
        return rebuilt

    monkeypatch.setattr(enrichment, "enrich_hosted_result", unexpected_enrich)
    monkeypatch.setattr(accuracy, "rebuild_enriched_reports", fake_rebuild)

    response = finalize_report_intelligence_at_response(
        {
            "status": "complete",
            "repository": "owner/repo",
            "maturity_signal": {"score": 92},
            "repository_quality_signals": {"status": "complete"},
            "repair_intelligence": {
                "status": "complete",
                "candidate_count": 2,
                "code_suggestion_count": 1,
            },
            "reports": {"markdown": "old export"},
        }
    )

    assert enrich_called is False
    assert response["report_intelligence_export"]["status"] == "complete"
    assert response["report_intelligence_export"]["repair_candidate_count"] == 2
    assert response["report_intelligence_export"]["code_suggestion_count"] == 1


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
    # Late diagnostics installers may legitimately become the outermost _execute
    # wrapper. Railway imports and calls this patched score-integrity installer only
    # after nico.api.main is fully loaded, so the final response boundary—not wrapper
    # name or nesting order—is the production contract.
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
