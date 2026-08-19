from __future__ import annotations

from nico import comprehensive_native_providers as providers
from nico import comprehensive_report_worker_runtime_v90 as v90
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico.comprehensive_stage_execution_timeout_v1 import execute_stage_with_timeout


_CONTEXT = {
    "run_id": "comprun_decision_runtime_fixture",
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger-decision-runtime-fixture",
    "customer_id": "customer-decision-runtime-fixture",
    "project_id": "project-decision-runtime-fixture",
    "assessment_depth": "strategic",
    "report_language": "es-MX",
    "prior_stage_results": {},
    "human_review_required": True,
    "client_delivery_allowed": False,
}


def test_decision_report_timeout_boundary_repairs_stale_report_runtime(monkeypatch) -> None:
    def stale_report(context: dict[str, object], final: bool) -> dict[str, object]:
        raise AssertionError("stale report delegate must not execute")

    monkeypatch.setattr(providers, "_build_report", stale_report)
    monkeypatch.setattr(v88, "_ORIGINAL_NATIVE_BUILD_REPORT", stale_report)

    observed: dict[str, object] = {}

    def executor(context: dict[str, object]) -> dict[str, object]:
        observed["provider_alias"] = providers._build_report
        observed["v88_base"] = v88._ORIGINAL_NATIVE_BUILD_REPORT
        assert providers._build_report is v88._native_build_report_v88
        assert v88._ORIGINAL_NATIVE_BUILD_REPORT is v90._native_report_base_v90
        return {
            "status": "complete",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "commit_sha": context["commit_sha"],
            "evidence_ledger_id": context["evidence_ledger_id"],
        }

    result = execute_stage_with_timeout(
        executor,
        _CONTEXT,
        stage_id="decision_report_generation",
        timeout_seconds=5,
    )

    assert result["status"] == "complete"
    execution = result["stage_execution"]
    assert execution["report_runtime_v90_rebound"] is True
    assert execution["report_runtime_boundary"] == "universal_stage_execution_timeout"
    assert execution["report_runtime_process_history_independent"] is True
    assert observed["v88_base"] is v90._native_report_base_v90


def test_decision_report_boundary_rebinds_exact_spanish_acceptance_contract(monkeypatch) -> None:
    v88.install_comprehensive_spanish_exit_criteria_v88()
    source = (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323."
    )

    def stale_field(value: str, key: str) -> str:
        raise ValueError(f"missing Spanish presentation translation for {key}: {value}")

    monkeypatch.setattr(canonical, "_translate_presentation_field", stale_field)
    observed: dict[str, str] = {}

    def executor(context: dict[str, object]) -> dict[str, object]:
        translated = canonical._translate_presentation_field(source, "acceptance_criteria")
        observed["translated"] = translated
        return {
            "status": "complete",
            "run_id": context["run_id"],
            "repository": context["repository"],
            "commit_sha": context["commit_sha"],
            "evidence_ledger_id": context["evidence_ledger_id"],
        }

    result = execute_stage_with_timeout(
        executor,
        _CONTEXT,
        stage_id="decision_report_generation",
        timeout_seconds=5,
    )

    assert result["status"] == "complete"
    assert "La nueva ejecución sobre el SHA exacto" in observed["translated"]
    assert "nico/comprehensive_review_work_v1.py:323" in observed["translated"]
    assert "The exact-SHA rerun" not in observed["translated"]


def test_non_report_stage_does_not_claim_report_runtime_rebind() -> None:
    def executor(context: dict[str, object]) -> dict[str, object]:
        return {"status": "complete"}

    result = execute_stage_with_timeout(
        executor,
        _CONTEXT,
        stage_id="functional_qa",
        timeout_seconds=5,
    )

    assert result["status"] == "complete"
    assert "report_runtime_v90_rebound" not in result["stage_execution"]
