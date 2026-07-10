from nico.final_report_consistency import finalize_express_result_consistency


def _section(section_id, label, score, evidence=None, findings=None):
    return {
        "id": section_id,
        "label": label,
        "status": "green",
        "score": score,
        "summary": f"{label} summary",
        "evidence": evidence or [],
        "findings": findings or [],
        "unavailable": [],
    }


def test_release_readiness_lifts_velocity_when_all_final_evidence_is_present():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "executive_summary": "old 89",
        "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
        "sections": [
            _section(
                "code_audit",
                "Code Audit",
                86,
                ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2."],
            ),
            _section("dependency_health", "Dependency / Library Ecosystem", 88, ["Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities."]),
            _section(
                "secrets_review",
                "Secrets Exposure Review",
                93,
                [
                    "Parsed credential-scan, gitleaks, and trufflehog full-history artifacts reported zero credential findings.",
                    "Scanner-worker secret tools completed: gitleaks, trufflehog.",
                ],
            ),
            _section("static_analysis", "Static Analysis", 86, ["Parsed Bandit and Semgrep artifacts reported zero scanner findings."]),
            _section("ci_cd", "CI/CD Analysis", 95, ["Current GitHub Actions scanner artifact sets were fetched and parsed successfully."]),
            _section("architecture_debt", "Architecture & Technical Debt", 94, ["Repository root contains nico/."]),
            _section(
                "velocity_complexity",
                "Velocity / Complexity",
                83,
                [
                    "Commit velocity: 100 commits over 180 days (3.89/week).",
                    "Pull request traceability ratio: 51 PRs / 100 commits = 0.51.",
                    "Source-file footprint from recursive tree: 101 files.",
                ],
            ),
        ],
        "reports": {},
    }

    finalized = finalize_express_result_consistency(result)
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert velocity["score"] == 90
    assert finalized["release_readiness"]["status"] == "provisionally_ready_for_human_review"
    assert finalized["maturity_signal"]["score"] == 90
    assert "Release-readiness evidence" in "\n".join(velocity["evidence"])
    assert "Why not higher" in "\n".join(velocity["evidence"])


def test_release_readiness_does_not_lift_velocity_when_secret_artifact_is_missing():
    result = {
        "status": "complete",
        "repository": "BoneManTGRM/NICO",
        "executive_summary": "old",
        "complexity_engine": {"status": "complete", "hotspot_risk": "low"},
        "sections": [
            _section("code_audit", "Code Audit", 86, ["Text files inspected for code-risk markers: actionable TODO/FIXME/security markers=0, risky pattern hits=2, test-path signals=2."]),
            _section("dependency_health", "Dependency / Library Ecosystem", 88, ["Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities."]),
            _section("secrets_review", "Secrets Exposure Review", 93, ["Credential scan was clean but no gitleaks artifact was parsed."]),
            _section("static_analysis", "Static Analysis", 86, ["Parsed Bandit and Semgrep artifacts reported zero scanner findings."]),
            _section("ci_cd", "CI/CD Analysis", 95, ["Current GitHub Actions scanner artifact sets were fetched and parsed successfully."]),
            _section("architecture_debt", "Architecture & Technical Debt", 94, ["Repository root contains nico/."]),
            _section("velocity_complexity", "Velocity / Complexity", 83, ["Commit velocity: 100 commits over 180 days (3.89/week).", "Pull request traceability ratio: 51 PRs / 100 commits = 0.51."]),
        ],
        "reports": {},
    }

    finalized = finalize_express_result_consistency(result)
    velocity = next(section for section in finalized["sections"] if section["id"] == "velocity_complexity")

    assert velocity["score"] == 84
    assert finalized["release_readiness"]["status"] == "evidence_incomplete"
    assert "secret_evidence_clean" in finalized["release_readiness"]["missing_signals"]
