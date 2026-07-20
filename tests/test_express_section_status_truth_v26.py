from __future__ import annotations

from nico.express_section_status_truth_v26 import reconcile_section_status_truth


def test_green_section_with_unresolved_analyzer_evidence_becomes_review_limited() -> None:
    result = reconcile_section_status_truth(
        {
            "sections": [
                {
                    "id": "secrets_review",
                    "label": "Secrets Exposure Review",
                    "score": 92,
                    "status": "green",
                    "findings": ["gitleaks ended with status timeout; output requires human review."],
                    "unavailable": [],
                }
            ]
        }
    )
    section = result["sections"][0]
    assert section["status"] == "yellow"
    assert section["display_status"] == "YELLOW · REVIEW LIMITED"
    assert "status_reason" in section


def test_clean_green_section_remains_green() -> None:
    result = reconcile_section_status_truth(
        {
            "sections": [
                {
                    "id": "dependency_health",
                    "label": "Dependency Health",
                    "score": 90,
                    "status": "green",
                    "findings": [],
                    "unavailable": [],
                }
            ]
        }
    )
    assert result["sections"][0]["status"] == "green"


def test_scanner_worker_and_client_acceptance_are_not_scored() -> None:
    result = reconcile_section_status_truth(
        {
            "sections": [
                {
                    "id": "scanner_worker_evidence",
                    "label": "Scanner Worker Evidence",
                    "score": 27,
                    "status": "red",
                    "findings": [],
                    "unavailable": [],
                },
                {
                    "id": "client_acceptance",
                    "label": "Client / Human Acceptance",
                    "score": 0,
                    "status": "red",
                    "findings": [],
                    "unavailable": ["No approval record was found."],
                },
            ]
        }
    )
    scanner, acceptance = result["sections"]
    assert scanner["status"] == "SUPPLEMENTAL"
    assert scanner["display_status"] == "SUPPLEMENTAL · NOT SCORED"
    assert scanner["score"] is None
    assert acceptance["status"] == "gray"
    assert acceptance["display_status"] == "GRAY · NOT SCORED"
    assert acceptance["score"] is None


def test_input_is_not_mutated() -> None:
    source = {
        "sections": [
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 90,
                "status": "green",
                "findings": ["bandit failed and requires human review."],
                "unavailable": [],
            }
        ]
    }
    result = reconcile_section_status_truth(source)
    assert source["sections"][0]["status"] == "green"
    assert result["sections"][0]["status"] == "yellow"
