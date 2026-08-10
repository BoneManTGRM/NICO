from __future__ import annotations

from pathlib import Path

from nico.phase1_completion_report_contract_v1 import dod_rows, extract_report, validate_external

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "phase1-completion-bound-report.yml"


def report_text(sha: str) -> str:
    return f"""
    NICO Comprehensive Immutable commit: {sha}
    Current-evidence candidates requiring new technical triage: 62; fresh automated triage completed=62.
    Technical triage coverage: 629/629 (100.0%).
    Exact carry-forward: 567; location-changed: 0; evidence-changed: 28.
    Technical triage outcome totals: not_actionable=567, needs_review=62, confirmed=0.
    Individual human attention: 47; grouped-review eligible candidates: 15; grouped human-review clusters: 3; quality-control pool: 214.
    Human review work units: 50 from 62 observations.
    Technical triage remains proposal-only. Authorized human approval remains pending and client delivery remains blocked.
    Candidate workload has no numeric technical-maturity or Evidence-Adjusted score effect.
    Only an authorized reviewer may change the status to APPROVED FINAL and CLIENT DELIVERY AUTHORIZED.
    """


def evidence(sha: str):
    acceptance = {
        "artifact_schema": "nico.unified_live_acceptance.v1",
        "status": "passed",
        "expected_deployed_sha": sha,
        "passes_required": 2,
        "passes_completed": 2,
        "proof": {"exact_sha_bound": True, "two_passes": True},
    }
    audit = {
        "artifact_schema": "nico.phase1-structured-artifact-audit.v1",
        "status": "passed",
        "commit_sha": sha,
        "candidate_register_sha256_expected": "a" * 64,
        "candidate_register_sha256_observed": "a" * 64,
        "cluster_integrity_error_count": 0,
        "score_effect": "none",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "errors": [],
    }
    release = {
        "artifact_schema": "nico.frontend_production_release_identity.v1",
        "status": "passed",
        "expected_sha": sha,
        "final_release_observation": {"release_sha": sha},
    }
    required = [
        "Vercel",
        "successful-cat - NICO",
        "NICO Mobile Restart Production Proof",
        "NICO iOS WebKit Paint Proof",
        "NICO Two-Service Production Acceptance",
    ]
    status = {
        "artifact_schema": "nico.phase1-current-head-status.v1",
        "commit_sha": sha,
        "required_contexts": required,
        "contexts": {name: {"state": "success"} for name in required},
    }
    return acceptance, audit, release, status


def test_report_contract_covers_items_one_through_eight() -> None:
    sha = "1" * 40
    report = extract_report(report_text(sha), sha)
    assert report["fresh_completed"] == 62
    assert report["coverage_done"] == report["coverage_total"] == 629
    assert report["carry_forward"] == 567
    assert report["work_units"] == 50
    rows = dod_rows(report)
    assert len(rows) == 9
    assert rows[-1][0] == "9. Required current-head checks pass"


def test_external_evidence_closes_item_nine_fail_closed() -> None:
    sha = "2" * 40
    acceptance, audit, release, status = evidence(sha)
    validate_external(acceptance, audit, release, status, sha)
    status["contexts"]["NICO iOS WebKit Paint Proof"]["state"] = "pending"
    try:
        validate_external(acceptance, audit, release, status, sha)
    except ValueError as exc:
        assert "not successful" in str(exc)
    else:
        raise AssertionError("A pending exact-current-head context must fail closed")


def test_workflow_creates_one_post_acceptance_comprehensive_report() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")
    assert 'workflows: ["Unified Production Acceptance"]' in source
    assert "github.event.workflow_run.conclusion == 'success'" in source
    assert "scripts/phase1_completion_report_binder_v1.py" in source
    assert "NICO-COMPREHENSIVE-PHASE-1-COMPLETE.pdf" in source
    assert 'manifest["phase1_definition_of_done"][8]["status"] == "passed"' in source
    assert 'manifest["additional_report_product_created"] is False' in source
    assert 'manifest["human_approval_status"] == "pending"' in source
    assert 'manifest["client_delivery_allowed"] is False' in source
