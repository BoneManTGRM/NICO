from __future__ import annotations

from fastapi import FastAPI

from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_binding_v1 import (
    install_strategic_human_evidence_binding,
)


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
        "human_evidence": human_evidence,
    }


def test_binding_attaches_provided_evidence_without_scoring_it() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = {
        "functional_qa": _provider_with_limit,
        "platform_parity": _provider_with_limit,
        "stakeholder_alignment": _provider_with_limit,
        "requirements_traceability": _provider_with_limit,
        "roadmap": _provider_with_limit,
        "resourcing": _provider_with_limit,
        "executive_briefing": _provider_with_limit,
    }

    status = install_strategic_human_evidence_binding(app)
    provider = getattr(app.state, PROVIDER_STATE_KEY)["functional_qa"]
    result = provider(
        _context(
            {
                "functional_qa": {
                    "records": [{"scenario": "checkout", "status": "passed"}],
                    "attachment_refs": ["evidence://qa/checkout"],
                }
            }
        )
    )

    assert status["bound"] is True
    assert result["human_evidence"]["status"] == "provided"
    assert result["human_evidence"]["directly_scored"] is False
    assert result["human_evidence"]["module_ids"] == ["functional_qa"]
    assert result["unavailable_data_notes"] == []
    assert result["client_delivery_allowed"] is False


def test_missing_human_evidence_remains_not_assessed() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = {
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
    install_strategic_human_evidence_binding(app)

    result = getattr(app.state, PROVIDER_STATE_KEY)["functional_qa"](_context({}))

    assert result["human_evidence"]["status"] == "not_assessed"
    assert result["unavailable_data_notes"]


def test_missing_provider_prevents_ready_binding() -> None:
    app = FastAPI()
    app.state.comprehensive_capability_providers = {"functional_qa": _provider_with_limit}

    status = install_strategic_human_evidence_binding(app)

    assert status["bound"] is False
    assert "executive_briefing" in status["missing_capabilities"]
