from __future__ import annotations

from nico.final_report_consistency import finalize_express_result_consistency


def base_result() -> dict:
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "evidence": []},
            {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "status": "green", "score": 90, "evidence": ["requirements.txt found", "package.json found", "Lockfile evidence found: apps/web/package-lock.json.", "Parsed GitHub Actions pip-audit, npm-audit, and OSV Scanner artifacts reported zero dependency vulnerabilities."], "findings": []},
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "yellow", "score": 74, "summary": "Secrets review is review-limited.", "evidence": ["Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.", "Secrets evidence classification: parsed credential-scan and gitleaks artifacts reported zero high-confidence credential findings for this run.", "Scanner-worker secret tools completed: gitleaks, trufflehog.", "Refresh Full Evidence required tool records: gitleaks=completed, trufflehog=completed."], "findings": ["Strict trust engine: Secrets cannot receive scanner-clean status while full-history secret coverage is unavailable or unverified.", "Strict trust engine: Secrets cannot be GREEN while full-history secret coverage is unavailable or unverified."], "unavailable": ["Full git-history secret coverage was not verified for this report run; attached credential artifacts and live full-history scanner proof are separate evidence sources."]},
            {"id": "static_analysis", "label": "Static Analysis", "status": "green", "score": 90, "evidence": ["Built-in static risk-pattern hits: 0.", "Verified score lift: static scanner artifacts are complete and bound to this report run.", "Scanner-worker static tools completed: bandit, semgrep, eslint, typescript.", "Bandit triage classified 0 finding(s): blocking=0, needs_review=0, approved=0, candidate_false_positive=0."], "findings": []},
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "evidence": ["Workflow text includes test, lint, or build commands.", "GitHub Actions workflow runs returned in assessment window: 100; success=94; non-success=6.", "Current GitHub Actions scanner artifact sets were fetched and parsed successfully."]},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "evidence": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 74, "evidence": ["Commit velocity: 100 commits over 180 days (3.89/week).", "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.", "Source-file footprint from recursive tree: 331 files."], "findings": ["Strict trust engine: Velocity / Complexity cannot be GREEN while release-readiness blockers or missing complexity evidence remain."], "unavailable": ["Release-readiness lift not applied because required final-clean evidence is incomplete: static_analysis_no_review_findings"]},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "evidence": []},
        ],
    }


def test_full_history_secret_evidence_lifts_secrets_and_release_readiness() -> None:
    result = finalize_express_result_consistency(base_result())

    secrets = next(item for item in result["sections"] if item["id"] == "secrets_review")
    velocity = next(item for item in result["sections"] if item["id"] == "velocity_complexity")

    assert secrets["status"] == "green"
    assert secrets["score"] >= 90
    assert not any("strict trust engine" in str(item).lower() for item in secrets.get("findings", []))
    assert result["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert "static_analysis_no_review_findings" not in result["release_readiness"]["missing_signals"]
    assert velocity["status"] == "green"
    assert velocity["score"] >= 90
    assert result["maturity_signal"]["score"] >= 90
