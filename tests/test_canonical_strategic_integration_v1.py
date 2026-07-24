from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_comprehensive_report_attaches_canonical_manifest_and_premium_exports() -> None:
    source = _read("nico/comprehensive_decision_grade_report_v5.py")

    assert "attach_canonical_strategic_package" in source
    assert 'depth="strategic"' in source
    assert '"canonical_run_manifest"' in source
    assert '"evidence_manifest"' in source
    assert '"premium_artifact_manifest"' in source
    assert '"code_remediation_plan"' in source
    assert '"risk_register"' in source
    assert '"canonical_score_assurance_ledger_present"' in source
    assert '"implementation_ready_remediation_plan_present"' in source
    assert 'and quality["canonical_run_manifest_present"]' in source


def test_express_completion_is_bound_to_same_canonical_contract() -> None:
    binding = _read("nico/canonical_express_binding_v1.py")
    bootstrap = _read("nico/api/terminal_authority_bootstrap.py")

    assert "attach_canonical_strategic_package" in binding
    assert 'source["assessment_depth"] = "core"' in binding
    assert 'depth="core"' in binding
    assert '"same_contract_used_by_strategic": True' in binding
    assert '"independent_core_scorecard_allowed": False' in binding
    assert "install_canonical_express_binding_v1" in bootstrap
    assert "CANONICAL_EXPRESS_BINDING" in bootstrap
    assert "Completed Express runs do not receive the canonical Core package contract" in bootstrap
    assert "Core and Strategic are not bound to the same canonical package contract" in bootstrap


def test_canonical_contract_does_not_auto_approve_or_apply_unreviewed_code() -> None:
    source = _read("nico/canonical_strategic_package_v1.py")

    assert '"automatic_code_change_performed": False' in source
    assert '"proposed_diff": ""' in source
    assert '"requires_human_engineering_review": True' in source
    assert '"automatic_approval": False' in source
    assert '"client_delivery_allowed": False' in source
    assert "named_human_approval_missing" in source
    assert "named_reviewer_missing" in source
