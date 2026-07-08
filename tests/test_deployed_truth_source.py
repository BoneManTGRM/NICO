from nico.deployed_truth_source import (
    apply_deployed_truth_invariants,
    exact_osv_dependencies,
    parse_requirements_normalized,
)


def test_deployed_truth_normalizes_python_extras_for_osv_queries():
    deps = parse_requirements_normalized("PyJWT[crypto]==2.13.0\nuvicorn[standard]==0.50.2\npsycopg>=3.2,<4\n")
    exact = exact_osv_dependencies(deps)

    assert {item["name"] for item in exact} == {"PyJWT", "uvicorn"}
    assert {item["version"] for item in exact} == {"2.13.0", "0.50.2"}
    assert "[crypto]" not in str(exact)
    assert "[standard]" not in str(exact)
    assert "psycopg" not in {item["name"] for item in exact}


def test_deployed_truth_discards_malformed_osv_evidence_and_caps_dependency_score():
    result = {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T19:23:51Z",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 90,
                "status": "green",
                "summary": "Dependency review is green from available manifest, lockfile, and OSV API evidence.",
                "evidence": [
                    "requirements.txt found with 13 active dependency lines.",
                    "Lockfile evidence found: apps/web/package-lock.json.",
                    "OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-example.",
                    "Parsed GitHub Actions pip-audit and npm-audit artifacts reported zero dependency vulnerabilities.",
                ],
                "findings": [
                    "Dependency evidence status: OSV API completed_with_findings; final scanner-clean status is not claimed without pip-audit/npm audit/OSV Scanner artifacts for this run."
                ],
                "unavailable": [],
            },
            {"id": "code_audit", "label": "Code Audit", "score": 86, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 90, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static", "score": 86, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD", "score": 95, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture", "score": 94, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity", "score": 82, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "client_acceptance", "label": "Client", "score": 0, "status": "gray", "summary": "", "evidence": [], "findings": [], "unavailable": []},
        ],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
    }

    fixed = apply_deployed_truth_invariants(result)
    dependency = fixed["sections"][0]
    markdown = fixed["reports"]["markdown"]

    assert dependency["score"] == 86
    assert dependency["status"] == "green"
    assert "Malformed OSV dependency evidence was discarded" in "\n".join(dependency["findings"])
    assert "PyJWT@[crypto]" not in markdown
    assert fixed["maturity_signal"]["score"] == 88


def test_deployed_truth_caps_real_normalized_osv_findings_to_yellow():
    result = {
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-08T19:23:51Z",
        "coverage_targets": {"express_technical_health_assessment": {"target": "90-95%"}},
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 90,
                "status": "green",
                "summary": "Dependency review is green.",
                "evidence": ["OSV returned 1 vulnerability record(s) for PyPI:package@1.0.0: GHSA-real."],
                "findings": [],
                "unavailable": [],
            },
            {"id": "code_audit", "label": "Code Audit", "score": 86, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "secrets_review", "label": "Secrets", "score": 90, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "static_analysis", "label": "Static", "score": 86, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "ci_cd", "label": "CI/CD", "score": 95, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "architecture_debt", "label": "Architecture", "score": 94, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "label": "Velocity", "score": 82, "status": "green", "summary": "", "evidence": [], "findings": [], "unavailable": []},
        ],
        "quick_wins": [],
        "medium_term_plan": [],
        "resourcing_recommendation": [],
        "risk_register": [],
        "verification_checklist": [],
    }

    fixed = apply_deployed_truth_invariants(result)
    dependency = fixed["sections"][0]

    assert dependency["score"] == 74
    assert dependency["status"] == "yellow"
    assert fixed["maturity_signal"]["score"] == 87
