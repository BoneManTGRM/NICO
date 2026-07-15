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
    assert result["candidate_count"] == 3
    assert result["candidates"][0]["title"] == "shell=True in worker"
    assert result["candidates"][0]["code_suggestion"]["status"] == "available"
    assert result["candidates"][0]["automatic_application_allowed"] is False
    assert result["candidates"][0]["human_review_required"] is True
    assert result["policy"]["automatic_application_allowed"] is False


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


def test_markdown_contains_code_and_safety_boundary() -> None:
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
