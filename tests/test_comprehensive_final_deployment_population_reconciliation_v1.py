from __future__ import annotations

import io
from pathlib import Path

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_final_deployment_population_reconciliation_v1 import (
    assert_deployment_population_reconciled,
    assert_final_deployment_population_reconciliation,
    reconcile_deployment_population,
)


RUN_ID = "comprun_36959bd62c444298a805fe4b2edc3131"
COMMIT = "9d817fdd827086a089a6153a7b65cdbd4344b1b4"
ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "comprehensive_human_review_package_cleanup_compat_v1.py"


def _stage(non_success: int) -> dict:
    return {
        "stage_id": "ci_cd_operational_readiness",
        "title": "CI/CD Operational Readiness and Historical Health",
        "evidence": [
            "Deployments observed: 10.",
            "Successful deployments: 7.",
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
