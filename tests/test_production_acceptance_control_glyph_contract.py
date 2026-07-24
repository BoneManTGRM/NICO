from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_acceptance_keeps_control_character_guard() -> None:
    source = (ROOT / "scripts/two_service_live_acceptance.py").read_text(encoding="utf-8")

    assert 'assert "\\x7f" not in pdf["text"], "Comprehensive PDF contains a control-character glyph"' in source


def test_comprehensive_pdf_sources_use_extraction_safe_list_markers() -> None:
    premium = (ROOT / "nico/comprehensive_premium_pdf_v6.py").read_text(encoding="utf-8")
    supplement = (ROOT / "nico/comprehensive_decision_grade_pdf_v5.py").read_text(encoding="utf-8")

    assert 'p(f"- {_text(item, 900)}", small)' in premium
    assert 'p(f"• {_text(item, 900)}", small)' not in premium
    assert 'return p(f"- {_text(value, 2100)}", small)' in supplement
    assert 'f"• {item}"' not in supplement
