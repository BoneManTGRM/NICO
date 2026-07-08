from nico.final_report_consistency import finalize_express_result_consistency
from nico.service_workflows import COVERAGE_TARGETS


def _base_result(**overrides):
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-07T11:20:00Z",
        "client_name": "",
        "project_name": "NICO",
        "assessment_mode": "express",
        "coverage_targets": COVERAGE_TARGETS,
        "executive_summary": "NICO completed an assessment. The current maturity signal is Mid (71/100).",
        "maturity_signal": {"level": "Mid", "score": 77, "summary": "Stale pre-final score."},
        "maturity_semaphore": {"Code Audit": "green"},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 80,
                "status": "green",
                "summary": "Code audit uses final evidence.",
                "evidence": ["Commits reviewed."],
                "findings": [],
                "unavailable": [],
            }
        ],
        "findings": [],
        "quick_wins": ["Review evidence."],
        "medium_term_plan": ["Keep report outputs consistent."],
        "resourcing_recommendation": ["Human review."],
        "risk_register": ["Stale report fields can mislead."],
        "verification_checklist": ["Check one final score."],
        "reports": {
            "markdown": "old markdown says 71/100",
            "html": "old html says 71/100",
            "pdf_base64": "old-pdf-placeholder",
        },
    }
    result.update(overrides)
    return result


def test_final_consistency_rebuilds_summary_and_reports_from_final_sections():
    result = finalize_express_result_consistency(_base_result())
    assert "71/100" not in result["executive_summary"]
    assert "80/100" in result["executive_summary"]
    assert result["score_source_of_truth"]["field"] == "maturity_signal"
    assert result["score_source_of_truth"]["score"] == 80
    assert result["maturity_signal"]["score"] == 80
    assert "71/100" not in result["reports"]["markdown"]
    assert "80/100" in result["reports"]["markdown"]
    assert "71/100" not in result["reports"]["html"]
    assert "80/100" in result["reports"]["html"]


def test_final_consistency_preserves_blocked_results_without_rewriting():
    blocked = {"status": "blocked", "executive_summary": "blocked old 71/100"}
    result = finalize_express_result_consistency(blocked)
    assert result is blocked
    assert result["executive_summary"] == "blocked old 71/100"


def test_final_consistency_rebuilds_es_mx_reports_from_final_sections():
    result = finalize_express_result_consistency(_base_result(assessment_mode="express_es_mx"))
    assert result["score_source_of_truth"]["score"] == 80
    assert result["maturity_signal"]["score"] == 80
    assert "71/100" not in result["executive_summary"]
    assert "80/100" in result["executive_summary"]
    assert "71/100" not in result["reports"]["markdown"]
    assert "Puntaje: **80/100**" in result["reports"]["markdown"]
    assert 'lang="es-MX"' in result["reports"]["html"]


def _scored_section(section_id, label, score, summary, evidence=None, findings=None, unavailable=None):
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": "green" if score >= 75 else "yellow",
        "summary": summary,
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def _pdf_regression_sections():
    return [
        _scored_section(
            "code_audit",
            "Code Audit",
            86,
            "Code audit uses recent commit/PR metadata plus hosted source-pattern review.",
            [
                "Commits returned since 2026-01-09T12:58:39Z: 100.",
                "Pull requests updated in the assessment window: 100; merged=90; open=6.",
                "Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=0, test-path signals=2.",
            ],
        ),
        _scored_section(
            "dependency_health",
            "Dependency / Library Ecosystem",
            90,
            "Dependency review uses manifest evidence, JavaScript lockfile evidence, OSV evidence, and parsed audit artifacts when available while keeping scanner-worker limitations disclosed.",
            [
                "requirements.txt found with 13 active dependency lines.",
                "package.json found with 0 npm dependency entries across dependency sections.",
                "apps/web/package.json found with 7 npm dependency entries across dependency sections.",
                "Lockfile evidence found: apps/web/package-lock.json.",
                "OSV returned 4 vulnerability record(s) for PyPI:uvicorn[standard]==0.50.2: GHSA-33c7-2mpw-hg34.",
            ],
            unavailable=[
                "pip-audit, npm audit, and OSV Scanner CLI execution are not yet run inside a sandboxed worker; hosted review uses manifest parsing plus OSV API where possible.",
                "Scanner-worker dependency tools unavailable: pip-audit, npm-audit, osv-scanner.",
            ],
        ),
        _scored_section(
            "secrets_review",
            "Secrets Exposure Review",
            90,
            "Secrets review uses built-in masked secret-pattern detection plus parsed credential-scan and gitleaks artifacts when available; full git-history limits remain disclosed.",
            [
                "Clean credential-scan and gitleaks artifacts downgraded generic token-name pattern matches as false-positive source-code signals for this run.",
                "Parsed credential-scan artifact reported zero high-confidence credential findings.",
                "Secrets evidence classification: parsed credential-scan and gitleaks artifacts reported zero high-confidence credential findings for this run.",
            ],
            unavailable=[
                "Full git-history secret scanning requires a sandboxed worker with gitleaks or trufflehog; hosted mode currently scans fetched file contents only.",
                "Scanner-worker secret tools unavailable: gitleaks, trufflehog.",
            ],
        ),
        _scored_section(
            "static_analysis",
            "Static Analysis",
            86,
            "Static analysis uses clean built-in pattern checks plus green CI/CD or lint/typecheck/build evidence, while keeping unavailable external scanner-worker execution disclosed.",
            ["Built-in static risk-pattern hits: 0."],
            findings=["Parsed Bandit artifact reported 50 finding(s)."],
            unavailable=[
                "Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker in hosted mode; this section uses built-in pattern checks only.",
                "Scanner-worker static tools unavailable: bandit, semgrep, eslint, typescript.",
                "External Semgrep/Bandit scanner-worker execution remains unavailable; CI-backed evidence is counted separately from full scanner-worker proof.",
            ],
        ),
        _scored_section(
            "ci_cd",
            "CI/CD Analysis",
            95,
            "CI/CD maturity is based on workflow configuration, automation keywords, permissions evidence, and available workflow run history.",
            [
                "Workflow text includes test, lint, or build commands.",
                "GitHub Actions workflow runs returned in assessment window: 100; success=96; non-success=2.",
            ],
        ),
        _scored_section(
            "architecture_debt",
            "Architecture & Technical Debt",
            94,
            "Architecture review uses repository layout, source-tree signals, documentation evidence, test structure, and deployment manifests.",
            ["Repository root contains nico/."],
            unavailable=["Full call-graph analysis and cyclomatic complexity scoring require a sandboxed worker that checks out the repo and runs language-specific analyzers."],
        ),
        _scored_section(
            "velocity_complexity",
            "Velocity / Complexity",
            90,
            "Work-vs-expected signal uses velocity, PR traceability, source footprint, and final release-readiness evidence from clean CI/security/dependency artifacts.",
            [
                "Commit velocity: 100 commits over 180 days (3.89/week).",
                "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                "Source-file footprint from recursive tree: 211 files.",
            ],
            findings=["Source-file footprint is large enough to require deeper complexity analysis before final client claims."],
            unavailable=[
                "Precise story-point expectation, reviewer seniority, and business-value mapping require stakeholder context and human review.",
            ],
        ),
        {
            "id": "client_acceptance",
            "label": "Client / Human Acceptance",
            "score": 0,
            "status": "gray",
            "summary": "Final report acceptance is not scored until an approved same-project review record exists.",
            "evidence": ["Client/human acceptance evidence unavailable."],
            "findings": ["Client/human acceptance evidence is unavailable for final delivery scoring."],
            "unavailable": ["No approved final report/client acceptance approval record was found for this project."],
        },
    ]


def test_pdf_regression_score_can_stay_90_but_report_text_is_not_contradictory():
    result = finalize_express_result_consistency(
        _base_result(
            maturity_signal={"level": "Senior", "score": 90, "summary": "Original report score."},
            sections=_pdf_regression_sections(),
            medium_term_plan=[
                "Add a sandboxed worker that checks out authorized repositories and runs pip-audit, npm audit, gitleaks/trufflehog, Semgrep, Bandit, ESLint, and coverage tools.",
                "Add authenticated GitHub App installation flow for private authorized repositories and richer PR/review evidence.",
                "Expand Mid assessment modules for QA evidence intake, iOS/Android parity checklists, stakeholder notes, and 6-month roadmap generation.",
                "Add Retainer Ops modules for weekly status, monthly strategy, backlog health, release readiness, and approval-gated issue creation.",
            ],
        )
    )

    markdown = result["reports"]["markdown"]
    assert result["maturity_signal"]["score"] == 90
    assert "Add a sandboxed worker" not in markdown
    assert "Add authenticated GitHub App installation flow" not in markdown
    assert "Expand Mid assessment modules" not in markdown
    assert "Add Retainer Ops modules" not in markdown
    assert "Run and attach verified scanner-worker artifacts" in markdown
    assert "Dependency evidence status: OSV API completed_with_findings" in markdown
    assert "final scanner-clean status is not claimed" in markdown
    assert "full git-history secret coverage is not verified for this run" in markdown
    assert "Bandit evidence source distinction" in markdown
    assert "Bandit triage summary: total=50" in markdown
    assert "review_required_count=50" in markdown
    assert "score impact=needs_human_review" in markdown
    assert "old markdown says 71/100" not in markdown
