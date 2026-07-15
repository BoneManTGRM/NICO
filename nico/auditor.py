#!/usr/bin/env python3
"""NICO local authorized repository auditor.

Usage:
    python -m nico.auditor <url> --tier full --swarm

The auditor clones an explicitly authorized repository into a temporary workspace,
runs NICO's real local scanner, and returns evidence-bound findings and report-only
repair candidates. It does not edit, commit, push, or deploy changes to the target.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from nico.cli import generate_reports, run_scan
from nico.swarm_bugs import swarm_audit


def audit(repo_url: str, tier: str = "full", mode: str = "audit", use_swarm: bool = False) -> dict[str, Any]:
    repo_name = repo_url.rstrip("/").split("/")[-1]
    workdir = Path("/tmp/nico_audit") / repo_name
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(workdir)],
            check=True,
            capture_output=True,
            text=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        message = getattr(exc, "stderr", None) or str(exc)
        return {
            "status": "failed",
            "error": f"Clone failed: {message}",
            "semaphore": "red",
            "code_changes_applied": False,
        }

    if use_swarm:
        swarm_result = swarm_audit(str(workdir))
        findings = [item for item in swarm_result.get("findings", []) or [] if isinstance(item, dict)]
        repairs = [item for item in swarm_result.get("repair_candidates", []) or [] if isinstance(item, dict)]
        scan_id = swarm_result.get("scan_id")
        detector_evidence = swarm_result.get("truth_rules", [])
    else:
        scan_result = run_scan(str(workdir), kind="url_audit")
        scan = scan_result.get("scan") if isinstance(scan_result.get("scan"), dict) else {}
        findings = [item for item in scan.get("findings", []) or [] if isinstance(item, dict)]
        repairs = [item for item in scan_result.get("repairs", []) or [] if isinstance(item, dict)]
        scan_id = scan.get("id")
        detector_evidence = ["Standard NICO local scanner path was used."]

    report_paths = generate_reports()
    semaphore = "green" if not findings else "yellow" if len(findings) < 10 else "red"
    report = {
        "status": "complete",
        "repo": repo_url,
        "tier": tier,
        "mode": mode,
        "scan_id": scan_id,
        "semaphore": semaphore,
        "findings_count": len(findings),
        "repair_candidate_count": len(repairs),
        "rye_top": sorted(
            [
                {
                    "issue": finding.get("title"),
                    "rye": (finding.get("rye") or {}).get("score", 0),
                    "severity": finding.get("severity"),
                    "affected_file": finding.get("affected_file"),
                }
                for finding in findings
            ],
            key=lambda item: item["rye"],
            reverse=True,
        )[:10],
        "quick_wins": [repair.get("smallest_safe_change") for repair in repairs[:5]],
        "repair_candidates": repairs[:15],
        "roadmap_6mo": "Prioritize evidence-bound TGRM repair candidates by RYE score and verify each adopted change.",
        "resourcing": "Assign owners from the affected capability and require independent review for high-risk repairs.",
        "retainer": (
            "Ongoing evidence collection and repair-memory review are available; no automatic code change is enabled."
            if mode == "retainer"
            else "Audit complete; human review required."
        ),
        "report_files": report_paths,
        "swarm_used": use_swarm,
        "detector_evidence": detector_evidence,
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "human_review_required": True,
    }
    print(json.dumps(report, indent=2, default=str))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="NICO authorized local repository auditor")
    parser.add_argument("url", help="Authorized GitHub repository URL")
    parser.add_argument("--tier", default="full", choices=["express", "mid", "full"])
    parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    parser.add_argument("--swarm", action="store_true")
    args = parser.parse_args()
    audit(args.url, args.tier, args.mode, args.swarm)


if __name__ == "__main__":
    main()
