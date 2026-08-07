from __future__ import annotations

from pathlib import Path


def test_runtime_patch_orders_identity_context_lineage_triage_and_workload() -> None:
    source = Path("nico/candidate_lineage_runtime_patch_v1.py").read_text(
        encoding="utf-8"
    )

    canonical = source.index("register = current_builder(scan, commit_sha)")
    identity = source.index("subject, normalization = scan_assessment_subject(scan)")
    context = source.index("register = enrich_canonical_candidate_evidence(register, scan)")
    lineage = source.index("register = apply_candidate_lineage(register)")
    technical = source.index("register = apply_candidate_technical_triage(register)")
    workload = source.index("return refine_candidate_review_workload(register)")
    assert canonical < identity < context < lineage < technical < workload
    assert "install_osv_scanner_context_patch()" in source
    assert "install_phase1_report_workload_patch()" in source
    assert '"human_approval_carried_forward": False' in source
    assert '"client_delivery_allowed": False' in source
    assert '"real_project_workspace_target_identity_remains_fail_closed": True' in source


def test_runtime_report_surface_distinguishes_technical_from_human_review() -> None:
    source = Path("nico/candidate_lineage_runtime_patch_v1.py").read_text(
        encoding="utf-8"
    )

    assert "Technical triage proposals imported for " in source
    assert "Current-evidence candidates requiring new technical triage: " in source
    assert "Human review work units: " in source
    assert "NICO automated technical triage completed" in source
    assert "Technical triage remains proposal-only." in source
    assert "Authorized human approval" in source
