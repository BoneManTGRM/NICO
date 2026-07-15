from __future__ import annotations

from nico import assessment_quality
from nico import final_report_consistency
from nico.post_polish_score_reconciliation_patch import (
    install_post_polish_score_reconciliation_patch,
    reconcile_after_polish,
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


def _post_polish_state() -> dict:
    sections = [
        _section(
            "code_audit",
            90,
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
                "Repository tree test-path signal count: 348.",
                "Complexity engine analyzed 702 source file(s), 93880 source LOC, and 5182 function-like units.",
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
    ]
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 91},
        "executive_summary": "Stale summary 91/100.",
        "sections": sections,
        "release_readiness": {
            "status": "evidence_incomplete",
            "passed_signals": [],
            "missing_signals": ["dependency_scanner_clean_artifacts_attached"],
        },
        "score_details": {
            "score": 90,
            "sections": [
                {
                    "id": item["id"],
                    "score": 86 if item["id"] == "dependency_health" else item["score"],
                }
                for item in sections
            ],
        },
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
        "complexity_engine": {"status": "completed", "risk_level": "medium"},
        "reports": {},
        "human_review_required": True,
        "client_ready": False,
    }


def test_post_polish_reconciliation_is_the_final_score_source(monkeypatch) -> None:
    rebuild_calls: list[int] = []
    monkeypatch.setattr(
        final_report_consistency,
        "_rebuild_reports",
        lambda result: rebuild_calls.append(int(result["maturity_signal"]["score"])),
    )

    result = reconcile_after_polish(_post_polish_state())
    by_id = {item["id"]: item for item in result["sections"]}
    detail_by_id = {item["id"]: item for item in result["score_details"]["sections"]}

    assert result["maturity_signal"]["score"] == 92
    assert result["score_details"]["score"] == 92
    assert by_id["code_audit"]["score"] == 90
    assert not any("No test-path signals" in item for item in by_id["code_audit"]["findings"])
    assert by_id["dependency_health"]["score"] == 90
    assert detail_by_id["dependency_health"]["score"] == 90
    assert by_id["velocity_complexity"]["score"] == 90
    assert detail_by_id["velocity_complexity"]["score"] == 90
    assert result["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert result["release_readiness"]["missing_signals"] == []
    assert "92/100" in result["executive_summary"]
    assert result["score_source_of_truth"]["final_stage"] == "post_polish_score_reconciliation"
    assert result["final_score_reconciliation"]["post_polish_applied"] is True
    assert rebuild_calls[-1] == 92
    assert result["human_review_required"] is True
    assert result["client_ready"] is False


def test_installer_is_idempotent_and_active_last() -> None:
    first = install_post_polish_score_reconciliation_patch()
    second = install_post_polish_score_reconciliation_patch()

    assert getattr(assessment_quality.polish_express_result, "_nico_post_polish_score_reconciliation_v1", False) is True
    assert first["post_polish_reconciliation"] is True
    assert second["post_polish_reconciliation"] is True
    assert second["status"] == "already_installed"
