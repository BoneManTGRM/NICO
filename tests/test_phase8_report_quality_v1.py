from nico.phase8_report_quality_v1 import contextual_decision_title, harden_report_findings


def test_generic_complexity_title_becomes_location_specific() -> None:
    finding = {
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
    }
    assert contextual_decision_title(finding) == (
        "Page at line 177 exceeds the approved complexity threshold"
    )


def test_acceptance_criteria_are_split_and_deduplicated() -> None:
    findings = harden_report_findings(
        [
            {
                "title": "High-complexity code hotspot",
                "location": "nico/report_builder.py:462",
                "acceptance_criteria": [
                    "Target function is below threshold; Target function is below threshold; Workflow passes",
                    "Workflow passes",
                ],
            }
        ]
    )
    statements = [item["statement"] for item in findings[0]["acceptance_criteria"]]
    assert statements == ["Target function is below threshold", "Workflow passes"]


def test_non_generic_security_title_is_preserved() -> None:
    finding = {
        "title": "Unsafe XML parser configuration permits external entities",
        "location": "agent/tools.py:1253",
    }
    assert contextual_decision_title(finding) == finding["title"]
