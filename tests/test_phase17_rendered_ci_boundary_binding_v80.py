from __future__ import annotations

from typing import Any

import pytest

from nico import client_report_completion_v2 as completion
from nico import phase17_canonical_artifact_rebuild_v1 as phase17


def _identity(value: Any) -> Any:
    return value


def test_phase17_directly_repairs_boundary_before_sanitize_and_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real Phase 17 choke point must not depend on optional installers."""

    calls: list[str] = []

    monkeypatch.setattr(phase17, "_phase2_review_truth_node", _identity)
    monkeypatch.setattr(phase17, "_reconcile", _identity)
    monkeypatch.setattr(phase17, "repair_canonical_truth", _identity)
    monkeypatch.setattr(
        phase17,
        "install_client_surface_structure_cleanup_v1",
        lambda: {},
    )
    monkeypatch.setattr(
        phase17,
        "install_human_review_worksheet_title_contract_v1",
        lambda: {},
    )
    monkeypatch.setattr(phase17, "project_client_stage_summaries", _identity)
    monkeypatch.setattr(phase17, "rebuild_single_pass_premium_artifacts", _identity)
    monkeypatch.setattr(phase17, "_is_spanish", lambda _canonical: False)
    monkeypatch.setattr(phase17, "repair_rendered_report", _identity)
    monkeypatch.setattr(phase17, "repair_localized_rendered_report", _identity)
    monkeypatch.setattr(completion, "prepare_client_report_package", _identity)

    def repair_boundary(package: Any) -> Any:
        calls.append("repair_boundary")
        return package

    def sanitize(package: Any) -> Any:
        calls.append("sanitize")
        return package

    def finalize(package: Any) -> dict[str, Any]:
        calls.append("finalize")
        return {"status": "review_required", "package": package}

    monkeypatch.setattr(
        phase17.ci_boundary_producer,
        "repair_rendered_ci_boundary",
        repair_boundary,
    )
    monkeypatch.setattr(phase17, "_sanitize_published_artifacts", sanitize)
    monkeypatch.setattr(completion, "finalize_client_report_package", finalize)

    result = phase17.rebuild_client_artifacts({"json": {}})

    assert calls == ["repair_boundary", "sanitize", "finalize"]
    assert result["status"] == "review_required"


def test_phase17_uses_module_binding_not_a_stale_function_alias() -> None:
    assert hasattr(phase17, "ci_boundary_producer")
    assert phase17.ci_boundary_producer.VERSION.startswith(
        "nico.comprehensive-rendered-ci-boundary-producer."
    )
