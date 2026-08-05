from __future__ import annotations

from copy import deepcopy

from nico.comprehensive_client_surface_structure_cleanup_v1 import (
    client_surface_values,
    humanize_client_surface_value,
    install_client_surface_structure_cleanup_v1,
    premium_renderer_clean_lines,
    project_client_stage_summaries,
    sanitize_client_rendered_stage,
)


def _roadmap() -> list[dict]:
    return [
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


def test_nested_roadmap_objects_render_as_readable_lines_without_mutation() -> None:
    roadmap = _roadmap()
    before = deepcopy(roadmap)

    lines = client_surface_values(roadmap, limit=8)

    assert len(lines) == 1
    assert "Window: 0-30 days" in lines[0]
    assert "Work Package Id: WP-001" in lines[0]
    assert "Owner Role: Product Engineer" in lines[0]
    assert "{" not in lines[0]
    assert "}" not in lines[0]
    assert roadmap == before


def test_stage_sanitizer_humanizes_every_client_facing_stage_field() -> None:
    stage = {
        "stage_id": "six_month_roadmap",
        "title": "Six-Month Roadmap",
        "evidence": _roadmap(),
        "findings": [{"risk": "Delivery regression", "priority": "P1"}],
        "unavailable": [{"field": "Owner approval", "reason": "Human input required"}],
        "limitations": [{"scope": "Repository evidence only"}],
    }
    before = deepcopy(stage)

    rendered = sanitize_client_rendered_stage(stage)

    for field in ("evidence", "findings", "unavailable", "limitations"):
        assert rendered[field]
        assert all("{" not in line and "}" not in line for line in rendered[field])
    assert "Window: 0-30 days" in rendered["evidence"][0]
    assert "Risk: Delivery regression" in rendered["findings"][0]
    assert "Field: Owner approval" in rendered["unavailable"][0]
    assert "Scope: Repository evidence only" in rendered["limitations"][0]
    assert stage == before


def test_stage_projection_humanizes_client_fields_and_retains_structured_sources() -> None:
    roadmap = _roadmap()
    stage = {
        "stage_id": "six_month_roadmap",
        "title": "Six-Month Roadmap",
        "evidence": deepcopy(roadmap),
        "findings": [],
        "unavailable": [],
    }
    package = {
        "json": {
            "roadmap": deepcopy(roadmap),
            "stage_summaries": [deepcopy(stage)],
            "assessment": {"stage_summaries": [deepcopy(stage)]},
        }
    }
    before = deepcopy(package)

    projected = project_client_stage_summaries(package)
    canonical = projected["json"]
    evidence = canonical["stage_summaries"][0]["evidence"]

    assert len(evidence) == 1
    assert "Window: 0-30 days" in evidence[0]
    assert "Work Package Id: WP-001" in evidence[0]
    assert "{" not in evidence[0]
    assert "'window'" not in evidence[0]
    assert canonical["roadmap"] == roadmap
    assert canonical["assessment"]["stage_summaries"] == canonical["stage_summaries"]
    assert package == before


def test_premium_renderer_clean_lines_humanizes_existing_stage_evidence() -> None:
    evidence = _roadmap()

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


def test_shared_renderer_helpers_and_final_truth_cleaner_are_patched() -> None:
    from nico import comprehensive_client_review_companion_v2 as companion
    from nico import comprehensive_client_truth_final_v1 as final_truth
    from nico import comprehensive_human_review_package_cleanup_v1 as cleanup
    from nico import v2_premium_evidence_appendix as appendix
    from nico import v2_premium_report_renderer as premium

    status = install_client_surface_structure_cleanup_v1()
    review_lines = companion._values(
        [{"window": "31-90 days", "owner_role": "Platform Engineer"}],
        limit=4,
    )
    premium_lines = premium._clean_lines(
        [{"window": "91-180 days", "owner_role": "Delivery Lead"}]
    )
    sanitized_stage = cleanup.sanitize_rendered_stage(
        {"stage_id": "six_month_roadmap", "evidence": _roadmap()}
    )
    final_truth_lines = final_truth._clean_evidence(_roadmap())

    assert status["status"] in {"installed", "already_installed"}
    assert review_lines == ["Window: 31-90 days; Owner Role: Platform Engineer"]
    assert premium_lines == ["Window: 91-180 days; Owner Role: Delivery Lead"]
    assert "Window: 0-30 days" in sanitized_stage["evidence"][0]
    assert "{" not in sanitized_stage["evidence"][0]
    assert "Window: 0-30 days" in final_truth_lines[0]
    assert "Work Package Id: WP-001" in final_truth_lines[0]
    assert "{" not in final_truth_lines[0]
    assert status["final_truth_evidence_cleanup_bound"] is True
    assert status["structured_stage_sanitizer_bound"] is True
    assert status["premium_renderer_clean_lines_bound"] is True
    assert status["premium_renderer_entrypoint_bound"] is True
    assert (
        appendix.rebuild_premium_client_artifacts
        is premium.rebuild_premium_client_artifacts
    )
    assert status["canonical_structured_sources_retained"] is True
