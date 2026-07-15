from __future__ import annotations

from nico.complexity_density_confidence_patch import (
    confidence_adjusted_file_complexity,
    install_complexity_density_confidence_patch,
)
from nico.complexity_score_integrity_patch import _calibrated_score_profile


def test_one_line_adapter_does_not_become_a_100_percent_density_hotspot() -> None:
    max_function, adjusted_density = confidence_adjusted_file_complexity(
        {
            "path": "nico/adapter.py",
            "loc": 1,
            "function_count": 0,
            "cyclomatic_complexity": 1,
            "max_function_complexity": 0,
        }
    )

    assert max_function == 1
    assert adjusted_density == 2.0


def test_density_reaches_full_weight_at_fifty_source_lines() -> None:
    max_function, adjusted_density = confidence_adjusted_file_complexity(
        {
            "path": "nico/service.py",
            "loc": 50,
            "function_count": 5,
            "cyclomatic_complexity": 10,
            "max_function_complexity": 6,
        }
    )

    assert max_function == 6
    assert adjusted_density == 20.0


def test_tiny_high_churn_adapter_does_not_create_complexity_churn_overlap() -> None:
    files = [
        {
            "path": f"nico/module_{index}.py",
            "loc": 200,
            "function_count": 20,
            "cyclomatic_complexity": 12,
            "max_function_complexity": 3,
            "churn": 20,
            "primary_owner": "owner@example.com",
            "owner_concentration": 0.6,
        }
        for index in range(100)
    ]
    files.append(
        {
            "path": "nico/adapter.py",
            "loc": 1,
            "function_count": 0,
            "cyclomatic_complexity": 1,
            "max_function_complexity": 0,
            "churn": 1000,
            "primary_owner": "owner@example.com",
            "owner_concentration": 1.0,
        }
    )
    churn = {item["path"]: item["churn"] for item in files}
    concentration = {item["path"]: item["owner_concentration"] for item in files}

    score, risk, findings = _calibrated_score_profile(files, churn, concentration, 20)

    assert score >= 90
    assert risk == "low"
    assert not any("Complexity and high churn overlap" in item for item in findings)


def test_installation_is_idempotent() -> None:
    first = install_complexity_density_confidence_patch()
    second = install_complexity_density_confidence_patch()

    assert first["minimum_density_sample_loc"] == 50
    assert second["minimum_density_sample_loc"] == 50
