from __future__ import annotations

from typing import Any

from nico.decision_grade_contract_v1 import build_decision_grade_contract
from nico.decision_grade_history_store_v1 import (
    enrich_report_identity_with_history,
    find_previous_compatible_assessment,
    wrap_report_builder_with_persisted_history,
)
from nico.storage import MemoryAdapter

REPOSITORY = "BoneManTGRM/NICO"


def _contract(run_id: str, completed_at: str, *, repository: str = REPOSITORY, assessment_type: str = "comprehensive"):
    assessment = {
        "technical_score": 82,
        "canonical_evidence_adjusted_score": 78,
        "findings_register": [],
    }
    contract = build_decision_grade_contract(
        identity={
            "run_id": run_id,
            "repository": repository,
            "commit_sha": (run_id[-1] if run_id[-1].isalnum() else "a") * 40,
            "assessment_type": assessment_type,
            "branch": "main",
            "nico_version": "0.1.1",
            "scanner_configuration_version": "test-v1",
            "assessment_completed_at": completed_at,
        },
        assessment=assessment,
        stage_summaries=[],
        roadmap=[],
        report_template_version="nico.comprehensive_decision_grade.v5",
        pdf_page_count=10,
        core_page_count=7,
        generated_at=completed_at,
    )
    return contract, assessment


def _put(
    store: MemoryAdapter,
    run_id: str,
    completed_at: str,
    *,
    customer_id: str = "customer-1",
    project_id: str = "project-1",
    repository: str = REPOSITORY,
    assessment_type: str = "comprehensive",
    nested: bool = False,
) -> None:
    contract, assessment = _contract(run_id, completed_at, repository=repository, assessment_type=assessment_type)
    payload: dict[str, Any] = {
        "decision_grade_contract": contract.model_dump(mode="json"),
        "assessment": assessment,
    }
    if nested:
        payload = {"reports": {"report_package": payload}}
    store.put(
        "assessment_runs",
        run_id,
        {
            "run_id": run_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "workflow": "full_assessment",
            "status": "complete",
            "repository": repository,
            "response": payload,
            "created_at": completed_at,
        },
    )


def test_newest_compatible_retained_contract_is_selected() -> None:
    store = MemoryAdapter()
    _put(store, "run-a", "2026-07-20T10:00:00Z")
    _put(store, "run-b", "2026-07-21T10:00:00Z", nested=True)
    selection = find_previous_compatible_assessment(
        repository=REPOSITORY,
        assessment_type="comprehensive",
        current_assessment_id="run-current",
        customer_id="customer-1",
        project_id="project-1",
        store=store,
    )
    assert selection["selected"] is True
    assert selection["previous_assessment_id"] == "run-b"
    assert selection["previous_assessment"]["technical_score"] == 82
    assert selection["synthetic_history_generated"] is False


def test_current_run_and_incompatible_records_are_rejected() -> None:
    store = MemoryAdapter()
    _put(store, "run-current", "2026-07-24T10:00:00Z")
    _put(store, "run-other-repo", "2026-07-23T10:00:00Z", repository="other/repository")
    _put(store, "run-mid", "2026-07-22T10:00:00Z", assessment_type="mid")
    store.put(
        "assessment_runs",
        "run-invalid",
        {
            "run_id": "run-invalid",
            "customer_id": "customer-1",
            "project_id": "project-1",
            "workflow": "full_assessment",
            "response": {"decision_grade_contract": {"status": "invalid"}},
        },
    )
    selection = find_previous_compatible_assessment(
        repository=REPOSITORY,
        assessment_type="comprehensive",
        current_assessment_id="run-current",
        customer_id="customer-1",
        project_id="project-1",
        store=store,
    )
    assert selection["selected"] is False
    assert selection["status"] == "no_comparable_previous_assessment"
    assert selection["rejected_counts"] == {
        "current_assessment": 1,
        "non_full_workflow": 0,
        "missing_or_invalid_contract": 1,
        "repository_mismatch": 1,
        "assessment_type_mismatch": 1,
        "schema_family_mismatch": 0,
    }


def test_newer_incompatible_schema_is_skipped_for_older_compatible_contract() -> None:
    store = MemoryAdapter()
    _put(store, "run-compatible", "2026-07-20T10:00:00Z")
    contract, assessment = _contract("run-legacy", "2026-07-24T10:00:00Z")
    raw = contract.model_dump(mode="json")
    raw["schema_version"] = "legacy.other_contract.v1"
    store.put(
        "assessment_runs",
        "run-legacy",
        {
            "run_id": "run-legacy",
            "customer_id": "customer-1",
            "project_id": "project-1",
            "workflow": "full_assessment",
            "status": "complete",
            "response": {"decision_grade_contract": raw, "assessment": assessment},
        },
    )
    selection = find_previous_compatible_assessment(
        repository=REPOSITORY,
        assessment_type="comprehensive",
        current_assessment_id="run-current",
        customer_id="customer-1",
        project_id="project-1",
        store=store,
    )
    assert selection["previous_assessment_id"] == "run-compatible"
    assert selection["rejected_counts"]["schema_family_mismatch"] == 1


def test_customer_and_project_scope_is_enforced() -> None:
    store = MemoryAdapter()
    _put(store, "run-outside", "2026-07-24T10:00:00Z", customer_id="customer-2", project_id="project-2")
    _put(store, "run-inside", "2026-07-20T10:00:00Z")
    selection = find_previous_compatible_assessment(
        repository=REPOSITORY,
        assessment_type="comprehensive",
        current_assessment_id="run-current",
        customer_id="customer-1",
        project_id="project-1",
        store=store,
    )
    assert selection["previous_assessment_id"] == "run-inside"
    assert selection["records_examined"] == 1


def test_identity_enrichment_supplies_previous_contract_and_discloses_durability() -> None:
    store = MemoryAdapter()
    _put(store, "run-a", "2026-07-20T10:00:00Z")
    enriched, selection = enrich_report_identity_with_history(
        {
            "run_id": "run-current",
            "repository": REPOSITORY,
            "customer_id": "customer-1",
            "project_id": "project-1",
        },
        store=store,
    )
    assert enriched["previous_comparable_assessment_id"] == "run-a"
    assert enriched["previous_decision_grade_contract"]["identity"]["assessment_id"] == "run-a"
    assert enriched["historical_comparison_selection"]["durability_verified"] is False
    assert "previous_decision_grade_contract" not in enriched["historical_comparison_selection"]
    assert selection["storage_adapter"] == "memory"


def test_report_wrapper_attaches_selection_and_passes_history_to_delegate() -> None:
    store = MemoryAdapter()
    _put(store, "run-a", "2026-07-20T10:00:00Z")
    captured: dict[str, Any] = {}

    def delegate(*, identity: dict[str, Any], stage_results: dict[str, Any]) -> dict[str, Any]:
        captured.update(identity)
        return {"status": "complete", "report_package": {}, "report_quality_contract": {}}

    wrapped = wrap_report_builder_with_persisted_history(delegate, store=store)
    result = wrapped(
        identity={
            "run_id": "run-current",
            "repository": REPOSITORY,
            "customer_id": "customer-1",
            "project_id": "project-1",
        },
        stage_results={},
    )
    assert captured["previous_comparable_assessment_id"] == "run-a"
    assert result["historical_comparison_selection"]["previous_assessment_id"] == "run-a"
    assert result["report_quality_contract"]["previous_compatible_assessment_selected"] is True
    assert result["report_quality_contract"]["historical_comparison_synthetic"] is False


def test_history_storage_failure_does_not_fabricate_or_block_report() -> None:
    class BrokenStore:
        def status(self):
            raise RuntimeError("offline")

        def list(self, *args, **kwargs):
            raise RuntimeError("offline")

    wrapped = wrap_report_builder_with_persisted_history(
        lambda **kwargs: {"status": "complete", "report_package": {}, "report_quality_contract": {}},
        store=BrokenStore(),  # type: ignore[arg-type]
    )
    result = wrapped(
        identity={
            "run_id": "run-current",
            "repository": REPOSITORY,
            "customer_id": "customer-1",
            "project_id": "project-1",
        },
        stage_results={},
    )
    assert result["status"] == "complete"
    assert result["historical_comparison_selection"]["status"] == "history_store_unavailable"
    assert result["report_quality_contract"]["persisted_history_lookup_completed"] is False
    assert result["report_quality_contract"]["historical_comparison_synthetic"] is False
