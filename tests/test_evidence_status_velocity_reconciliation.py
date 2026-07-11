from __future__ import annotations

from nico.evidence_status import apply_report_evidence_status
from nico.final_report_consistency import finalize_express_result_consistency


def _base_result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 89},
        "scanner_artifact_summary": {"files": ["complexity-profile.json"]},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "status": "green",
                "score": 86,
                "summary": "Code audit.",
                "evidence": ["actionable TODO/FIXME/security markers=0"],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is verified by current-run clean pip-audit, npm audit, and OSV Scanner artifacts.",
                "evidence": [
                    "requirements.txt found with 13 active dependency lines.",
                    "package.json found with 0 npm dependency entries across dependency sections.",
                    "Lockfile evidence found: apps/web/package-lock.json.",
                    "OSV returned no vulnerability records for 12 pinned dependency query/queries.",
                    "Parsed GitHub Actions pip-audit, npm-audit, and OSV Scanner artifacts reported zero dependency vulnerabilities.",
                ],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "status": "green",
                "score": 92,
                "summary": "Secrets review is verified by current-run clean credential-scan, gitleaks, and trufflehog full-history artifacts.",
                "evidence": [
                    "Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.",
                    "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                ],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 90,
                "summary": "Static analysis is verified by current-run Bandit, Semgrep, ESLint, and TypeScript artifacts.",
                "evidence": [
                    "Built-in static risk-pattern hits: 0.",
                    "Scanner-worker static tools completed: bandit, semgrep, eslint, typescript.",
                    "Bandit triage classified 0 finding(s): blocking=0, needs_review=0, approved=0, candidate_false_positive=0.",
                ],
                "findings": ["Parsed Bandit artifact reported 57 finding(s)."],
                "unavailable": [],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "status": "green",
                "score": 95,
                "summary": "CI/CD maturity separates current release-readiness checks from historical workflow reliability.",
                "evidence": [
                    "Workflow text includes test, lint, or build commands.",
                    "GitHub Actions workflow runs returned in assessment window: 100; success=89; non-success=11.",
                    "Current GitHub Actions scanner artifact sets were fetched and parsed successfully.",
                ],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "status": "green",
                "score": 94,
                "summary": "Architecture review uses repository layout.",
                "evidence": ["Repository tree source-file signal count: 333."],
                "findings": [],
                "unavailable": ["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker that checks out the repo and runs language-specific analyzers."],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "status": "yellow",
                "score": 74,
                "summary": "Velocity / Complexity is review-limited.",
                "evidence": [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                    "Source-file footprint from recursive tree: 333 files.",
                ],
                "findings": [],
                "unavailable": ["Release-readiness lift not applied because required final-clean evidence is incomplete: static_analysis_no_review_findings"],
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "status": "gray",
                "score": 0,
                "summary": "Final report acceptance is not scored until an approved same-project review record exists.",
                "evidence": [],
                "findings": [],
                "unavailable": ["No approved final report/client acceptance approval record was found for this project."],
            },
        ],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_clean_bandit_triage_removes_static_review_finding_and_attaches_complexity() -> None:
    result = apply_report_evidence_status(_base_result())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert static["findings"] == []
    assert result["complexity_engine"]["artifact"] == "complexity-profile.json"
    assert any("Complexity evidence attached" in item for item in velocity["evidence"])
    assert not any("static_analysis_no_review_findings" in item for item in velocity["unavailable"])


def test_final_consistency_lifts_velocity_when_clean_static_and_complexity_are_attached() -> None:
    result = finalize_express_result_consistency(_base_result())
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert result["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert "static_analysis_no_review_findings" not in result["release_readiness"]["missing_signals"]
    assert velocity["score"] >= 90
    assert velocity["status"] == "green"
