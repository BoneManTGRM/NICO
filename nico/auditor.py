#!/usr/bin/env python3
"""NICO local authorized GitHub repository auditor.

Usage:
    python -m nico.auditor <owner/name-or-github-url> --tier full --swarm

The auditor clones an explicitly authorized GitHub repository into a unique temporary
workspace, runs NICO's real local scanner, and returns evidence-bound findings and
report-only repair candidates. It does not edit, commit, push, or deploy changes to
the target.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from nico.cli import generate_reports, run_scan
from nico.swarm_bugs import swarm_audit

_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def _canonical_github_repository(value: str) -> tuple[str, str]:
    """Return a credential-free GitHub clone URL and canonical owner/name identity."""

    candidate = str(value or "").strip()
    if _REPOSITORY_RE.fullmatch(candidate):
        repository = candidate
    else:
        parsed = urlparse(candidate)
        if (
            parsed.scheme != "https"
            or (parsed.hostname or "").lower() != "github.com"
            or parsed.username
            or parsed.password
            or parsed.port not in {None, 443}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("repository must be an HTTPS github.com URL or owner/name")
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) != 2:
            raise ValueError("GitHub repository URL must contain exactly owner/name")
        owner, name = parts
        if name.endswith(".git"):
            name = name[:-4]
        repository = f"{owner}/{name}"
        if not _REPOSITORY_RE.fullmatch(repository):
            raise ValueError("GitHub repository owner/name contains unsupported characters")

    owner, name = repository.split("/", 1)
    if owner in {".", ".."} or name in {".", ".."}:
        raise ValueError("invalid GitHub repository identity")
    return f"https://github.com/{repository}.git", repository


def _failed(error: str) -> dict[str, Any]:
    return {
        "status": "failed",
        "error": error,
        "semaphore": "red",
        "code_changes_applied": False,
        "automatic_application_allowed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def audit(repo_url: str, tier: str = "full", mode: str = "audit", use_swarm: bool = False) -> dict[str, Any]:
    try:
        clone_url, repository = _canonical_github_repository(repo_url)
    except ValueError as exc:
        return _failed(f"Repository validation failed: {exc}")

    workspace_root = Path(tempfile.mkdtemp(prefix="nico-audit-"))
    workdir = workspace_root / "repo"
    try:
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", "--", clone_url, str(workdir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            return _failed(f"Clone failed safely: {type(exc).__name__}")

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
            "repo": repository,
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
            "client_delivery_allowed": False,
        }
        print(json.dumps(report, indent=2, default=str))
        return report
    finally:
        shutil.rmtree(workspace_root, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="NICO authorized local GitHub repository auditor")
    parser.add_argument("url", help="Authorized GitHub owner/name or HTTPS repository URL")
    parser.add_argument("--tier", default="full", choices=["express", "mid", "full"])
    parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    parser.add_argument("--swarm", action="store_true")
    args = parser.parse_args()
    audit(args.url, args.tier, args.mode, args.swarm)


if __name__ == "__main__":
    main()
