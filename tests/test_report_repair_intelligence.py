from __future__ import annotations

from nico.report_repair_intelligence import (
    build_report_repair_intelligence,
    render_repair_intelligence_markdown,
)


def test_structured_findings_are_prioritized_and_report_only() -> None:
    payload = {
        "sections": [
            {
                "id": "static_analysis",
                "findings": ["A lower-priority maintainability note."],
            }
        ]
    }
    structured = [
        {
            "code": "python_shell_true",
            "title": "shell=True in worker",
            "severity": "high",
            "confidence": 0.95,
            "category": "python_shell_true",
            "evidence": ["worker.py:20 shell=True"],
            "affected_files": ["worker.py"],
            "business_impact": "Command injection could expose the service.",
            "technical_impact": "Shell parsing receives a dynamic command.",
            "recommendation": "Use an argument list with shell disabled.",
            "verification_method": "Run command-injection tests and static analysis.",
            "exploitability": "high",
        },
        {
            "code": "documentation_drift",
            "title": "Documentation is stale",
            "severity": "medium",
            "confidence": 0.9,
            "category": "documentation_drift",
            "evidence": ["PROJECT_STATUS points to an old SHA"],
            "affected_files": ["docs/PROJECT_STATUS.md"],
            "business_impact": "Operators may use old release evidence.",
            "technical_impact": "Documented SHA differs from current main.",
            "recommendation": "Update from verified release evidence.",
            "verification_method": "Compare the document to deployment proof.",
            "exploitability": "low",
        },
    ]

    result = build_report_repair_intelligence(payload, structured_findings=structured)

    assert result["status"] == "complete"
    assert result["mode"] == "report_only"
    assert result["priority_model"] == "calibrated_weighted_v2"
    assert result["candidate_count"] == 3
    assert result["candidates"][0]["title"] == "shell=True in worker"
    assert result["candidates"][0]["code_suggestion"]["status"] == "available"
    assert result["candidates"][0]["automatic_application_allowed"] is False
    assert result["candidates"][0]["human_review_required"] is True
    assert result["policy"]["automatic_application_allowed"] is False
    assert result["candidates"][0]["priority_score"] > result["candidates"][1]["priority_score"]
    assert len({item["priority_score"] for item in result["candidates"]}) > 1
    assert all(0 < item["priority_score"] <= 100 for item in result["candidates"])
    assert all(item["effort"] in {"low", "medium", "high"} for item in result["candidates"])


def test_unknown_generic_finding_does_not_get_fabricated_code() -> None:
    payload = {
        "sections": [
            {
                "id": "architecture_debt",
                "findings": ["The ownership model needs stakeholder review."],
            }
        ]
    }

    result = build_report_repair_intelligence(payload)
    candidate = result["candidates"][0]

    assert candidate["code_suggestion"]["status"] == "unavailable"
    assert candidate["verified_fix"] is False
    assert candidate["rollback_plan"]


def test_markdown_contains_code_effort_and_safety_boundary() -> None:
    intelligence = build_report_repair_intelligence(
        {"sections": []},
        structured_findings=[
            {
                "code": "unsafe_yaml_load",
                "title": "Unsafe YAML load",
                "severity": "high",
                "confidence": 0.95,
                "category": "unsafe_yaml_load",
                "evidence": ["config.py:10 yaml.load(data)"],
                "affected_files": ["config.py"],
                "business_impact": "Unsafe deserialization risk.",
                "technical_impact": "yaml.load is used without a safe loader.",
                "recommendation": "Use yaml.safe_load and validate schema.",
                "verification_method": "Run malicious YAML regression tests.",
                "exploitability": "medium",
            }
        ],
    )

    markdown = "\n".join(render_repair_intelligence_markdown(intelligence))

    assert "Report-only safety boundary" in markdown
    assert "yaml.safe_load" in markdown
    assert "not applied" in markdown
    assert "Verification required" in markdown
    assert "Effort:" in markdown


def test_repository_size_is_advisory_not_a_ranked_defect() -> None:
    result = build_report_repair_intelligence(
        {
            "sections": [
                {
                    "id": "architecture_debt",
                    "findings": [
                        "Source-file footprint is large and increases review scope; repository size is not scored as technical debt by itself.",
                        "Total source LOC is high for an Express review and increases review depth; size alone does not reduce maintainability score.",
                    ],
                }
            ]
        }
    )

    assert result["candidate_count"] == 0
    assert len(result["advisories"]) == 2
    assert result["portfolio"]["advisory_count"] == 2
    assert all("not ranked as a defect" in item["reason"].lower() for item in result["advisories"])


def test_complexity_signals_are_consolidated_into_one_actionable_candidate() -> None:
    result = build_report_repair_intelligence(
        {
            "sections": [
                {
                    "id": "architecture_debt",
                    "findings": [
                        "At least one function has very high cyclomatic complexity and should be decomposed or tested heavily.",
                        "Function-level complexity risk is concentrated in 258 source file(s).",
                        "Complexity and high churn overlap in 38 delivery hotspot file(s).",
                        "Large-file and complexity risk overlap in 16 source file(s).",
                        "Complexity hotspot: nico/mid_review_enforcement.py score=517.65, loc=800, max_function_cyclomatic=None, density=None, churn=899.",
                        "Complexity hotspot: nico/assessment_recovery.py score=442.02, loc=890, max_function_cyclomatic=None, density=None, churn=969.",
                    ],
                }
            ]
        }
    )

    assert result["candidate_count"] == 1
    candidate = result["candidates"][0]
    assert candidate["title"] == "Complexity concentration and churn create elevated change risk"
    assert candidate["severity"] == "high"
    assert candidate["effort"] == "high"
    assert candidate["affected_files"] == [
        "nico/mid_review_enforcement.py",
        "nico/assessment_recovery.py",
    ]
    assert len(candidate["evidence"]) == 6
    assert "None" not in " ".join(candidate["evidence"])


def test_low_medium_and_high_findings_do_not_all_saturate_at_100() -> None:
    result = build_report_repair_intelligence(
        {"sections": []},
        structured_findings=[
            {
                "code": "runtime_patch_surface",
                "title": "Large runtime patch and compatibility surface creates import-order fragility",
                "severity": "high",
                "confidence": 0.95,
                "category": "runtime_patch_surface",
                "business_impact": "Import regressions increase debugging cost.",
                "technical_impact": "Installer order is difficult to reason about.",
                "recommendation": "Consolidate installers in stages.",
                "verification_method": "Run import-order tests.",
                "exploitability": "low",
            },
            {
                "code": "documentation_drift",
                "title": "Documented deployment requires provider verification",
                "severity": "medium",
                "confidence": 0.8,
                "category": "documentation_drift",
                "business_impact": "Operators may use the wrong version.",
                "technical_impact": "The release claim is not provider-bound.",
                "recommendation": "Verify deployment identity.",
                "verification_method": "Compare provider proof.",
                "exploitability": "low",
            },
            {
                "code": "delivery_reliability",
                "title": "Historical workflow reliability includes non-success runs",
                "severity": "low",
                "confidence": 0.72,
                "category": "delivery_reliability",
                "business_impact": "Retries consume engineering time.",
                "technical_impact": "Some runs did not succeed.",
                "recommendation": "Classify repeat failures.",
                "verification_method": "Review the next 20 runs.",
                "exploitability": "low",
            },
        ],
    )

    scores = [item["priority_score"] for item in result["candidates"]]
    levels = [(item["tgrm"] or {}).get("level") for item in result["candidates"]]
    assert scores == sorted(scores, reverse=True)
    assert scores[0] < 100
    assert len(set(scores)) == 3
    assert len(set(levels)) >= 2
