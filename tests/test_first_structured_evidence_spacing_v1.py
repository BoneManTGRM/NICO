from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FORM = (
    ROOT
    / "apps"
    / "web"
    / "app"
    / "assessment"
    / "StrategicEvidenceForm.tsx"
).read_text(encoding="utf-8")
EVIDENCE = (
    ROOT
    / "apps"
    / "web"
    / "app"
    / "assessment"
    / "strategicEvidence.ts"
).read_text(encoding="utf-8")


def test_only_first_two_functional_qa_fields_keep_exact_live_drafts() -> None:
    assert 'const EXACT_DRAFT_MODULE = "functional_qa"' in FORM
    assert 'new Set(["test_cases", "observed_results"])' in FORM
    assert "const [structuredDrafts, setStructuredDrafts]" in FORM
    assert "const preserveExactDraft = exactDraftField(activeDefinition.moduleId, field)" in FORM
    assert "const rawValue = event.target.value" in FORM
    assert "[draftKey]: rawValue" in FORM
    assert 'data-exact-editing-draft={preserveExactDraft ? "true" : undefined}' in FORM
    assert "delete next[draftKey]" in FORM


def test_live_evidence_parser_does_not_trim_spaces_during_editing() -> None:
    editor = EVIDENCE.split("export function evidenceLines", 1)[1].split(
        "export function moduleCompleteness", 1
    )[0]
    assert ".split(/\\r?\\n/)" in editor
    assert ".map((item) => item.trim())" not in editor
    assert ".filter(Boolean)" not in editor
