from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "docs" / "phase3-finish-summary.md"


def test_phase3_finish_scope_preserves_protected_boundaries() -> None:
    text = SUMMARY.read_text(encoding="utf-8")
    assert "production-acceptance harness mismatch" in text
    assert "synthetic client/project labels" in text
    for boundary in ("scoring", "authorization", "human review", "approval", "client delivery"):
        assert boundary in text
