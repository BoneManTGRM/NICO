from __future__ import annotations

from copy import deepcopy

from nico.client_assessment_truth_v3 import normalize_client_assessment_truth
from nico.client_finding_remediation_register_v3 import (
    build_finding_remediation_register,
    canonical_findings_from_register,
)


SHA = "a" * 40


def _canonical() -> dict:
    return {
        "identity": {
            "repository": "example/product",
            "commit_sha": SHA,
            "run_id": "comprun_truth_v3",
        },
        "canonical_findings": [
            {
                "finding_id": "RISK-P1-LEGACY",
                "priority": "P1",
                "category": "architecture",
                "status": "open",
                "title": "operations page has concentrated branching and elevated change risk",
                "location": "apps/web/app/operations/page.tsx:177",
                "fact": "cyclomatic_complexity=52; loc=173; grade=F; method=typescript_compiler_ast",
                "interpretation": "High-complexity code hotspot",
                "business_impact": "Concentrated branching increases regression risk.",
                "recommendation": "Decompose the hotspot.",
                "acceptance_criteria": ["Complexity is at or below 30."],
                "production_scope": True,
                "exact_commit_match": True,
            }
        ],
        "complexity_evidence": {
            "hotspots": [
                {
                    "path": "apps/web/app/operations/page.tsx",
                    "line": 177,
                    "name": "OperationsPage",
                    "cyclomatic_complexity": 52,
                    "loc": 173,
                    "grade": "F",
                    "method": "typescript_compiler_ast",
                    "source_excerpt": "export default function OperationsPage() { /* branches */ }",
                }
            ]
        },
        "repository_evidence": {
            "code_signal_evidence": {
                "sample": (
                    "nico/client_finding_remediation_register_v1.py:225: "
                    "tls_verify_disabled — Disabled TLS verification should not ship to production."
                )
            }
        },
        "scanner_execution_records": [
            {
                "scanner_name": "eslint",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "verified_complete": True,
                "exact_commit_match": True,
                "artifact_hash": "b" * 64,
                "findings": [
                    {
                        "path": (
                            "/tmp/nico-snapshot-scan-abc123/repo/"
                            "apps/web/app/operations/AssessmentRecoveryPanel.tsx"
                        ),
                        "line": 110,
                        "column": 5,
                        "message": (
                            "Definition for rule 'react-hooks/exhaustive-deps' was not found."
                        ),
                    }
                ],
            },
            {
                "scanner_name": "semgrep",
                "category": "security",
                "state": "completed_with_findings",
                "status": "completed_with_findings",
                "completed": True,
                "verified": True,
                "verified_complete": True,
                "exact_commit_match": True,
                "artifact_hash": "c" * 64,
                "findings": [
                    {
                        "path": "src/http_client.py",
                        "line": 20,
                        "check_id": "tls_verify_disabled",
                        "message": "Certificate verification is disabled.",
                        "source_excerpt": "response = requests.get(url, verify=False)",
                        "severity": "high",
                    }
                ],
            },
        ],
        "assessment": {
            "sections": [
                {
                    "id": "static_analysis",
                    "label": "Static Analysis",
                    "score": 83,
                    "status": "REVIEW_LIMITED_NOT_SCORED",
                    "unavailable": ["eslint configuration failed"],
                }
            ],
            "final_report_input_scores_synchronized": True,
            "report_contract_status": "blocked",
            "report_contract_reason": "canonical_score_truth_mismatch",
        },
        "report_contract_status": "blocked",
        "report_contract_reason": "canonical_score_truth_mismatch",
    }


def test_truth_normalization_separates_scanner_configuration_and_assurance() -> None:
    result = normalize_client_assessment_truth(_canonical())
    eslint = next(
        item for item in result["scanner_execution_records"]
        if item["scanner_name"] == "eslint"
    )

    assert eslint["state"] == "configuration_failed"
    assert eslint["completed"] is False
    assert eslint["verified_complete"] is False
    assert eslint["findings"] == []
    assert eslint["scanner_configuration_error_count"] == 1
    assert eslint["scanner_configuration_findings"][0]["path"] == (
        "apps/web/app/operations/AssessmentRecoveryPanel.tsx"
    )
    assert result["scanner_configuration_issues"][0]["scanner_name"] == "eslint"

    section = result["assessment"]["sections"][0]
    assert section["presented_status"] == "MODERATE"
    assert section["assurance_status"] == "review_limited"
    assert section["execution_and_assurance_separated"] is True

    assert result["report_contract_status"] == "reconciled"
    assert result["assessment"]["report_contract_status"] == "reconciled"


def test_register_deduplicates_source_anchor_and_blocks_false_promotions() -> None:
    register = build_finding_remediation_register(_canonical())
    code = register["code_findings"]
    operational = register["operational_findings"]
    summary = register["summary"]

    operations = [
        item for item in code
        if item["location"] == "apps/web/app/operations/page.tsx:177"
    ]
    assert len(operations) == 1
    assert operations[0]["symbol"] == "OperationsPage"
    assert operations[0]["rule_id"] == "complexity_hotspot"
    assert "typed hooks or services" in operations[0]["recommended_correction"]
    assert "export default function OperationsPage" in operations[0]["source_excerpt"]
    assert "RISK-P1-LEGACY" in operations[0]["finding_aliases"]

    tls = [item for item in code if item["location"] == "src/http_client.py:20"]
    assert len(tls) == 1
    assert tls[0]["finding_family"] == "tls_verify_disabled"
    assert "verify=False" in tls[0]["source_excerpt"]

    assert all("/tmp/" not in str(item.get("path") or "") for item in code)
    assert all("react-hooks/exhaustive-deps" not in str(item) for item in code)
    assert all(
        item.get("location") != "nico/client_finding_remediation_register_v1.py:225"
        for item in code
    )
    false_tls = [
        item for item in operational
        if item.get("promotion_blocked_reason") == "executable_tls_source_evidence_not_retained"
    ]
    assert len(false_tls) == 1
    assert false_tls[0]["priority"] == "P2"
    assert false_tls[0]["title"] == "Unverified TLS pattern candidate"

    assert summary["semantic_duplicate_code_anchors_absent"] is True
    assert summary["scanner_configuration_errors_promoted_to_code_findings"] is False
    assert summary["unverified_tls_candidates_promoted_to_p1"] is False
    assert summary["repository_relative_paths_only"] is True
    assert summary["finding_population_reconciled"] is True
    assert summary["raw_observation_count"] >= summary["normalized_candidate_count"]
    assert summary["normalized_candidate_count"] >= summary["decision_finding_count"]


def test_stable_code_identity_survives_repeat_commit() -> None:
    first = build_finding_remediation_register(_canonical())
    changed = deepcopy(_canonical())
    changed["identity"]["commit_sha"] = "d" * 40
    second = build_finding_remediation_register(changed)

    first_id = next(
        item["finding_id"] for item in first["code_findings"]
        if item["location"] == "apps/web/app/operations/page.tsx:177"
    )
    second_id = next(
        item["finding_id"] for item in second["code_findings"]
        if item["location"] == "apps/web/app/operations/page.tsx:177"
    )
    assert first_id == second_id

    projected = canonical_findings_from_register(first)
    assert len(projected) == first["summary"]["decision_finding_count"]
    assert len({item["finding_id"] for item in projected}) == len(projected)
