from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.report_final_qa import apply_final_report_qa


def _new_report_contradiction_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T21:12:08Z",
        "client_name": "",
        "project_name": "NICO",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "executive_summary": "NICO completed an authorized hosted Express Technical Health Assessment for BoneManTGRM/NICO.",
        "maturity_signal": {"level": "Senior", "score": 86},
        "maturity_semaphore": {},
        "project_trend_evidence": {"status": "tracked", "prior_run_count": 9, "previous_score": 89, "average_prior_score": 89, "current_score": 83},
        "sections": [
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86, "summary": "Code audit.", "evidence": [], "findings": [], "unavailable": []},
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from available manifest, lockfile, and OSV API evidence, but OSV returned vulnerability records and final scanner-clean dependency status is not claimed.",
                "evidence": [
                    "requirements.txt found with 13 active dependency lines.",
                    "OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-752w-5fwx-jx9f, GHSA-993g-76c3-p5m4.",
                ],
                "findings": ["Dependency evidence status: OSV API completed_with_findings; final scanner-clean status is not claimed without pip-audit/npm audit/OSV Scanner artifacts for this run."],
                "unavailable": ["Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner."],
            },
            {"id": "secrets_review", "label": "Secrets Exposure Review", "status": "green", "score": 90, "summary": "Secrets.", "evidence": [], "findings": [], "unavailable": []},
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 86,
                "summary": "Static analysis uses clean built-in pattern checks plus CI-backed evidence, but Bandit artifact findings require explicit triage; the green score is not a final scanner-clean claim.",
                "evidence": ["Built-in static risk-pattern hits: 0."],
                "findings": ["Parsed Bandit artifact reported 50 finding(s).", "Bandit triage summary: total=50, blocker_count=0, review_required_count=50, candidate_false_positive_count=0; score impact=needs_human_review until rule-level triage is attached and approved."],
                "unavailable": ["Live scanner-worker artifacts for Semgrep, Bandit, ESLint, and TypeScript were not attached or verified for this report run."],
            },
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 80, "summary": "CI.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity / Complexity", "status": "yellow", "score": 73, "summary": "Velocity.", "evidence": ["Project trend evidence: 9 prior completed Express run(s); previous score=89; prior average=89; current score=83; delta vs previous=-6."], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings": [],
        "repairs": [],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "stale GREEN 90 PyJWT@[crypto] current score=83", "html": "", "pdf_base64": ""},
    }


def test_final_report_qa_blocks_green_dependency_and_static_contradictions():
    result = apply_final_report_qa(_new_report_contradiction_result())
    dependency = next(item for item in result["sections"] if item["id"] == "dependency_health")
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")

    assert dependency["status"] == "yellow"
    assert dependency["score"] == 74
    assert "green" not in dependency["summary"].lower()
    assert "PyJWT@[crypto]" not in "\n".join(dependency["evidence"])
    assert static["status"] == "yellow"
    assert static["score"] == 74
    assert "green" not in static["summary"].lower()
    assert result["maturity_signal"]["score"] == 82
    assert result["report_quality_guards"]["final_report_qa"]["status"] == "applied"


def test_hosted_truth_gate_rebuilds_exports_after_final_qa():
    result = apply_final_hosted_truth_gate(_new_report_contradiction_result())
    markdown = result["reports"]["markdown"]

    assert "Dependency / Library Ecosystem" in markdown
    assert "Dependency / Library Ecosystem — YELLOW (74/100)" in markdown
    assert "Static Analysis — YELLOW (74/100)" in markdown
    assert "PyJWT@[crypto]" not in markdown
    assert "GREEN 90" not in markdown
    assert result["maturity_signal"]["score"] == 82
