from nico.final_report_consistency import finalize_express_result_consistency


def _section(section_id, label, score, status, evidence, findings=None, unavailable=None):
    return {
        "id": section_id,
        "label": label,
        "score": score,
        "status": status,
        "summary": f"{label} summary.",
        "evidence": evidence,
        "findings": findings or [],
        "unavailable": unavailable or [],
    }


def test_evidence_bound_static_secret_and_velocity_lifts_move_score_above_85():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "assessment_mode": "express",
            "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
            "sections": [
                _section(
                    "code_audit",
                    "Code Audit",
                    86,
                    "green",
                    ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=0."],
                ),
                _section(
                    "dependency_health",
                    "Dependency / Library Ecosystem",
                    90,
                    "green",
                    [
                        "requirements.txt found with 12 active dependency lines.",
                        "package.json found with 0 npm dependency entries across dependency sections.",
                        "apps/web/package.json found with 7 npm dependency entries across dependency sections.",
                        "Lockfile evidence found: apps/web/package-lock.json.",
                        "Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities.",
                    ],
                    unavailable=["OSV Scanner CLI execution still requires the sandboxed worker."],
                ),
                _section(
                    "secrets_review",
                    "Secrets Exposure Review",
                    88,
                    "green",
                    [
                        "Clean credential-scan and gitleaks artifacts downgraded generic token-name pattern matches as false-positive source-code signals for this run.",
                        "Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.",
                        "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                    ],
                ),
                _section(
                    "static_analysis",
                    "Static Analysis",
                    70,
                    "yellow",
                    ["Built-in static risk-pattern hits: 0."],
                    findings=["External analyzer execution remains unavailable until the sandboxed worker is expanded."],
                    unavailable=["Semgrep, Bandit, ESLint, and TypeScript checks are not yet executed by a sandboxed worker."],
                ),
                _section(
                    "ci_cd",
                    "CI/CD Analysis",
                    95,
                    "green",
                    [
                        "Workflow text includes test, lint, or build commands.",
                        "GitHub Actions workflow runs returned in assessment window: 100; success=87; non-success=13.",
                        "Current GitHub Actions scanner artifact sets were fetched and parsed successfully.",
                    ],
                ),
                _section(
                    "architecture_debt",
                    "Architecture & Technical Debt",
                    94,
                    "green",
                    ["Repository tree source-file signal count: 175."],
                    unavailable=["Full call-graph analysis requires a sandboxed worker."],
                ),
                _section(
                    "velocity_complexity",
                    "Velocity / Complexity",
                    73,
                    "yellow",
                    [
                        "Commit velocity: 100 commits over 180 days (3.89/week).",
                        "Pull request traceability ratio: 100 PRs / 100 commits = 1.0.",
                        "Source-file footprint from recursive tree: 175 files.",
                    ],
                    findings=["Source-file footprint is large enough to require deeper complexity analysis before final client claims."],
                ),
            ],
            "reports": {},
        }
    )

    scores = {item["id"]: item["score"] for item in result["sections"]}

    assert scores["secrets_review"] >= 90
    assert scores["static_analysis"] >= 86
    assert scores["velocity_complexity"] >= 90
    assert result["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert result["maturity_signal"]["score"] >= 90


def test_static_lift_does_not_ignore_real_blocking_findings():
    result = finalize_express_result_consistency(
        {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "sections": [
                _section(
                    "static_analysis",
                    "Static Analysis",
                    70,
                    "yellow",
                    ["Built-in static risk-pattern hits: 0."],
                    findings=["src/app.py:1: eval usage detected."],
                ),
                _section("ci_cd", "CI/CD Analysis", 95, "green", ["Workflow text includes test, lint, or build commands."]),
            ],
            "reports": {},
        }
    )

    scores = {item["id"]: item["score"] for item in result["sections"]}

    assert scores["static_analysis"] == 70
