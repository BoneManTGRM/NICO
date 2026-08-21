from __future__ import annotations

from pathlib import Path


SCRIPT = Path("scripts/spanish_comprehensive_live_acceptance_v1.py")


def test_spanish_production_pdf_canary_rejects_rich_finding_english_labels() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for marker in (
        '"Finding ID:"',
        '"Category / status:"',
        '"Exact source:"',
        '"Analyzer / rule:"',
        '"Technical consequence:"',
        '"Business consequence:"',
        '"Specific correction:"',
        '"Owner / effort:"',
        '"Cost of inaction:"',
        '"Residual risk:"',
        '"Acceptance / exit criteria:"',
        '"Final exit criteria:"',
    ):
        assert marker in source

    assert "forbidden = [marker for marker in FORBIDDEN_PDF_MARKERS if marker in rendered]" in source
    assert "assert not forbidden" in source
    assert "Spanish PDF retained forbidden English/failure markers: {forbidden}" in source
