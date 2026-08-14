from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "scripts" / "phase1_structured_artifact_audit_v1.py"
RUNTIME_PATCH = ROOT / "nico" / "candidate_lineage_runtime_patch_v1.py"


def test_phase1_audit_uses_current_canonical_lineage_taxonomy() -> None:
    source = AUDIT.read_text(encoding="utf-8")

    assert '"carried_forward_evidence_changed"' in source
    assert '"carried_forward_exact"' in source
    assert '"carried_forward_location_changed"' in source
    assert '"newly_observed"' in source
    assert 'lineage_status == "carried_forward_evidence_changed"' in source
    assert 'source.startswith("fresh_")' in source
    assert '"exact_carry_forward"' not in source


def test_phase1_audit_keeps_dependency_reachability_fail_safe() -> None:
    source = AUDIT.read_text(encoding="utf-8")

    assert '"first_party_reachability" in (record.get("proof_gaps") or [])' in source
    assert "reachability_gap_not_explicit" in source
    assert 'rationale_code != "dependency_resolution_not_affected"' in source


def test_runtime_revalidates_retained_triage_before_workload_routing() -> None:
    source = RUNTIME_PATCH.read_text(encoding="utf-8")
    triage = source.index("register = apply_candidate_technical_triage(register)")
    revalidate = source.index("register = revalidate_retained_candidate_triage(register)")
    refine = source.index("return refine_candidate_review_workload(register)")

    assert triage < revalidate < refine
    assert '"client_delivery_allowed": False' in source
    assert '"human_approval_may_carry_forward": False' in source
