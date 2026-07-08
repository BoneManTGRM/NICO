from pathlib import Path


def test_runtime_evidence_notes_preserve_no_fake_artifact_rule():
    text = Path("docs/report-runtime-evidence-notes.md").read_text(encoding="utf-8")
    assert "must not claim scanner-clean or release-ready" in text
    assert "Workflow artifacts from GitHub Actions are not automatically attached" in text
