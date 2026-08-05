from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_blank_deployment_metric_repair_v1 import (
    install_blank_deployment_metric_repair_v1,
    normalize_blank_non_success_deployment_metric,
    project_blank_deployment_metrics,
    sanitize_blank_deployment_metric_stage,
)
from nico.comprehensive_client_surface_structure_cleanup_v1 import (
    project_client_stage_summaries,
)
from nico.comprehensive_human_review_package_cleanup_v1 import (
    assert_human_review_package_cleanup,
)

RUN_ID = "comprun_ae789858c7a94507ad2c886d8bbde9bf"
REPLACEMENT = "Non-success deployment classification: Not available."


def _pdf(pages: list[list[str]]) -> bytes:
    buffer = io.BytesIO()
    document = canvas.Canvas(buffer, invariant=1)
    for lines in pages:
        y = 760
        for line in lines:
            document.drawString(40, y, line)
            y -= 18
        document.showPage()
    document.save()
    return buffer.getvalue()


def test_blank_metric_is_projected_as_explicitly_unavailable() -> None:
    for value in (
        "Non-success deployments:",
        "Non-success deployments: .",
        "- Non-success deployments: ---",
        "Non-success deployment classification: —",
    ):
        assert REPLACEMENT in normalize_blank_non_success_deployment_metric(value)


def test_known_non_success_deployment_values_are_preserved() -> None:
    for value in (
        "Non-success deployments: 3.",
        "Non-success deployment classification: cancelled=2; failed=1.",
        "Non-success deployments: Review required.",
    ):
        assert normalize_blank_non_success_deployment_metric(value) == value


def test_stage_and_package_projection_repair_only_client_facing_fields() -> None:
    raw_stage = {
        "stage_id": "historical_trends_and_change_failure",
        "summary": "Historical evidence retained.",
        "evidence": ["Non-success deployments: .", "Successful deployments: 7."],
        "source_payload": {"non_success_deployments": "."},
    }

    stage = sanitize_blank_deployment_metric_stage(raw_stage)
    assert stage["evidence"] == [REPLACEMENT, "Successful deployments: 7."]
    assert stage["source_payload"] == {"non_success_deployments": "."}

    projected = project_blank_deployment_metrics(
        {
            "json": {
                "identity": {"run_id": RUN_ID},
                "stage_summaries": [raw_stage],
                "assessment": {
                    "stage_summaries": [raw_stage],
                    "sections": [
                        {
                            "id": "ci_cd",
                            "evidence": ["Non-success deployments:"],
                        }
                    ],
                },
                "raw_scanner_payload": {"non_success_deployments": "."},
            }
        }
    )
    canonical = projected["json"]
    assert canonical["stage_summaries"][0]["evidence"][0] == REPLACEMENT
    assert canonical["assessment"]["sections"][0]["evidence"][0] == REPLACEMENT
    assert canonical["raw_scanner_payload"] == {"non_success_deployments": "."}
    assert (
        canonical["v2_pipeline_contract"]
        ["blank_non_success_deployment_metric_renders_not_available"]
        is True
    )


def test_failed_run_shape_renders_without_weakening_blank_metric_gate() -> None:
    install_blank_deployment_metric_repair_v1()
    package = {
        "json": {
            "identity": {
                "run_id": RUN_ID,
                "customer_id": "Not supplied",
                "project_id": "Not supplied",
            },
            "stage_summaries": [
                {
                    "stage_id": "historical_trends_and_change_failure",
                    "title": "Historical Trends and Change Failure",
                    "status": "review_required",
                    "summary": "Historical deployment evidence requires review.",
                    "evidence": ["Non-success deployments: ."],
                    "findings": [],
                    "unavailable": [],
                }
            ],
            "assessment": {},
        }
    }

    projected = project_client_stage_summaries(package)
    canonical = projected["json"]
    assert canonical["stage_summaries"][0]["evidence"] == [REPLACEMENT]

    safe_pdf = _pdf(
        [
            ["Table of Contents", "Historical Trends and Change Failure 2"],
            [
                "Historical Trends and Change Failure",
                REPLACEMENT,
                "Human review required.",
            ],
        ]
    )
    assert_human_review_package_cleanup(
        canonical,
        f"AUTOMATED DRAFT\nRun ID: {RUN_ID}\n{REPLACEMENT}",
        f"<p>CLIENT DELIVERY BLOCKED</p><p>{REPLACEMENT}</p>",
        safe_pdf,
    )

    blank_pdf = _pdf(
        [
            ["Table of Contents", "Historical Trends and Change Failure 2"],
            ["Historical Trends and Change Failure", "Non-success deployments: ."],
        ]
    )
    with pytest.raises(ValueError, match="blank non-success deployment metric"):
        assert_human_review_package_cleanup(
            canonical,
            "AUTOMATED DRAFT",
            "<p>CLIENT DELIVERY BLOCKED</p>",
            blank_pdf,
        )
