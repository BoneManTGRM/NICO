from __future__ import annotations

import asyncio

from nico import swarm_bugs
from nico.swarm_bug import BugSwarm


def _scan_result() -> dict:
    return {
        "scan": {
            "id": "scan_123",
            "files_scanned": ["app.py"],
            "findings": [
                {
                    "id": "finding_1",
                    "title": "Unsafe eval",
                    "category": "unsafe_eval",
                    "severity": "critical",
                    "rye": {"score": 90},
                }
            ],
        },
        "repairs": [
            {
                "id": "repair_1",
                "status": "report_only_unverified_candidate",
                "code_change_applied": False,
            }
        ],
    }


def test_swarm_audit_returns_real_findings_without_change_claim(monkeypatch) -> None:
    monkeypatch.setattr(swarm_bugs, "run_scan", lambda repo, kind: _scan_result())

    result = swarm_bugs.swarm_audit("/authorized/repo")

    assert result["status"] == "complete"
    assert result["scan_id"] == "scan_123"
    assert result["findings_count"] == 1
    assert result["repair_candidate_count"] == 1
    assert result["code_changes_applied"] is False
    assert result["automatic_application_allowed"] is False
    assert result["repair_candidates"][0]["status"] == "report_only_unverified_candidate"
    assert result["repair_candidates"][0]["code_change_applied"] is False
    assert not any(
        finding.get("status") in {"fixed", "applied", "deployed"}
        for finding in result["findings"]
        if isinstance(finding, dict)
    )


def test_async_swarm_facade_uses_evidence_bound_result(monkeypatch) -> None:
    monkeypatch.setattr("nico.swarm_bug.swarm_audit", lambda repo: {
        "status": "complete",
        "findings": [],
        "repair_candidates": [],
        "code_changes_applied": False,
    })

    result = asyncio.run(BugSwarm().swarm("/authorized/repo"))

    assert result["status"] == "complete"
    assert result["code_changes_applied"] is False
    assert "crewai" not in str(result).lower()
    assert result["detector_families"]
