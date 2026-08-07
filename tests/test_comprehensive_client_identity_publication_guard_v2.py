from __future__ import annotations

import io

import pytest
from reportlab.pdfgen import canvas

from nico.comprehensive_client_identity_publication_guard_v2 import (
    assert_client_identity_publication_guard,
    sanitize_client_report_package,
    sanitize_public_identity_fields,
)


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


def test_recursive_identity_projection_sanitizes_public_ids_but_preserves_source_evidence() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "project_id": "default_project",
        },
        "assessment": {
            "identity": {
                "project_id": "default_project",
                "workspace_id": "default_workspace",
            },
            "project_id": "default_project",
            "stage_summaries": [
                {
                    "stage_id": "static_analysis",
                    "evidence": [
                        "Source compares project_id to default_project for internal routing.",
                        {
                            "source_symbol": "normalize_subject",
                            "project_id": "default_project",
                        },
                    ],
                }
            ],
        },
    }

    projected = sanitize_public_identity_fields(canonical)

    assert projected["identity"]["project_id"] == "Not supplied"
    assert projected["assessment"]["identity"]["project_id"] == "Not supplied"
    assert projected["assessment"]["identity"]["workspace_id"] == "Not supplied"
    assert projected["assessment"]["project_id"] == "Not supplied"
    evidence = projected["assessment"]["stage_summaries"][0]["evidence"]
    assert evidence[0] == "Source compares project_id to default_project for internal routing."
    assert evidence[1]["project_id"] == "default_project"


def test_real_identity_values_are_preserved() -> None:
    projected = sanitize_public_identity_fields(
        {
            "identity": {
                "project_id": "project-mercury",
                "project_name": "Mercury",
                "workspace_id": "workspace-42",
                "target_id": "release-main",
            }
        }
    )

    assert projected["identity"]["project_id"] == "project-mercury"
    assert projected["identity"]["project_name"] == "Mercury"
    assert projected["identity"]["workspace_id"] == "workspace-42"
    assert projected["identity"]["target_id"] == "release-main"


def test_report_package_projection_marks_contract_without_changing_scores() -> None:
    package = {
        "json": {
            "identity": {"project_id": "default_project"},
            "assessment": {
                "technical_score": 93,
                "canonical_evidence_adjusted_score": 89,
            },
        }
    }

    projected = sanitize_client_report_package(package)

    assert projected["json"]["identity"]["project_id"] == "Not supplied"
    assert projected["json"]["assessment"]["technical_score"] == 93
    assert projected["json"]["assessment"]["canonical_evidence_adjusted_score"] == 89
    contract = projected["json"]["v2_pipeline_contract"]
    assert contract["client_identity_fields_recursively_sanitized"] is True
    assert contract["literal_source_evidence_preserved"] is True
    assert contract["human_review_required"] is True
    assert contract["client_delivery_allowed"] is False


def test_publication_guard_allows_literal_default_project_in_source_evidence() -> None:
    canonical = {
        "identity": {
            "repository": "BoneManTGRM/NICO",
            "project_id": "Not supplied",
        },
        "v2_pipeline_contract": {
            "client_identity_placeholders_sanitized": True,
        },
        "stage_summaries": [
            {
                "stage_id": "static_analysis",
                "evidence": [
                    "Source evidence: project_id == 'default_project' is an internal sentinel."
                ],
            }
        ],
    }
    markdown = (
        "# NICO Comprehensive\n\n"
        "Project: Not supplied\n\n"
        "Source evidence: project_id == `default_project` is retained literally.\n"
    )
    rendered_html = (
        "<h1>NICO Comprehensive</h1>"
        "<p>Project: Not supplied</p>"
        "<p>Source evidence: project_id == <code>default_project</code>.</p>"
    )
    pdf = _pdf(
        "NICO Comprehensive",
        "Project: Not supplied",
        "Source evidence: project_id == default_project is retained literally.",
    )

    assert_client_identity_publication_guard(
        canonical,
        markdown,
        rendered_html,
        pdf,
    )


def test_publication_guard_rejects_actual_rendered_identity_placeholder() -> None:
    canonical = {
        "identity": {"project_id": "Not supplied"},
        "v2_pipeline_contract": {
            "client_identity_placeholders_sanitized": True,
        },
        "stage_summaries": [],
    }

    with pytest.raises(ValueError, match="exposed placeholder identity"):
        assert_client_identity_publication_guard(
            canonical,
            "Project: default_project",
            "<p>Project: default_project</p>",
            _pdf("Project: default_project"),
        )


def test_production_contract_fails_closed_if_nested_identity_placeholder_reappears() -> None:
    canonical = {
        "identity": {"project_id": "Not supplied"},
        "assessment": {
            "identity": {"project_id": "default_project"},
        },
        "v2_pipeline_contract": {
            "client_identity_placeholders_sanitized": True,
        },
        "stage_summaries": [],
    }

    with pytest.raises(ValueError, match="canonical client identity retained placeholder field"):
        assert_client_identity_publication_guard(
            canonical,
            "Project: Not supplied",
            "<p>Project: Not supplied</p>",
            _pdf("Project: Not supplied"),
        )
