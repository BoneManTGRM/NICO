from nico.deployment_truth import build_truth_guard_status
from nico.hosted_dependency_normalization import exact_osv_dependencies, parse_requirements_normalized
from nico.report_truth_runtime_patch import apply_dependency_score_consistency


def test_pyjwt_extra_is_not_sent_to_osv_as_version_or_package_name():
    deps = parse_requirements_normalized("PyJWT[crypto]==2.13.0\n")
    exact = exact_osv_dependencies(deps)

    assert deps == [
        {
            "name": "PyJWT",
            "operator": "==",
            "version": "2.13.0",
            "ecosystem": "PyPI",
            "source": "requirements.txt",
        }
    ]
    assert exact == [{"name": "PyJWT", "version": "2.13.0", "ecosystem": "PyPI"}]
    assert "[crypto]" not in str(exact)


def test_dependency_cannot_stay_green_90_with_osv_vulnerability_records():
    result = {
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "status": "green",
                "score": 90,
                "summary": "Dependency review is green from available evidence.",
                "evidence": ["OSV returned 11 vulnerability record(s) for PyPI:PyJWT@[crypto]==2.13.0: GHSA-example."],
                "findings": [],
                "unavailable": [],
            },
            {"id": "code_audit", "label": "Code Audit", "status": "green", "score": 86},
            {"id": "secrets_review", "label": "Secrets", "status": "green", "score": 90},
            {"id": "static_analysis", "label": "Static", "status": "green", "score": 86},
            {"id": "ci_cd", "label": "CI/CD", "status": "green", "score": 95},
            {"id": "architecture_debt", "label": "Architecture", "status": "green", "score": 94},
            {"id": "velocity_complexity", "label": "Velocity", "status": "green", "score": 82},
        ]
    }

    fixed = apply_dependency_score_consistency(result)
    dependency = fixed["sections"][0]

    assert dependency["score"] == 74
    assert dependency["status"] == "yellow"
    assert "cannot claim GREEN 90" in "\n".join(dependency["findings"])
    assert "@[crypto]" not in str(dependency)
    assert "PyPI:PyJWT@2.13.0" in str(dependency)
    assert fixed["maturity_signal"]["score"] == 87


def test_truth_guard_status_exposes_live_deployment_check():
    status = build_truth_guard_status()

    assert status["status"] == "ok"
    assert status["normalized_pyjwt_extra"] is True
    assert status["sample_dependency_score_after_guard"] == 74
    assert status["sample_dependency_status_after_guard"] == "yellow"
    assert status["sample_contains_malformed_pyjwt_extra"] is False
    assert "truth-guards-" in status["truth_guard_version"]
