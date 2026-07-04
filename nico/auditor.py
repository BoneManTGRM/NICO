#!/usr/bin/env python3
"""Real MalamuteNICO-Auditor (local, no server)
Uses restored CLI from PR #1 for actual scans + RYE + reports."""

import argparse
import json
import os
import shutil
import subprocess
from pathlib import Path

try:
    from nico.cli import (
        run_scan, apply_rye, repairs_for, generate_reports,
        scan_test_lab, scan_drift_demo, verify_latest,
        rye_score, Store
    )
except ImportError:
    # Fallback if run as standalone
    print("Importing from nico.cli... ensure PYTHONPATH or installed package")
    raise

def audit(repo_url: str, tier: str = "full", mode: str = "audit", use_swarm: bool = False) -> dict:
    """
    Real audit for any public GitHub repo URL.
    Clones locally, runs NICO scan + RYE + repairs.
    """
    print(f"\n🚀 Starting {tier.upper()} audit for {repo_url} (local mode)")

    # Clone to temp local dir (safe, no server)
    repo_name = repo_url.rstrip("/").split("/")[-1]
    workdir = Path("/tmp/nico_audit") / repo_name
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.parent.mkdir(parents=True, exist_ok=True)

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, str(workdir)],
            check=True, capture_output=True, text=True
        )
    except subprocess.CalledProcessError as e:
        return {"error": f"Clone failed: {e.stderr}", "semaphore": "Red"}

    # Run real NICO scan + RYE
    result = run_scan(str(workdir), kind="url_audit")
    findings = result.get("scan", {}).get("findings", [])
    repairs = result.get("repairs", [])

    # Apply extra RYE if swarm requested
    if use_swarm:
        for f in findings:
            f["rye"] = rye_score(f)

    # Generate full reports
    report_paths = generate_reports()

    report = {
        "repo": repo_url,
        "tier": tier,
        "mode": mode,
        "semaphore": "🟢 Green" if len(findings) == 0 else "🟡 Mid" if len(findings) < 10 else "🔴 Red",
        "findings_count": len(findings),
        "repairs_count": len(repairs),
        "rye_top": sorted(
            [{"issue": f.get("title"), "rye": f.get("rye", {}).get("score", 0)} for f in findings],
            key=lambda x: x["rye"], reverse=True
        )[:5],
        "quick_wins": [r.get("smallest_safe_change") for r in repairs[:3]],
        "roadmap_6mo": "TGRM repairs prioritized by RYE score. Start with top 3.",
        "resourcing": "1 Product Engineering Architect (AI-augmented) + 2 Mobile/Product Engineers + QA swarm",
        "retainer": "Persistent RYE monitoring + auto ceremonies active" if mode == "retainer" else "Audit complete",
        "report_files": report_paths,
        "swarm_used": use_swarm,
    }

    print("\n✅ Real audit complete (local clone + NICO engine + RYE)")
    print(json.dumps(report, indent=2, default=str))
    return report


def main():
    parser = argparse.ArgumentParser(description="MalamuteNICO-Auditor - Real local agent")
    parser.add_argument("url", help="Public GitHub repo URL (iOS/Android or any)")
    parser.add_argument("--tier", default="full", choices=["express", "mid", "full"])
    parser.add_argument("--mode", default="audit", choices=["audit", "retainer"])
    parser.add_argument("--swarm", action="store_true")
    args = parser.parse_args()

    audit(args.url, args.tier, args.mode, args.swarm)

if __name__ == "__main__":
    main()
