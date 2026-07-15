from __future__ import annotations

from nico.final_score_reconciliation_patch import (
    dependency_scanner_proof_is_clean,
    reconcile_final_evidence_scores,
)


def _section(section_id: str, score: int, evidence: list[str], findings: list[str] | None = None) -> dict:
    return {
        "id": section_id,
        "label": section_id,
        "score": score,
        "status": "green" if score >= 75 else "yellow",
        "summary": "Evidence-bound section.",
        "evidence": evidence,
        "findings": findings or [],
        "unavailable": [],
        "confidence": "high",
    }


def _result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 90},
        "complexity_engine": {"status": "completed", "risk_level": "medium"},
        "repository_metadata": {},
        "sections": [
            _section(
                "code_audit",
                86,
                [
                    "Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=0, test-path signals=0.",
                ],
                ["No test-path signals were found in fetched text files."],
            ),
            _section(
                "dependency_health",
                90,
                [
                    "requirements.txt found with 13 active dependency lines.",
                    "package.json found with 7 npm dependency entries across dependency sections.",
                    "Lockfile evidence found: apps/web/package-lock.json.",
                    "OSV returned no vulnerability records for 12 pinned dependency query/queries.",
                    "Parsed pip-audit and npm-audit artifacts reported zero dependency vulnerabilities.",
                ],
            ),
            _section(
                "secrets_review",
                92,
                [
                    "Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.",
                    "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                ],
            ),
            _section(
                "static_analysis",
                90,
                [
                    "Built-in static risk-pattern hits: 0.",
                    "Scanner-worker static tools completed: bandit, semgrep, eslint, typescript.",
                    "Bandit triage classified 0 finding(s): blocking=0, needs_review=0.",
                ],
            ),
            _section(
                "ci_cd",
                95,
                [
                    "GitHub Actions workflow runs returned in assessment window: 100.",
                    "Current GitHub Actions scanner artifact sets were fetched and parsed successfully.",
                ],
            ),
            _section(
                "architecture_debt",
                94,
                [
                    "Repository tree test-path signal count: 346.",
                    "Complexity engine analyzed 698 source file(s), 93126 source LOC, and 5218 function-like units.",
                ],
            ),
            _section(
                "velocity_complexity",
                84,
                [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                    "Complexity evidence verified for this report run.",
                ],
            ),
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
                "summary": "Human approval required.",
                "evidence": [],
                "findings": [],
                "unavailable": ["No approval record."],
            },
        ],
        "hosted_full_evidence_runtime_validation": {
            "tool_records": [
                {
                    "tool": name,
                    "status": "completed",
                    "findings_count": 0,
                    "verified_for_this_report": True,
                    "current_run": True,
                }
                for name in ("pip-audit", "npm-audit", "osv-scanner")
            ]
        },
        "reports": {},
    }


def test_structured_clean_dependency_proof_is_recognized() -> None:
    result = _result()

    assert dependency_scanner_proof_is_clean(result) is True


def test_final_reconciliation_raises_only_evidence_supported_scores() -> None:
    result = reconcile_final_evidence_scores(_result())
    by_id = {item["id"]: item for item in result["sections"]}

    assert by_id["code_audit"]["score"] == 90
    assert not any("No test-path signals" in item for item in by_id["code_audit"]["findings"])
    assert any("recursive repository tree contains 346" in item for item in by_id["code_audit"]["evidence"])
    assert by_id["dependency_health"]["score"] == 90
    assert by_id["velocity_complexity"]["score"] == 90
    assert result["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert result["release_readiness"]["missing_signals"] == []
    assert result["maturity_signal"]["score"] == 92
    assert result["score_details"]["score"] == 92
    detail_scores = {item["id"]: item["score"] for item in result["score_details"]["sections"]}
    assert detail_scores["dependency_health"] == 90
    assert detail_scores["velocity_complexity"] == 90
    assert result["final_score_reconciliation"]["score_inflation_allowed"] is False


def test_dependency_findings_block_release_readiness_lift() -> None:
    result = _result()
    result["hosted_full_evidence_runtime_validation"]["tool_records"][0]["findings_count"] = 1

    reconciled = reconcile_final_evidence_scores(result)
    velocity = next(item for item in reconciled["sections"] if item["id"] == "velocity_complexity")

    assert dependency_scanner_proof_is_clean(reconciled) is False
    assert reconciled["release_readiness"]["status"] == "evidence_incomplete"
    assert "dependency_scanner_clean_artifacts_attached" in reconciled["release_readiness"]["missing_signals"]
    assert velocity["score"] == 84


def test_bounded_sample_absence_is_not_removed_without_recursive_tree_proof() -> None:
    result = _result()
    architecture = next(item for item in result["sections"] if item["id"] == "architecture_debt")
    architecture["evidence"] = [item for item in architecture["evidence"] if "test-path" not in item]

    reconciled = reconcile_final_evidence_scores(result)
    code = next(item for item in reconciled["sections"] if item["id"] == "code_audit")

    assert code["score"] == 86
    assert any("No test-path signals" in item for item in code["findings"])
