from __future__ import annotations

import io

import pytest
from pypdf import PdfReader

from nico import comprehensive_rendered_ci_boundary_producer_v79 as producer


@pytest.mark.parametrize(
    ("spanish", "marker"),
    (
        (False, "A. CI/CD configuration maturity:"),
        (True, "A. Madurez de configuración de CI/CD:"),
    ),
)
def test_ci_boundary_pdf_lists_are_extractable_without_control_glyphs(
    spanish: bool,
    marker: str,
) -> None:
    canonical: dict[str, object] = {
        "report_language": "es-MX" if spanish else "en",
        "identity": {
            "repository": "acme/api",
            "commit_sha": "abc123",
            "run_id": "comprun_control_glyph_fixture",
            "generated_at": "2026-01-01T00:00:00Z",
            "evidence_ledger_id": "ledger_control_glyph_fixture",
        },
        "assessment": {
            "report_language": "es-MX" if spanish else "en",
            "sections": [],
        },
        "stage_summaries": [],
        "canonical_findings": [],
        "findings_register": [],
        "roadmap": [],
        "staffing_plan": [],
        "scanner_execution_records": [],
        "workflow_health": {},
    }

    pdf = producer._boundary_pdf_page(canonical, spanish=spanish)
    text = "\n".join(
        page.extract_text() or ""
        for page in PdfReader(io.BytesIO(pdf)).pages
    )

    assert f"- {marker}" in text
    forbidden = [
        f"U+{ord(character):04X}"
        for character in text
        if (
            ord(character) == 0x7F
            or (ord(character) < 32 and character not in "\n\r\t\f")
        )
    ]
    assert forbidden == []
