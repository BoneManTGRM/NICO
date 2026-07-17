from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class ReportPalette:
    ink: str
    muted: str
    surface: str
    surface_alt: str
    border: str
    accent: str
    success: str
    warning: str
    danger: str


@dataclass(frozen=True)
class ReportTypography:
    title_pt: float
    section_pt: float
    subsection_pt: float
    body_pt: float
    small_pt: float
    body_leading: float


@dataclass(frozen=True)
class ReportLayout:
    page_margin_in: float
    section_gap_in: float
    card_padding_in: float
    table_header_repeat: bool
    avoid_orphans: bool
    minimum_body_lines_per_page: int


@dataclass(frozen=True)
class ReportDesignSystem:
    version: str
    palette: ReportPalette
    typography: ReportTypography
    layout: ReportLayout
    required_components: tuple[str, ...]


NICO_REPORT_DESIGN_SYSTEM: Final = ReportDesignSystem(
    version="nico-report-design-v1",
    palette=ReportPalette(
        ink="#0F172A",
        muted="#64748B",
        surface="#FFFFFF",
        surface_alt="#F8FAFC",
        border="#CBD5E1",
        accent="#0EA5E9",
        success="#059669",
        warning="#D97706",
        danger="#DC2626",
    ),
    typography=ReportTypography(
        title_pt=24.0,
        section_pt=17.0,
        subsection_pt=12.0,
        body_pt=9.25,
        small_pt=7.75,
        body_leading=12.0,
    ),
    layout=ReportLayout(
        page_margin_in=0.55,
        section_gap_in=0.18,
        card_padding_in=0.12,
        table_header_repeat=True,
        avoid_orphans=True,
        minimum_body_lines_per_page=8,
    ),
    required_components=(
        "cover",
        "executive_dashboard",
        "scorecard",
        "evidence_summary",
        "technical_dossier",
        "repair_roadmap",
        "integrity_boundary",
    ),
)


def validate_report_design_system(system: ReportDesignSystem = NICO_REPORT_DESIGN_SYSTEM) -> list[str]:
    issues: list[str] = []
    if not system.version.strip():
        issues.append("missing_version")
    for name, value in vars(system.palette).items():
        if not isinstance(value, str) or len(value) != 7 or not value.startswith("#"):
            issues.append(f"invalid_palette_{name}")
    if not (20 <= system.typography.title_pt <= 32):
        issues.append("title_size_out_of_range")
    if not (8 <= system.typography.body_pt <= 11):
        issues.append("body_size_out_of_range")
    if system.typography.body_leading <= system.typography.body_pt:
        issues.append("body_leading_too_tight")
    if not (0.4 <= system.layout.page_margin_in <= 0.8):
        issues.append("page_margin_out_of_range")
    if not system.layout.table_header_repeat:
        issues.append("table_headers_must_repeat")
    if not system.layout.avoid_orphans:
        issues.append("orphan_control_required")
    required = set(system.required_components)
    expected = {
        "cover",
        "executive_dashboard",
        "scorecard",
        "evidence_summary",
        "technical_dossier",
        "repair_roadmap",
        "integrity_boundary",
    }
    missing = expected - required
    issues.extend(f"missing_component_{name}" for name in sorted(missing))
    return issues


__all__ = [
    "NICO_REPORT_DESIGN_SYSTEM",
    "ReportDesignSystem",
    "ReportLayout",
    "ReportPalette",
    "ReportTypography",
    "validate_report_design_system",
]
