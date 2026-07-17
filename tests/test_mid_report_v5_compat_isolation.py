from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPAT = ROOT / "nico" / "mid_report_v5_compat.py"


def test_mid_pdf_heading_compatibility_is_context_local() -> None:
    source = COMPAT.read_text(encoding="utf-8")

    assert "from contextvars import ContextVar" in source
    assert "_PDF_HEADING_REPLACEMENTS" in source
    assert "token = _PDF_HEADING_REPLACEMENTS.set(replacements)" in source
    assert "_PDF_HEADING_REPLACEMENTS.reset(token)" in source
    assert "flowable_module._paragraph = paragraph_dispatch" in source
    assert "flowable_module._paragraph = original_paragraph" not in source
    assert '"concurrent_pdf_rendering_isolated": True' in source
