from __future__ import annotations

import io
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_final_deployment_population_reconciliation_v1 import (
    assert_deployment_population_reconciled,
    assert_final_deployment_population_reconciliation,
    project_deployment_population_package,
    reconcile_deployment_population,
)


RUN_ID = "comprun_c1a9bc931086455a9e16054a1820264a"
COMMIT = "7235a861b1ab4dea5280917d80c76a00fd9f16d5"
ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "comprehensive_human_review_package_cleanup_compat_v1.py"


def _stage(non_success: int, *, observed: int = 10, successful: int = 7) -> dict:
    return {
        "stage_id": "ci_cd_operational_readiness",
        "title": "CI/CD Operational Readiness and Historical Health",
        "evidence": [
            f"Deployments observed: {observed}.",
            f"Successful deployments: {successful}.",
            f"Non-success deployments: {non_success}.",
        ],
    }


def _pdf(*lines: str) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    y = 760
    for line in lines:
        document.drawString(40, y, line)
        y -= 18
    document.showPage()
    document.save()
    return buffer.getvalue()


def test_exact_10_7_1_report_population_becomes_bounded_remainder() -> None:
    source = _stage(1)

    repaired = reconcile_deployment_population(source)

    assert "Non-success deployments: 1." not in repaired["evidence"]
    assert (
        "Non-success or unresolved deployment observations: 3."
        in repaired["evidence"]
    )
    assert "Outcome classification breakdown: Not available." in repaired["evidence"]
    assert source["evidence"][-1] == "Non-success deployments: 1."


def test_prior_10_7_2_mismatch_is_reconciled_the_same_way() -> None:
    repaired = reconcile_deployment_population(_stage(2))

    assert "Non-success deployments: 2." not in repaired["evidence"]
    assert (
        "Non-success or unresolved deployment observations: 3."
        in repaired["evidence"]
    )
    assert "Outcome classification breakdown: Not available." in repaired["evidence"]


def test_complete_10_7_3_numeric_classification_is_preserved() -> None:
    source = _stage(3)

    repaired = reconcile_deployment_population(source)

    assert repaired["evidence"] == source["evidence"]
    assert "Outcome classification breakdown: Not available." not in repaired["evidence"]


def test_final_package_projection_repairs_every_rendered_stage_copy() -> None:
    source = _stage(1)
    package = {
        "json": {
            "identity": {"run_id": RUN_ID, "commit_sha": COMMIT},
            "stage_summaries": [source],
            "assessment": {
                "stage_summaries": [source],
                "sections": [source],
            },
        }
    }

    projected = project_deployment_population_package(package)
    canonical = projected["json"]
    copies = [
        canonical["stage_summaries"][0],
        canonical["assessment"]["stage_summaries"][0],
        canonical["assessment"]["sections"][0],
    ]

    assert all(
        "Non-success or unresolved deployment observations: 3."
        in item["evidence"]
        for item in copies
    )
    assert all(
        "Outcome classification breakdown: Not available." in item["evidence"]
        for item in copies
    )
    assert package["json"]["stage_summaries"][0]["evidence"][-1] == (
        "Non-success deployments: 1."
    )


def test_validator_rejects_bullet_prefixed_incomplete_population() -> None:
    surface = "\n".join(
        (
            "- Deployments observed: 10.",
            "- Successful deployments: 7.",
            "- Non-success deployments: 1.",
        )
    )

    with pytest.raises(ValueError, match="does not reconcile"):
        assert_deployment_population_reconciled(surface)


def test_repeated_populations_are_validated_independently() -> None:
    surface = "\n".join(
        (
            "Summary deployment evidence",
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployments: 3.",
            "Detailed deployment evidence",
            "Deployments observed: 12.",
            "Successful deployments: 10.",
            "Non-success deployments: 2.",
        )
    )

    assert_deployment_population_reconciled(surface)


def test_one_bad_repeated_population_still_fails_closed() -> None:
    surface = "\n".join(
        (
            "Deployments observed: 10.",
            "Successful deployments: 7.",
            "Non-success deployments: 3.",
            "Deployments observed: 12.",
            "Successful deployments: 10.",
            "Non-success deployments: 1.",
        )
    )

    with pytest.raises(ValueError, match="does not reconcile"):
        assert_deployment_population_reconciled(surface)


def test_cross_format_validator_accepts_the_bounded_remainder() -> None:
    lines = (
        "Deployments observed: 10.",
        "Successful deployments: 7.",
        "Non-success or unresolved deployment observations: 3.",
        "Outcome classification breakdown: Not available.",
    )
    markdown = "\n".join(f"- {line}" for line in lines)
    rendered_html = "<ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>"

    assert_final_deployment_population_reconciliation(
        {"identity": {"run_id": RUN_ID, "commit_sha": COMMIT}},
        markdown,
        rendered_html,
        _pdf(*lines),
    )


def test_final_reconciliation_installs_after_the_previous_final_two_contract() -> None:
    source = COMPAT.read_text(encoding="utf-8")

    final_two = source.rindex("final_two_truth = install_final_two_report_truth_v1()")
    final_population = source.rindex(
        "install_final_deployment_population_reconciliation_v1()"
    )
    assert final_two < final_population
    assert (
        'VERSION = "nico.comprehensive-human-review-package-cleanup-compat.v1.9"'
        in source
    )
