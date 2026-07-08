from nico.hosted_truth_delivery_gate import apply_final_hosted_truth_gate
from nico.trust_engine import apply_strict_trust_engine


def _contradictory_green_report():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T23:01:38Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "executive_summary": "NICO completed an authorized hosted Express Technical Health Assessment.",
        "maturity_signal": {"level": "Senior", "score": 89},
        "maturity_semaphore": {},
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
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "status": "green",
                "score": 90,
                "summary": "Secrets review found no high-confidence credential findings, but full git-history secret coverage is not verified for this report run.",
                "evidence": ["Parsed credential-scan and gitleaks git-history artifacts reported zero credential findings."],
                "findings": [],
                "unavailable": ["Scanner-worker secret tools unavailable: gitleaks, trufflehog.", "Full git-history secret coverage was not verified for this report run."],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 86,
                "summary": "Static analysis uses clean built-in pattern checks plus CI-backed evidence, but Bandit artifact findings require explicit triage; the green score is not a final scanner-clean claim.",
                "evidence": ["Built-in static risk-pattern hits: 0."],
                "findings": [
                    "Parsed Bandit artifact reported 50 finding(s).",
                    "Bandit triage summary: total=50, blocker_count=0, review_required_count=50, candidate_false_positive_count=0; score impact=needs_human_review until rule-level triage is attached and approved.",
                ],
                "unavailable": ["Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript."],
            },
            {"id": "ci_cd", "label": "CI/CD Analysis", "status": "green", "score": 95, "summary": "CI/CD maturity.", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture & Technical Debt", "status": "green", "score": 94, "summary": "Architecture.", "evidence": [], "findings": [], "unavailable": []},
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "status": "green",
                "score": 82,
                "summary": "Work-vs-expected signal uses velocity and explicit missing runtime artifacts; it does not claim final release-readiness.",
                "evidence": ["Source-file footprint is large enough to require deeper complexity analysis before final client claims."],
                "findings": ["Source-file footprint is large enough to require deeper complexity analysis before final client claims."],
                "unavailable": ["Release-readiness lift not applied because required final-clean evidence is incomplete: dependency_scanner_clean_artifacts_attached, dependency_no_osv_vulnerabilities, static_analysis_no_review_findings"],
            },
            {"id": "client_acceptance", "label": "Client / Human Acceptance", "status": "gray", "score": 0, "summary": "Acceptance.", "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings": [],
        "repairs": [],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {"markdown": "", "html": "", "pdf_base64": ""},
    }


def test_strict_trust_engine_downgrades_green_contradictions():
    result = apply_strict_trust_engine(_contradictory_green_report())
    sections = {item["id"]: item for item in result["sections"]}

    assert sections["dependency_health"]["status"] == "yellow"
    assert sections["dependency_health"]["score"] == 74
    assert sections["static_analysis"]["status"] == "yellow"
    assert sections["static_analysis"]["score"] == 74
    assert sections["secrets_review"]["status"] == "yellow"
    assert sections["secrets_review"]["score"] == 74
    assert sections["velocity_complexity"]["status"] == "yellow"
    assert sections["velocity_complexity"]["score"] == 74
    assert result["maturity_signal"]["score"] == 82
    assert result["trust_level"] == "Review-limited"
    assert len(result["trust_engine"]["violations"]) == 4


def test_final_hosted_gate_exports_strict_trust_caps():
    result = apply_final_hosted_truth_gate(_contradictory_green_report())
    markdown = result["reports"]["markdown"]

    assert result["trust_engine"]["trust_level"] == "Review-limited"
    assert result["maturity_signal"]["score"] == 82
    assert "Dependency / Library Ecosystem — YELLOW (74/100)" in markdown
    assert "Static Analysis — YELLOW (74/100)" in markdown
    assert "Secrets Exposure Review — YELLOW (74/100)" in markdown
    assert "Velocity / Complexity — YELLOW (74/100)" in markdown
    assert "PyJWT@[crypto]" not in markdown
