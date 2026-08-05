from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_client_surface_structure_cleanup_v1 import (
    client_surface_values,
    humanize_client_surface_value,
    install_client_surface_structure_cleanup_v1,
    premium_renderer_clean_lines,
)


def test_nested_roadmap_objects_render_as_readable_lines_without_mutation() -> None:
    roadmap = [
        {
            "window": "0-30 days",
            "objective": "Remove the highest-risk constraints.",
            "work_packages": [
                {
                    "work_package_id": "WP-001",
                    "title": "Decompose page.tsx",
                    "owner_role": "Product Engineer",
                    "effort": "M",
                }
            ],
        }
    ]
    before = deepcopy(roadmap)

    lines = client_surface_values(roadmap, limit=8)

    assert len(lines) == 1
    assert "Window: 0-30 days" in lines[0]
    assert "Work Package Id: WP-001" in lines[0]
    assert "Owner Role: Product Engineer" in lines[0]
    assert "{" not in lines[0]
    assert "}" not in lines[0]
    assert roadmap == before


def test_premium_renderer_clean_lines_humanizes_existing_stage_evidence() -> None:
    evidence = [
        {
            "window": "0-30 days",
            "objective": "Remove the highest-risk delivery constraints.",
            "work_packages": [
                {
                    "work_package_id": "WP-001",
                    "title": "Decompose page.tsx",
                    "owner_role": "Product Engineer",
                    "effort": "M",
                }
            ],
        }
    ]

    lines = premium_renderer_clean_lines(evidence)

    assert len(lines) == 1
    assert lines[0].startswith("Window: 0-30 days; Objective:")
    assert "Work Package Id: WP-001" in lines[0]
    assert "{" not in lines[0]
    assert "'window'" not in lines[0]


def test_workflow_outcome_mapping_uses_client_readable_labels() -> None:
    rendered = humanize_client_surface_value(
        {
            "success": 81,
            "failure": 10,
            "cancelled": 2,
            "skipped": 3,
            "timed_out": 1,
            "unknown": 9,
            "in_progress": 4,
        }
    )

    assert rendered == (
        "Successful: 81; Failed: 10; Cancelled: 2; Skipped: 3; "
        "Timed out: 1; Unknown: 9; In progress: 4"
    )
    assert "{" not in rendered
    assert "'success'" not in rendered


def test_shared_renderer_helpers_are_patched() -> None:
    from nico import comprehensive_client_review_companion_v2 as companion
    from nico import v2_premium_report_renderer as premium

    status = install_client_surface_structure_cleanup_v1()
    review_lines = companion._values(
        [{"window": "31-90 days", "owner_role": "Platform Engineer"}],
        limit=4,
    )
    premium_lines = premium._clean_lines(
        [{"window": "91-180 days", "owner_role": "Delivery Lead"}]
    )

    assert status["status"] in {"installed", "already_installed"}
    assert review_lines == ["Window: 31-90 days; Owner Role: Platform Engineer"]
    assert premium_lines == ["Window: 91-180 days; Owner Role: Delivery Lead"]
    assert status["premium_renderer_clean_lines_bound"] is True
    assert status["canonical_json_unchanged"] is True
