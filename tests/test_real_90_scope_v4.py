from __future__ import annotations

from pathlib import Path


def test_scope_does_not_claim_architecture_remediation_or_delivery_approval() -> None:
    text = Path("docs/real-90-remediation-scope-v4.md").read_text(encoding="utf-8")
    assert "does not alter the architecture score" in text
    assert "remove human review" in text
    assert "authorize client delivery" in text
    assert "target score as an input" in text
