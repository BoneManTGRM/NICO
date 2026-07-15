from __future__ import annotations

from typing import Any

from nico.local_scan_service import run_scan


def swarm_audit(repo: str) -> dict[str, Any]:
    """Run the real local scanner and return report-only repair intelligence.

    This compatibility entry point does not claim a fixed bug, a deployed change, or
    a specific agent count. Findings and repair candidates come from the actual NICO
    scan result for the authorized local repository path.
    """

    result = run_scan(repo, kind="swarm_audit")
    scan = result.get("scan") if isinstance(result.get("scan"), dict) else {}
    findings = [item for item in scan.get("findings", []) or [] if isinstance(item, dict)]
    repairs = [item for item in result.get("repairs", []) or [] if isinstance(item, dict)]
    return {
        "status": "complete",
        "mode": "evidence_bound_local_swarm",
        "repository_path": repo,
        "scan_id": scan.get("id"),
        "files_scanned_count": len(scan.get("files_scanned", []) or []),
        "findings_count": len(findings),
        "repair_candidate_count": len(repairs),
        "findings": findings,
        "repair_candidates": repairs,
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "human_review_required": True,
        "truth_rules": [
            "No finding is described as fixed by this scan.",
            "Code suggestions remain inside reports or repair records until separately reviewed and tested.",
            "Unavailable tools remain disclosed by the underlying scan evidence.",
        ],
    }


__all__ = ["swarm_audit"]
