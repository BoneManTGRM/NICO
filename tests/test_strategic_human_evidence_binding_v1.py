from __future__ import annotations

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_binding_v1 import (
    install_strategic_human_evidence_binding,
)
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence


def _provider_with_limit(context: dict) -> dict:
    return {
        "status": "complete",
        "summary": "Repository-only evidence was reviewed.",
        "evidence": {"repository_test_paths": 12},
        "unavailable_data_notes": [
            "Runtime user-journey execution and stakeholder acceptance testing were not available from repository evidence alone."
        ],
        "run_id": context["run_id"],
        "repository": context["repository"],
        "commit_sha": context["commit_sha"],
        "evidence_ledger_id": context["evidence_ledger_id"],
    }


def _context(human_evidence: dict) -> dict:
    return {
        "run_id": "run-1",
        "repository": "owner/repo",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger-1",
        "customer_id": "customer-1",
        "project_id": "project-1",
        "human_evidence": normalize_strategic_human_evidence(human_evidence),
    }


def _providers() -> dict:
    return {
        capability: _provider_with_limit
        for capability in (
            "functional_qa",
            "platform_parity",
            "stakeholder_alignment",
            "requirements_traceability",
            "roadmap",
            "resourcing",
            "executive_briefing",
        )
    }


def test_binding_attaches_decision_grade_evidence_without_scoring_it() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = _providers()

    status = install_strategic_human_evidence_binding(app)
    provider = getattr(app.state, PROVIDER_STATE_KEY)["functional_qa"]
    result = provider(
        _context(
            {
                "functional_qa": {
                    "evidence": {
                        "test_cases": [{"scenario": "checkout", "expected": "success"}],
                        "observed_results": [{"scenario": "checkout", "actual": "success"}],
                    },
                    "reviewer": "QA lead",
                    "observed_at": "2026-07-25T23:00:00Z",
                    "source_reference": "evidence://qa/checkout",
                }
            }
        )
    )

    assert status["bound"] is True
    assert status["existing_decision_grade_ledger_reused"] is True
    assert result["human_evidence_summary"]["status"] == "complete"
    assert result["human_evidence_summary"]["directly_scored"] is False
    assert result["human_evidence_summary"]["module_ids"] == ["functional_qa"]
    assert result["human_evidence"]["functional_qa"]["reviewer"] == "QA lead"
    assert result["human_evidence"]["functional_qa"]["observed_results"][0][
        "actual"
    ] == "success"
    assert result["unavailable_data_notes"] == []
    assert result["client_delivery_allowed"] is False


def test_partial_human_evidence_remains_review_limited() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = _providers()
    install_strategic_human_evidence_binding(app)

    result = getattr(app.state, PROVIDER_STATE_KEY)["functional_qa"](
        _context(
            {
                "functional_qa": {
                    "evidence": {"test_cases": [{"scenario": "checkout"}]},
                    "reviewer": "QA lead",
                }
            }
        )
    )

    assert result["human_evidence_summary"]["status"] == "review_limited"
    assert result["human_evidence_summary"]["partial_count"] == 1
    assert result["unavailable_data_notes"]


def test_missing_human_evidence_remains_not_assessed() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = _providers()
    install_strategic_human_evidence_binding(app)

    result = getattr(app.state, PROVIDER_STATE_KEY)["functional_qa"](_context({}))

    assert result["human_evidence_summary"]["status"] == "not_assessed"
    assert result["human_evidence"] == {}
    assert result["unavailable_data_notes"]


def test_missing_provider_prevents_ready_binding() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = {
        "functional_qa": _provider_with_limit
    }

    status = install_strategic_human_evidence_binding(app)

    assert status["bound"] is False
    assert "executive_briefing" in status["missing_capabilities"]
