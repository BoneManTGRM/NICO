from __future__ import annotations

from typing import Any

from nico.final_report_consistency import finalize_express_result_consistency


def live_score_check() -> dict[str, Any]:
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": [
                {"id": "code_audit", "label": "Code Audit", "score": 86, "status": "green", "summary": "", "evidence": ["actionable TODO/FIXME/security markers=0"], "findings": [], "unavailable": []},
                {"id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 90, "status": "green", "summary": "", "evidence": ["requirements.txt found", "package.json found", "Lockfile evidence found", "pip-audit", "npm-audit"], "findings": [], "unavailable": []},
                {"id": "secrets_review", "label": "Secrets Exposure Review", "score": 88, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
                {"id": "static_analysis", "label": "Static Analysis", "score": 70, "status": "yellow", "summary": "", "evidence": ["Built-in static risk-pattern hits: 0."], "findings": [], "unavailable": ["External analyzer execution is unavailable."]},
                {"id": "ci_cd", "label": "CI/CD Analysis", "score": 95, "status": "green", "summary": "", "evidence": ["GitHub Actions workflow runs returned in assessment window: 100; success=91; non-success=9."], "findings": [], "unavailable": []},
                {"id": "architecture_debt", "label": "Architecture & Technical Debt", "score": 94, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
                {"id": "velocity_complexity", "label": "Velocity / Complexity", "score": 73, "status": "yellow", "summary": "", "evidence": ["Commit velocity: 100 commits over 180 days.", "Pull request traceability ratio: 90 PRs / 100 commits = 0.9."], "findings": [], "unavailable": ["Human review required."]},
            ],
            "reports": {},
        }
    )
    scores = {item["id"]: item.get("score") for item in result.get("sections", []) if isinstance(item, dict)}
    statuses = {item["id"]: item.get("status") for item in result.get("sections", []) if isinstance(item, dict)}
    overall = int((result.get("maturity_signal") or {}).get("score") or 0)
    return {
        "status": "ok" if overall > 85 else "needs_review",
        "overall_score": overall,
        "expected_above_85": overall > 85,
        "section_scores": scores,
        "section_statuses": statuses,
        "rule": "This check runs the live final scoring helper against the known 85-point fixture.",
    }
