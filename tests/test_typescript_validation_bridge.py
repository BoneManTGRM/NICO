from __future__ import annotations

import nico.typescript_validation_bridge as bridge


def test_ci_typescript_validation_requires_command_and_success() -> None:
    repo = {
        "workflow_evidence": {
            "commands_detected": ["pytest", "npm run lint"],
            "successful_runs": 12,
        }
    }

    result = bridge.ci_typescript_validation(repo)

    assert result["completed"] is True
    assert result["commands"] == ["npm run lint"]
    assert result["successful_workflow_runs"] == 12


def test_typescript_validation_does_not_claim_eslint(monkeypatch) -> None:
    monkeypatch.setattr(
        bridge,
        "_DELEGATE_STATIC_SECTION",
        lambda _repo, _scanner: {
            "id": "static_analysis",
            "label": "Static Analysis",
            "score": 76,
            "status": "yellow",
            "evidence": [],
            "verified_claims": [],
            "findings": [],
            "unavailable": ["ESLint exact-snapshot evidence was not completed; JavaScript/TypeScript semantic lint coverage remains unavailable."],
            "static_triage": {"material_finding_count": 0},
        },
    )
    repo = {
        "workflow_evidence": {
            "commands_detected": ["npm run lint"],
            "successful_runs": 4,
        }
    }
    scanner = {"scanner_results": [{"scanner": "eslint", "status": "unavailable"}]}

    section = bridge.static_section_with_typescript_validation(repo, scanner)

    assert section["score"] == 80
    assert section["status"] == "green"
    assert any("CI-backed TypeScript validation completed" in item for item in section["evidence"])
    assert any("not equivalent to exact-snapshot ESLint" in item for item in section["unavailable"])
    assert section["static_triage"]["typescript_validation"]["eslint_exact_snapshot_completed"] is False
