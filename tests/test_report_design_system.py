from dataclasses import replace

from nico.report_design_system import (
    NICO_REPORT_DESIGN_SYSTEM,
    validate_report_design_system,
)


def test_default_report_design_system_is_valid() -> None:
    assert validate_report_design_system() == []


def test_required_components_cover_core_client_report_structure() -> None:
    components = set(NICO_REPORT_DESIGN_SYSTEM.required_components)
    assert {
        "cover",
        "executive_dashboard",
        "scorecard",
        "evidence_summary",
        "technical_dossier",
        "repair_roadmap",
        "integrity_boundary",
    } <= components


def test_invalid_typography_fails_closed() -> None:
    system = replace(
        NICO_REPORT_DESIGN_SYSTEM,
        typography=replace(NICO_REPORT_DESIGN_SYSTEM.typography, body_pt=6.0),
    )
    assert "body_size_out_of_range" in validate_report_design_system(system)


def test_missing_component_is_reported() -> None:
    system = replace(
        NICO_REPORT_DESIGN_SYSTEM,
        required_components=tuple(
            item for item in NICO_REPORT_DESIGN_SYSTEM.required_components if item != "integrity_boundary"
        ),
    )
    assert "missing_component_integrity_boundary" in validate_report_design_system(system)


def test_table_headers_and_orphan_control_are_mandatory() -> None:
    system = replace(
        NICO_REPORT_DESIGN_SYSTEM,
        layout=replace(
            NICO_REPORT_DESIGN_SYSTEM.layout,
            table_header_repeat=False,
            avoid_orphans=False,
        ),
    )
    issues = validate_report_design_system(system)
    assert "table_headers_must_repeat" in issues
    assert "orphan_control_required" in issues
