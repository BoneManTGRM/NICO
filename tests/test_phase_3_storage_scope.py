from __future__ import annotations

from pathlib import Path


def test_phase_3_storage_scope_keeps_unsafe_actions_out() -> None:
    text = (Path(__file__).resolve().parents[1] / "docs" / "phase-3-storage-schema-scope.md").read_text(encoding="utf-8").lower()

    assert "automatic destructive migration" in text
    assert "backup creation or restore execution" in text
    assert "automatic workflow resume" in text
    assert "client-delivery authorization" in text
    assert "assessment score changes" in text
    assert "restart/resume and duplicate-prevention" in text
