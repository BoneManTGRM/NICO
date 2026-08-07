from __future__ import annotations

from pathlib import Path


def test_runtime_patch_applies_lineage_before_technical_triage() -> None:
    source = Path("nico/candidate_lineage_runtime_patch_v1.py").read_text(
        encoding="utf-8"
    )

    lineage = source.index(
        "register = apply_candidate_lineage(current_builder(scan, commit_sha))"
    )
    technical = source.index("return apply_candidate_technical_triage(register)")
    assert lineage < technical
    assert "install_osv_scanner_context_patch()" in source
    assert '"human_approval_carried_forward": False' in source
    assert '"client_delivery_allowed": False' in source


def test_runtime_report_surface_distinguishes_technical_from_human_review() -> None:
    source = Path("nico/candidate_lineage_runtime_patch_v1.py").read_text(
        encoding="utf-8"
    )

    assert "Technical triage proposals imported for " in source
    assert "Current-evidence candidates requiring new technical triage: " in source
    assert "Technical triage remains proposal-only." in source
    assert "Authorized human approval" in source
