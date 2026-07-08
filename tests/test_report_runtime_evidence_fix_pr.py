from pathlib import Path


def test_runtime_evidence_fix_handoff_names_real_remaining_gaps():
    text = Path("docs/report-runtime-evidence-fix-pr.md").read_text(encoding="utf-8")
    assert "nico-express-BoneManTGRM-NICO(8).pdf" in text
    assert "PyJWT[crypto]" in text
    assert "does not fake scanner artifacts" in text
    assert "only rise if the hosted report actually consumes clean current-run" in text
