from pathlib import Path


def test_runtime_evidence_fix_handoff_names_real_remaining_gaps():
    text = Path("docs/report-runtime-evidence-fix-pr.md").read_text(encoding="utf-8")
    assert "nico-express-BoneManTGRM-NICO(9).pdf" in text
    assert "85/100" in text
    assert "PyJWT[crypto]" in text
    assert "Normalize package identity before OSV lookup" in text
    assert "Remaining honest blockers are unchanged" in text
