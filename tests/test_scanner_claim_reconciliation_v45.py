from __future__ import annotations

from nico.scanner_claim_reconciliation_v45 import reconcile_scanner_claims_v45


def _payload() -> dict:
    return {
        "scanner_assurance_ledger": {
            "analyzers": [
                {"tool": "osv-scanner", "lifecycle_result": "completed_with_candidates", "raw_candidate_count": 1, "deduplicated_candidate_count": 1},
                {"tool": "bandit", "lifecycle_result": "failed", "raw_candidate_count": 0},
                {"tool": "eslint", "lifecycle_result": "not_configured", "raw_candidate_count": 0},
                {"tool": "gitleaks", "lifecycle_result": "timed_out", "raw_candidate_count": 10},
            ]
        },
        "sections": [
            {
                "id": "dependency_health",
                "evidence": ["OSV returned no vulnerability records for 12 pinned dependency query/queries."],
                "findings": ["Scanner-worker dependency tools reported 1 finding(s)."],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "evidence": [],
                "findings": ["Parsed gitleaks artifact reported 10 git-history secret finding(s)."],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "evidence": [
                    "Static evidence classification: current-run Bandit, Semgrep, ESLint, and TypeScript artifacts are complete for this report run.",
                    "Static review finding reconciliation: clean Bandit triage supersedes raw Bandit finding count for release-readiness gating.",
                    "Canonical scanner disposition: bandit=unknown; no stronger conclusion is inferred.",
                    "Canonical scanner disposition: eslint=unknown; no stronger conclusion is inferred.",
                ],
                "findings": [],
                "unavailable": ["Accepted current-run execution evidence remains unresolved for: eslint."],
            },
        ],
        "verification_checklist": ["Authorized I human reviewer approves the exact-snapshot report before client delivery."],
    }


def test_osv_direct_query_and_repository_scanner_scopes_are_explained() -> None:
    result = reconcile_scanner_claims_v45(_payload())
    dependency = result["sections"][0]

    assert any("Direct pinned-package OSV queries" in item for item in dependency["evidence"])
    assert any("separate repository-wide OSV scanner" in item for item in dependency["evidence"])
    assert not any("Scanner-worker dependency tools reported" in item for item in dependency["findings"])
    assert any("not confirmed vulnerabilities" in item for item in dependency["findings"])


def test_timed_out_gitleaks_candidates_are_not_presented_as_verified_findings() -> None:
    result = reconcile_scanner_claims_v45(_payload())
    secrets = result["sections"][1]

    assert secrets["gitleaks_partial_artifact_disposition"] == "review_only_timeout"
    assert any("review-only candidate" in item for item in secrets["findings"])
    assert not any("artifact reported 10 git-history secret finding" in item for item in secrets["findings"])


def test_failed_bandit_and_not_configured_eslint_are_reconciled() -> None:
    result = reconcile_scanner_claims_v45(_payload())
    static = result["sections"][2]

    assert static["bandit_execution_disposition"] == "failed_review_only"
    assert static["eslint_execution_disposition"] == "not_configured"
    assert any("Live Bandit execution failed" in item for item in static["evidence"])
    assert any("ESLint is not configured" in item for item in static["evidence"])
    assert not any("artifacts are complete" in item for item in static["evidence"])
    assert not static["unavailable"]


def test_copy_defect_is_removed_recursively() -> None:
    result = reconcile_scanner_claims_v45(_payload())

    assert result["verification_checklist"] == [
        "Authorized human reviewer approves the exact-snapshot report before client delivery."
    ]
