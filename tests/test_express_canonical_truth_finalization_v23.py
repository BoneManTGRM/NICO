from __future__ import annotations

from nico.express_canonical_truth_finalization_v23 import finalize_express_truth


def _result() -> dict:
    return {
        "sections": [
            {
                "id": "dependency_health",
                "label": "Dependency / Library Ecosystem",
                "score": 90,
                "status": "green",
                "confidence": "high",
                "evidence": ["OSV returned no vulnerability records for 12 pinned dependency queries."],
                "findings": ["osv-scanner returned 1 finding(s) requiring human triage."],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 92,
                "status": "green",
                "confidence": "high",
                "evidence": ["Clean credential-scan and gitleaks artifacts were retained.", "trufflehog artifacts reported zero credential findings."],
                "findings": ["gitleaks ended with status timeout.", "trufflehog returned 1 finding requiring human triage."],
                "unavailable": [],
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 90,
                "status": "green",
                "confidence": "high",
                "evidence": ["Bandit artifacts are complete for this report run."],
                "findings": ["bandit ended with status failed."],
                "unavailable": ["eslint was unavailable."],
            },
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": 27,
                "presented_score": 6,
                "status": "red",
                "confidence": "review-limited",
                "evidence": ["gitleaks status=timeout; findings=1"],
                "findings": ["gitleaks returned timeout."],
                "unavailable": [],
            },
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "status": "green",
                "confidence": "high",
                "evidence": ["No vulnerabilities found."],
                "findings": ["No vulnerabilities found."],
                "unavailable": [],
            },
        ],
        "repair_intelligence": {
            "candidates": [
                {"title": "TODO/FIXME/security-note markers require triage", "affected_files": []},
                {"title": "Complexity hotspot", "affected_files": ["nico/a.py"]},
            ]
        },
        "finding_dossiers": [
            {"evidence": ["README.md is present and can support onboarding.", "Exact affected location: nico/a.py"]}
        ],
        "reports": {
            "markdown": """
## Maturity Semaphore
- **Dependency / Library Ecosystem**: green
- **Secrets Exposure Review**: green
- **Static Analysis**: green
- **Scanner Worker Evidence**: red

### Dependency / Library Ecosystem — GREEN (90/100)
### Secrets Exposure Review — GREEN (92/100)
### Static Analysis — GREEN (90/100)
### Scanner Worker Evidence — SUPPLEMENTAL (27/100)
"""
        },
    }


def test_ten_canonical_truth_repairs() -> None:
    output = finalize_express_truth(_result())
    sections = {item["id"]: item for item in output["sections"]}

    # 1. Clean OSV evidence is not promoted as a finding.
    assert sections["dependency_health"]["findings"] == []
    # 2. A timed-out gitleaks run removes contradictory clean-gitleaks evidence.
    assert all("clean credential-scan and gitleaks" not in value.casefold() for value in sections["secrets_review"]["evidence"])
    # 3. An unresolved trufflehog candidate removes zero-credential claims.
    assert all("zero credential" not in value.casefold() for value in sections["secrets_review"]["evidence"])
    # 4. Failed Bandit cannot remain described as complete.
    assert all("bandit artifacts are complete" not in value.casefold() for value in sections["static_analysis"]["evidence"])
    # 5. Failed/unavailable analyzer evidence cannot remain GREEN.
    assert sections["static_analysis"]["status"] == "yellow"
    assert sections["static_analysis"]["confidence"] == "review-limited"
    # 6. Scanner Worker is supplemental and not scored.
    scanner = sections["scanner_worker_evidence"]
    assert scanner["status"] == "supplemental"
    assert scanner["score"] is None
    assert scanner["presented_score"] is None
    assert scanner["directly_scored"] is False
    # 7. Clean statements are removed from finding lists generally.
    assert sections["code_audit"]["findings"] == []
    # 8. Generic TODO candidates without exact locations are excluded.
    assert [item["title"] for item in output["repair_intelligence"]["candidates"]] == ["Complexity hotspot"]
    # 9. README-only evidence is removed from specific dossiers.
    assert output["finding_dossiers"][0]["evidence"] == ["Exact affected location: nico/a.py"]
    # 10. Markdown semaphore and headings use canonical statuses.
    markdown = output["reports"]["markdown"]
    assert "**Static Analysis**: yellow" in markdown
    assert "Static Analysis — YELLOW" in markdown
    assert "**Scanner Worker Evidence**: supplemental" in markdown
    assert "Scanner Worker Evidence — SUPPLEMENTAL (NOT SCORED)" in markdown

    truth = output["express_canonical_truth_finalization"]
    assert truth["status"] == "complete"
    assert truth["human_review_required"] is True
