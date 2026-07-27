#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from nico.frozen_sha_scanner_evidence_v1 import (
    CRITICAL_REPEATABILITY_TOOLS,
    FROZEN_QUALIFICATION_SHA,
    REQUIRED_TOOLS,
    qualification_summary,
    run_snapshot_scan_sync,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the complete NICO scanner boundary twice against one immutable SHA."
    )
    parser.add_argument("--repository", default="BoneManTGRM/NICO")
    parser.add_argument("--commit-sha", default=FROZEN_QUALIFICATION_SHA)
    parser.add_argument("--output", type=Path, default=Path("frozen-sha-scanner-qualification.json"))
    parser.add_argument("--artifact-root", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    commit_sha = str(args.commit_sha or "").strip().lower()
    if commit_sha != FROZEN_QUALIFICATION_SHA:
        raise SystemExit(
            f"Qualification must remain pinned to {FROZEN_QUALIFICATION_SHA}; received {commit_sha or 'missing'}."
        )
    if args.artifact_root:
        os.environ["NICO_SCANNER_ARTIFACT_ROOT"] = str(args.artifact_root.resolve())
    payload = {
        "repository": args.repository,
        "snapshot_commit_sha": commit_sha,
        "snapshot_id": f"frozen_sha_{commit_sha[:16]}",
        "run_id": f"qualification_{commit_sha[:16]}",
        "customer_id": "nico_internal_qualification",
        "project_id": "scanner_evidence_pipeline",
        "authorized": True,
        "authorized_by": "NICO scanner qualification workflow",
        "authorization_scope": "read-only defensive scanner qualification against the frozen NICO commit",
    }
    scan = run_snapshot_scan_sync(payload)
    summary = qualification_summary(scan)
    summary["required_tools"] = list(REQUIRED_TOOLS)
    summary["critical_repeatability_tools"] = list(CRITICAL_REPEATABILITY_TOOLS)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    errors: list[str] = []
    if summary.get("status") != "qualified":
        errors.append("scanner qualification status is not qualified")
    if summary.get("actual_commit_sha") != commit_sha or summary.get("snapshot_match") is not True:
        errors.append("scanner checkout did not remain pinned to the frozen SHA")
    if summary.get("full_history_verified") is not True:
        errors.append("full exact-SHA history was not verified")
    if summary.get("required_tools_complete") is not True:
        errors.append("one or more required scanners did not complete")
    repeatability = summary.get("repeatability") if isinstance(summary.get("repeatability"), dict) else {}
    if repeatability.get("status") != "verified" or repeatability.get("equivalent") is not True:
        errors.append("critical scanner outputs were not deterministic across two consecutive passes")
    for name in REQUIRED_TOOLS:
        item = (summary.get("first_pass") or {}).get(name) or {}
        if item.get("status") != "completed":
            errors.append(f"{name} first pass did not complete")
        if item.get("output_capture_complete") is not True:
            errors.append(f"{name} first-pass output was incomplete")
        if not item.get("artifact_sha256"):
            errors.append(f"{name} first-pass artifact checksum is missing")
    for name in CRITICAL_REPEATABILITY_TOOLS:
        item = (summary.get("second_pass") or {}).get(name) or {}
        if item.get("status") != "completed":
            errors.append(f"{name} second pass did not complete")
        if item.get("output_capture_complete") is not True:
            errors.append(f"{name} second-pass output was incomplete")
        if not item.get("artifact_sha256"):
            errors.append(f"{name} second-pass artifact checksum is missing")
    retention = summary.get("artifact_retention") if isinstance(summary.get("artifact_retention"), dict) else {}
    if retention.get("raw_outputs_retained") is not True or not retention.get("manifest_sha256"):
        errors.append("raw scanner artifacts were not retained with a checksummed manifest")

    print(json.dumps(summary, indent=2, sort_keys=True))
    if errors:
        raise SystemExit("Frozen-SHA scanner qualification failed: " + "; ".join(errors))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
