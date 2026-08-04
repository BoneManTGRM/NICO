from __future__ import annotations

from pathlib import Path


EVIDENCE = Path("apps/web/app/assessment/assessmentEvidence.ts")
WORKSPACE = Path("apps/web/app/assessment/AssessmentWorkspace.tsx")


def test_terminal_stage_evidence_is_bounded_before_react_rendering() -> None:
    source = EVIDENCE.read_text(encoding="utf-8")

    assert "BROWSER_EVIDENCE_KEY_LIMIT = 24" in source
    assert "BROWSER_ARRAY_PREVIEW_LIMIT = 8" in source
    assert "export function browserEvidencePreview" in source
    assert "top_level_key_count" in source
    assert "keys_retained" in source
    assert "complete_evidence" in source
    assert "Retained in the canonical report and machine-readable assessment artifacts." in source
    assert "evidence: browserEvidencePreview(value.evidence)" in source
    assert "evidence: value.evidence" not in source


def test_workspace_never_stringifies_unbounded_stage_evidence() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    assert "JSON.stringify(item.evidence, null, 2)" in workspace
    assert "browserEvidencePreview(value.evidence)" in evidence
    assert "compactBrowserValue" in evidence
    assert "item_count" in evidence
    assert "key_count" in evidence
