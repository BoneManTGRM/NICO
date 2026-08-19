from __future__ import annotations

from pathlib import Path

from nico import comprehensive_ci_pdf_control_safety_v89 as v89
from nico import comprehensive_native_providers as providers
from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer
from nico import comprehensive_spanish_exit_criteria_v88 as v88
from nico import comprehensive_report_worker_runtime_v90 as v90


ROOT = Path(__file__).resolve().parents[1]
BACKGROUND = ROOT / "nico/comprehensive_stage_background_v2.py"


def test_v90_repairs_first_install_after_recursive_public_aliases(monkeypatch) -> None:
    def recursive_report(context: dict[str, object], final: bool) -> dict[str, object]:
        return providers._build_report(context, final)

    def recursive_pdf(*args: object, **kwargs: object) -> bytes:
        return producer._boundary_pdf_page(*args, **kwargs)

    monkeypatch.setattr(v88, "_ORIGINAL_NATIVE_BUILD_REPORT", recursive_report)
    monkeypatch.setattr(v89, "_ORIGINAL_BOUNDARY_PDF_PAGE", recursive_pdf)
    monkeypatch.setattr(providers, "_build_report", recursive_report)
    monkeypatch.setattr(producer, "_boundary_pdf_page", recursive_pdf)

    installation = v90.install_report_worker_runtime_v90()

    assert installation["native_report_base_stable"] is True
    assert installation["ci_pdf_base_stable"] is True
    assert installation["first_install_order_independent"] is True
    assert installation["detached_report_alias_recursion_blocked"] is True
    assert v88._ORIGINAL_NATIVE_BUILD_REPORT is v90._native_report_base_v90
    assert v89._ORIGINAL_BOUNDARY_PDF_PAGE is v90._boundary_pdf_page_base_v90
    assert providers._build_report is v88._native_build_report_v88
    assert producer._boundary_pdf_page is v89._boundary_pdf_page_v89


def test_v90_report_base_does_not_delegate_through_mutable_provider_alias(monkeypatch) -> None:
    calls: list[tuple[dict[str, object], bool]] = []

    def exploding_alias(context: dict[str, object], final: bool) -> dict[str, object]:
        raise AssertionError("mutable providers._build_report must not be called")

    def fake_identity(context: dict[str, object]) -> dict[str, str]:
        return {
            "run_id": "comprun_v90_fixture",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "a" * 40,
            "evidence_ledger_id": "ledger_v90_fixture",
            "customer_id": "customer_v90",
            "project_id": "project_v90",
        }

    def fake_package(*, identity: dict[str, str], stage_results: dict[str, object]) -> dict[str, object]:
        assert identity["run_id"] == "comprun_v90_fixture"
        assert stage_results == {"evidence_reconciliation_and_scoring": {"status": "complete"}}
        return {
            "status": "complete",
            "report_id": "report_v90",
            "canonical_truth_sha256": "b" * 64,
            "assessment": {"status": "complete"},
            "report_package": {"pdf_page_count": 7},
        }

    def fake_result(context: dict[str, object], status: str = "complete", **payload: object) -> dict[str, object]:
        calls.append((context, payload.get("evidence", {}).get("final_package") is True))
        return {"status": status, **payload}

    monkeypatch.setattr(providers, "_build_report", exploding_alias)
    monkeypatch.setattr(providers, "_identity", fake_identity)
    monkeypatch.setattr(providers, "_result", fake_result)
    monkeypatch.setattr(v90, "build_comprehensive_report_package", fake_package)

    context: dict[str, object] = {
        "run_id": "comprun_v90_fixture",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_v90_fixture",
        "customer_id": "customer_v90",
        "project_id": "project_v90",
        "prior_stage_results": {
            "evidence_reconciliation_and_scoring": {"status": "complete"},
        },
    }

    result = v90._native_report_base_v90(context, False)

    assert result["status"] == "complete"
    assert result["report_package"] == {"pdf_page_count": 7}
    assert result["evidence"]["final_package"] is False
    assert calls == [(context, False)]


def test_detached_report_stage_rebind_occurs_before_provider_execution() -> None:
    source = BACKGROUND.read_text(encoding="utf-8")

    guard_index = source.index("install_report_worker_runtime_v90()")
    execution_index = source.index("raw = execute_stage_with_timeout(")

    assert guard_index < execution_index
    assert "if report_stage(stage_id):" in source
    assert "report_runtime_v90_rebound" in source
    assert "detached_stage_execution_failed:{exception_type}:stage={stage_id}" in source
