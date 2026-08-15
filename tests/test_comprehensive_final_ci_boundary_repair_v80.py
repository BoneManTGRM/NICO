from __future__ import annotations

import inspect
from typing import Any, Mapping

import pytest

from nico import comprehensive_client_truth_final_v1 as final_truth
from nico import comprehensive_final_ci_boundary_repair_v80 as repair_v80
from nico import comprehensive_review_candidate_compat_v76 as compat_v76


def _complete_english_truth(_result: Mapping[str, Any]) -> dict[str, Any]:
    surface = {
        "english": {"complete": True},
        "spanish": {"complete": False},
    }
    return {
        "language": "en",
        "complete": True,
        "conflict": False,
        "per_surface": {
            "markdown": dict(surface),
            "html": dict(surface),
            "pdf": dict(surface),
        },
    }


def test_v80_repairs_mutable_package_before_existing_final_validator(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def existing_validator(result: Mapping[str, Any]) -> None:
        calls.append("validate")
        assert result.get("repaired") is True

    def repair(result: Mapping[str, Any]) -> dict[str, Any]:
        calls.append("repair")
        output = dict(result)
        output["repaired"] = True
        return output

    monkeypatch.setattr(final_truth, "_validate_surfaces", existing_validator)
    monkeypatch.setattr(
        final_truth,
        repair_v80._INSTALL_MARKER,
        False,
        raising=False,
    )
    monkeypatch.setattr(
        repair_v80.producer_v79,
        "repair_rendered_ci_boundary",
        repair,
    )
    monkeypatch.setattr(
        repair_v80.truth_v78,
        "rendered_ci_boundary_truth",
        _complete_english_truth,
    )

    installation = repair_v80.install_comprehensive_final_ci_boundary_repair_v80()
    package: dict[str, Any] = {"json": {}}
    final_truth._validate_surfaces(package)

    assert installation["validator_bound"] is True
    assert calls == ["repair", "validate"]
    assert package["repaired"] is True
    assert package["human_review_required"] is True
    assert package["client_delivery_allowed"] is False
    assert package["final_ci_boundary_repair"]["pdf_complete"] is True


def test_v76_installs_v80_after_renderer_and_v78_truth() -> None:
    source = inspect.getsource(
        compat_v76.install_comprehensive_review_candidate_compat_v76
    )

    producer = source.index(
        "install_comprehensive_rendered_ci_boundary_producer_v79"
    )
    final_repair = source.index(
        "install_comprehensive_final_ci_boundary_repair_v80"
    )
    returned_contract = source.index("final_ci_boundary_repair_installer")

    assert producer < final_repair < returned_contract
