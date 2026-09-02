from __future__ import annotations

import base64
import io

import pytest
from pypdf import PdfReader

from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY


@pytest.mark.parametrize("spanish", [False, True])
def test_active_pdf_source_passes_finality_gate_with_embedded_fonts(spanish: bool) -> None:
    from nico.comprehensive_pdf_embedded_fonts_v1 import (
        install_comprehensive_pdf_embedded_fonts_v1,
    )
    from nico.comprehensive_report_package import _pdf
    from nico.comprehensive_spanish_canonical_report_v87 import _translate_presentation
    from nico.v2_automated_draft_quality_compat_v1 import (
        _contains_legacy_bare_draft,
        _validate_review_pdf,
    )

    install_comprehensive_pdf_embedded_fonts_v1()
    run_id = "comprun_embedded_font_draft_source"
    commit_sha = "a" * 40
    identity = {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "commit_sha": commit_sha,
        "customer_id": "customer-production-verification",
        "project_id": "project-production-verification",
    }
    assessment = {
        "maturity_signal": {"presented_score": 93, "level": "advanced"},
        "sections": [],
    }
    encoded, error, page_count = _pdf(
        identity,
        assessment,
        [],
        "2026-09-02T12:00:00Z",
        localize_presentation=_translate_presentation if spanish else None,
    )

    assert error is None
    assert encoded
    pdf = base64.b64decode(encoded)
    assert page_count >= 3
    extracted = "\n".join(
        page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages
    )
    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    assert boundary in extracted
    assert _contains_legacy_bare_draft(extracted) is False
    _validate_review_pdf(
        pdf,
        {"identity": identity},
        expected_sections=[],
        spanish=spanish,
    )
