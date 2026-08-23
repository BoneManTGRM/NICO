from __future__ import annotations

from fastapi import FastAPI

from nico.comprehensive_capability_registry import execution_plan
from nico.comprehensive_production_capabilities import (
    PROVIDER_STATE_KEY,
    build_production_capability_executors,
)
from nico.hosted_provider_comprehensive_runtime_v1 import (
    install_hosted_provider_comprehensive_runtime,
)


def _provider(name: str):
    def execute(context: dict) -> dict:
        return {
            "status": "complete",
            "provider_marker": name,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    return execute


def test_hosted_runtime_changes_acquisition_only_and_preserves_every_downstream_capability() -> None:
    app = FastAPI()
    capabilities = {
        str(item["capability"])
        for item in execution_plan()
        if str(item["capability"]) != "authorization"
    }
    original = {name: _provider(name) for name in sorted(capabilities)}
    setattr(app.state, PROVIDER_STATE_KEY, dict(original))

    status = install_hosted_provider_comprehensive_runtime(app)
    installed = getattr(app.state, PROVIDER_STATE_KEY)

    assert installed["repository_evidence"] is not original["repository_evidence"]
    for name in sorted(capabilities - {"repository_evidence"}):
        assert installed[name] is original[name], name

    assert status["same_scanner_pipeline"] is True
    assert status["same_candidate_triage_report_pipeline"] is True
    assert status["operator_run_only"] is True
    assert status["customer_self_service"] is False
    assert status["human_review_required"] is True
    assert status["client_delivery_allowed"] is False

    executors = build_production_capability_executors(app)
    expected = {str(item["capability"]) for item in execution_plan()}
    assert set(executors) == expected

    context = {
        "service_id": "comprehensive",
        "run_id": "comprun_provider_downstream_parity",
        "repository": "gitlab.com/group/repo",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_provider_downstream_parity",
    }
    for name in (
        "scanner_suite",
        "technical_analysis",
        "canonical_scoring",
        "scanner_triage",
        "functional_qa",
        "platform_parity",
        "deployment_review",
        "architecture_data_flow",
        "delivery_process",
        "requirements_traceability",
        "historical_trends",
        "roadmap",
        "resourcing",
        "executive_briefing",
        "final_report_generation",
        "cross_format_verification",
        "human_review",
        "acceptance_gate",
    ):
        result = executors[name](dict(context))
        assert result["provider_marker"] == name
        assert result["capability"] == name
        assert result["run_id"] == context["run_id"]
        assert result["repository"] == context["repository"]
        assert result["commit_sha"] == context["commit_sha"]
        assert result["human_review_required"] is True
        assert result["client_delivery_allowed"] is False
