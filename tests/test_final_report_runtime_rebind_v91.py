from __future__ import annotations

from nico import comprehensive_final_report_compact_base_v1 as compact
from nico import comprehensive_final_report_execution_boundary_v4 as boundary
from nico import comprehensive_native_providers as providers
from nico import comprehensive_report_worker_runtime_v90 as v90
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico import comprehensive_spanish_exit_criteria_v88 as v88


_CONTEXT = {
    "run_id": "comprun_final_runtime_fixture",
    "repository": "BoneManTGRM/NICO",
    "commit_sha": "a" * 40,
    "evidence_ledger_id": "ledger_final_runtime_fixture",
    "customer_id": "customer_final_runtime_fixture",
    "project_id": "project_final_runtime_fixture",
    "assessment_depth": "strategic",
    "report_language": "es-MX",
    "prior_stage_results": {},
    "human_review_required": True,
    "client_delivery_allowed": False,
}


def _blocked_fixture_result() -> dict[str, object]:
    return {
        "status": "blocked",
        "reason": "fixture_stop_after_runtime_guard",
        "run_id": _CONTEXT["run_id"],
        "repository": _CONTEXT["repository"],
        "commit_sha": _CONTEXT["commit_sha"],
        "evidence_ledger_id": _CONTEXT["evidence_ledger_id"],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _wrapper_chain_contains(value: object, target: object, limit: int = 20) -> bool:
    current = value
    seen: set[int] = set()
    for _ in range(limit):
        if current is target:
            return True
        identity = id(current)
        if identity in seen:
            return False
        seen.add(identity)
        next_value = getattr(current, "_nico_previous", None)
        if next_value is None:
            next_value = getattr(current, "__wrapped__", None)
        if next_value is None:
            return False
        current = next_value
    return False


def test_final_report_boundary_repairs_stale_report_alias_before_executor(monkeypatch) -> None:
    def stale_report(context: dict[str, object], final: bool) -> dict[str, object]:
        raise AssertionError("stale pre-v90 report delegate must not execute")

    monkeypatch.setattr(providers, "_build_report", stale_report)
    monkeypatch.setattr(v88, "_ORIGINAL_NATIVE_BUILD_REPORT", stale_report)

    observed: dict[str, object] = {}

    def executor(context: dict[str, object]) -> dict[str, object]:
        observed["provider_alias"] = providers._build_report
        observed["v88_base"] = v88._ORIGINAL_NATIVE_BUILD_REPORT
        assert getattr(providers._build_report, compact._BUILD_MARKER, False) is True
        assert _wrapper_chain_contains(providers._build_report, v88._native_build_report_v88)
        assert v88._ORIGINAL_NATIVE_BUILD_REPORT is v90._native_report_base_v90
        return _blocked_fixture_result()

    result = boundary.execute_final_report_stage(
        executor,
        _CONTEXT,
        durable_coordinator_owns_lifetime=True,
    )

    assert result["status"] == "blocked"
    execution = result["stage_execution"]
    assert execution["report_runtime_v90_rebound"] is True
    assert execution["compact_final_report_runtime_rebound"] is True
    assert execution["runtime_guard_order"] == "v90_then_compact"
    assert execution["process_history_independent"] is True
    assert execution["recovery_entry_point_independent"] is True
    assert observed["v88_base"] is v90._native_report_base_v90


def test_final_report_boundary_rebinds_exact_production_spanish_contract(monkeypatch) -> None:
    # Establish the authoritative lower-level translator once, then simulate a process
    # whose public alias was replaced before final-report recovery begins.
    v88.install_comprehensive_spanish_exit_criteria_v88()
    assert v88._ORIGINAL_CANONICAL_TRANSLATE_FIELD is not None

    source = (
        "The exact-SHA rerun no longer reports cyclomatic complexity above 30 at "
        "nico/comprehensive_review_work_v1.py:323."
    )

    def stale_field(value: str, key: str) -> str:
        raise ValueError(f"missing Spanish presentation translation for {key}: {value}")

    monkeypatch.setattr(canonical, "_translate_presentation_field", stale_field)

    observed: dict[str, str] = {}

    def executor(context: dict[str, object]) -> dict[str, object]:
        translated = canonical._translate_presentation_field(
            source,
            "acceptance_criteria",
        )
        observed["translated"] = translated
        assert "La nueva ejecución sobre el SHA exacto" in translated
        assert "nico/comprehensive_review_work_v1.py:323" in translated
        assert "The exact-SHA rerun" not in translated
        return _blocked_fixture_result()

    result = boundary.execute_final_report_stage(
        executor,
        _CONTEXT,
        durable_coordinator_owns_lifetime=True,
    )

    assert result["status"] == "blocked"
    assert "La nueva ejecución sobre el SHA exacto" in observed["translated"]
    assert result["stage_execution"]["report_runtime_v90_rebound"] is True
    assert result["stage_execution"]["compact_final_report_runtime_rebound"] is True


def test_final_report_runtime_guard_executes_before_managed_provider(monkeypatch) -> None:
    events: list[str] = []
    original = boundary._install_final_report_runtime_guards

    def install() -> dict[str, object]:
        events.append("runtime_guard")
        return original()

    def executor(context: dict[str, object]) -> dict[str, object]:
        events.append("provider")
        return _blocked_fixture_result()

    monkeypatch.setattr(boundary, "_install_final_report_runtime_guards", install)

    result = boundary.execute_final_report_stage(
        executor,
        _CONTEXT,
        durable_coordinator_owns_lifetime=True,
    )

    assert result["status"] == "blocked"
    assert events == ["runtime_guard", "provider"]
