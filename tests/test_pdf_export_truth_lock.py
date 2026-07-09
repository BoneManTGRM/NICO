from nico.client_acceptance import attach_client_acceptance_gate


def _pdf_contradiction_result():
    return {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T00:58:46Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "coverage_targets": {
            "express_technical_health_assessment": {"current": "65-75%", "target": "90-95%"},
        },
        "maturity_signal": {"level": "Senior", "score": 89},
        "maturity_semaphore": {},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "status": "green",
                "score": 86,
                "summary": "Code audit uses recent commit/PR metadata plus hosted source-pattern review.",
                "evidence": ["Commits returned since 2026-01-10T00:58:18Z: 100."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from available manifest, lockfile, and OSV API evidence, but final scanner-clean dependency status is not claimed.",
                "evidence": [
                    "requirements.txt found with 13 active dependency lines.",
                    "Lockfile evidence found: apps/web/package-lock.json.",
                    "OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-752w-5fwx-jx9f, GHSA-993g-76c3-p5m4.",
                ],
                "findings": [
                    "Dependency evidence status: OSV API completed_with_findings; final scanner-clean status is not claimed without pip-audit/npm audit/OSV Scanner artifacts for this run."
                ],
                "unavailable": [
                    "Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner.",
                    "Full pip-audit, npm audit, and OSV Scanner CLI artifacts are still required before claiming final scanner-clean dependency status.",
                ],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "status": "green",
                "score": 90,
                "summary": "Secrets review found no high-confidence credential findings in attached credential-scan/gitleaks artifacts, but full git-history secret coverage is not verified for this report run.",
                "evidence": [
                    "Parsed credential-scan and gitleaks git-history artifacts reported zero credential findings.",
                    "Secrets evidence status: no high-confidence credential findings in attached artifacts, but full git-history secret coverage is not verified for this run.",
                ],
                "findings": [],
                "unavailable": [
                    "Scanner-worker secret tools unavailable: gitleaks, trufflehog.",
                    "Full git-history secret coverage was not verified for this report run; attached credential artifacts and live full-history scanner proof are separate evidence sources.",
                ],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "status": "green",
                "score": 86,
                "summary": "Static analysis uses clean built-in pattern checks plus CI-backed evidence, but Bandit artifact findings require explicit triage; the green score is not a final scanner-clean claim.",
                "evidence": ["Built-in static risk-pattern hits: 0."],
                "findings": [
                    "Parsed Bandit artifact reported 53 finding(s).",
                    "Bandit triage summary: total=53, blocker_count=0, review_required_count=53, candidate_false_positive_count=0; score impact=needs_human_review until rule-level triage is attached and approved.",
                ],
                "unavailable": [
                    "Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript.",
                    "Live scanner-worker artifacts for Semgrep, Bandit, ESLint, and TypeScript were not attached or verified for this report run.",
                ],
            },
            {
                "id": "ci_cd",
                "label": "CI/CD Analysis",
                "status": "green",
                "score": 95,
                "summary": "CI/CD maturity is based on workflow configuration and available workflow run history.",
                "evidence": ["GitHub Actions workflow runs returned in assessment window: 100; success=87; non-success=13."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "status": "green",
                "score": 94,
                "summary": "Architecture review uses repository layout and source-tree signals.",
                "evidence": ["Repository root contains nico/."],
                "findings": [],
                "unavailable": ["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker."],
            },
            {
                "id": "velocity_complexity",
                "label": "Velocity / Complexity",
                "status": "green",
                "score": 82,
                "summary": "Work-vs-expected signal uses velocity, PR traceability, source footprint, available supporting evidence, disclosed findings, and explicit missing runtime artifacts; it does not claim final release-readiness.",
                "evidence": [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                ],
                "findings": ["Source-file footprint is large enough to require deeper complexity analysis before final client claims."],
                "unavailable": [
                    "Release-readiness lift not applied because required final-clean evidence is incomplete: dependency_scanner_clean_artifacts_attached, dependency_no_osv_vulnerabilities, static_analysis_no_review_findings"
                ],
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
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
        "reports": {
            "markdown": "# stale report\n\nScore mix: green=7, yellow=0, red=0, unavailable=1.",
            "html": "<p>stale report</p>",
            "pdf_base64": "stale-pdf",
        },
    }


def test_client_acceptance_applies_final_truth_gate_before_live_pdf_return():
    result = attach_client_acceptance_gate(_pdf_contradiction_result())
    sections = {item["id"]: item for item in result["sections"] if isinstance(item, dict) and item.get("id")}

    assert result["trust_report_display"]["trust_level"] in {"Review-limited", "Draft only"}
    assert result["client_delivery_status"] in {"Human Review Required", "Draft only — not client-ready"}
    assert result["maturity_signal"]["score"] < 89
    assert sections["dependency_health"]["status"] == "yellow"
    assert sections["static_analysis"]["status"] == "yellow"
    assert sections["secrets_review"]["status"] == "yellow"
    assert sections["velocity_complexity"]["status"] == "yellow"
    assert result["export_truth_gate"]["status"] == "passed"
    assert result["client_acceptance"]["client_delivery_allowed"] is False
    assert "Trust & Client Readiness" in result["reports"]["markdown"]
    assert "Trust Level:" in result["reports"]["markdown"]
    assert "green=7, yellow=0" not in result["reports"]["markdown"]
    assert result["reports"].get("pdf_base64") and result["reports"].get("pdf_base64") != "stale-pdf"
