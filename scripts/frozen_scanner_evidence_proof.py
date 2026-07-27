#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from nico.scanner_evidence_pipeline_v1 import (
    REQUIRED_EVIDENCE_TOOLS,
    VERSION,
    materialize_raw_artifacts,
    run_canonical_scanner_tools,
)
from nico.scanner_tool_runners import TOOL_SPECS
from nico.worker_execution import WorkerWorkspace


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def run_git(*args: str, cwd: Path | None = None) -> str:
    completed = subprocess.run(
        ("git", *args),
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def prepare_checkout(source: Path, destination: Path, target_sha: str) -> WorkerWorkspace:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True)
    repo_dir = destination / "repo"
    subprocess.run(
        ("git", "clone", "--no-local", "--no-tags", "--no-checkout", str(source), str(repo_dir)),
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ("git", "checkout", "--detach", target_sha),
        cwd=repo_dir,
        check=True,
        capture_output=True,
        text=True,
    )
    observed = run_git("rev-parse", "HEAD", cwd=repo_dir)
    if observed != target_sha:
        raise RuntimeError(f"checkout identity mismatch: expected {target_sha}, got {observed}")
    shallow = run_git("rev-parse", "--is-shallow-repository", cwd=repo_dir)
    if shallow != "false":
        raise RuntimeError("frozen proof checkout is shallow; full-history secret evidence would be invalid")
    return WorkerWorkspace(root=destination)


def run_once(
    *,
    source: Path,
    target_sha: str,
    repository: str,
    output_root: Path,
    run_number: int,
) -> dict[str, Any]:
    started_at = now_iso()
    workspace = prepare_checkout(source, output_root / f"workspace-{run_number}", target_sha)
    specs = tuple(spec for spec in TOOL_SPECS if spec.name in REQUIRED_EVIDENCE_TOOLS)
    if {spec.name for spec in specs} != set(REQUIRED_EVIDENCE_TOOLS):
        missing = sorted(set(REQUIRED_EVIDENCE_TOOLS) - {spec.name for spec in specs})
        raise RuntimeError(f"required scanner specifications are missing: {missing}")

    started = time.monotonic()
    artifact = run_canonical_scanner_tools(workspace, specs=specs)
    run_id = f"frozen-{target_sha[:12]}-{run_number}"
    artifact.update(
        {
            "proof_run_number": run_number,
            "repository": repository,
            "target_commit_sha": target_sha,
            "run_id": run_id,
            "started_at": started_at,
            "finished_at": now_iso(),
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    )
    materialize_raw_artifacts(
        artifact,
        output_root / "retained",
        repository=repository,
        commit_sha=target_sha,
        run_id=run_id,
    )
    safe_artifact = dict(artifact)
    safe_artifact.pop("raw_artifact_blobs", None)
    output_path = output_root / f"scanner-run-{run_number}.json"
    output_path.write_text(json.dumps(safe_artifact, indent=2, sort_keys=True), encoding="utf-8")
    # The retained gzip artifacts and manifest are the proof. The temporary
    # checkout, node_modules, and unredacted working files must not be uploaded.
    shutil.rmtree(workspace.root, ignore_errors=True)

    statuses = artifact.get("required_scanner_statuses") or {}
    incomplete = {
        tool: statuses.get(tool, "missing")
        for tool in REQUIRED_EVIDENCE_TOOLS
        if statuses.get(tool) != "completed"
    }
    if incomplete:
        raise RuntimeError(f"required scanners did not complete: {incomplete}")
    if artifact.get("required_scanner_completion") is not True:
        raise RuntimeError("required_scanner_completion is not true")
    if artifact.get("raw_artifact_capture_complete") is not True:
        raise RuntimeError("raw scanner artifact capture is incomplete")
    if artifact.get("raw_artifact_retention_complete") is not True:
        raise RuntimeError(
            "raw scanner artifact retention is incomplete: "
            + json.dumps(artifact.get("raw_artifact_retention_errors") or [])
        )
    if artifact.get("scanner_evidence_ready") is not True:
        raise RuntimeError("scanner evidence did not reach the ready state")
    return safe_artifact


def equivalence(run_one: dict[str, Any], run_two: dict[str, Any]) -> dict[str, Any]:
    statuses_equal = run_one.get("required_scanner_statuses") == run_two.get("required_scanner_statuses")
    fingerprints_one = run_one.get("deterministic_fingerprints") or {}
    fingerprints_two = run_two.get("deterministic_fingerprints") or {}
    fingerprints_equal = fingerprints_one == fingerprints_two
    counts_one = {
        tool: int(((run_one.get("tools") or {}).get(tool) or {}).get("findings_count") or 0)
        for tool in REQUIRED_EVIDENCE_TOOLS
    }
    counts_two = {
        tool: int(((run_two.get("tools") or {}).get(tool) or {}).get("findings_count") or 0)
        for tool in REQUIRED_EVIDENCE_TOOLS
    }
    counts_equal = counts_one == counts_two
    return {
        "statuses_equal": statuses_equal,
        "deterministic_fingerprints_equal": fingerprints_equal,
        "finding_counts_equal": counts_equal,
        "run_one_fingerprints": fingerprints_one,
        "run_two_fingerprints": fingerprints_two,
        "run_one_finding_counts": counts_one,
        "run_two_finding_counts": counts_two,
        "equivalent": statuses_equal and fingerprints_equal and counts_equal,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run two complete NICO scanner passes against one immutable repository SHA."
    )
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--target-sha", required=True)
    parser.add_argument("--repository", default="BoneManTGRM/NICO")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)

    source = args.source.resolve()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if not (source / ".git").exists():
        raise SystemExit(f"source checkout is not a git repository: {source}")
    source_has_target = subprocess.run(
        ("git", "cat-file", "-e", f"{args.target_sha}^{{commit}}"),
        cwd=source,
        capture_output=True,
        text=True,
    )
    if source_has_target.returncode != 0:
        raise SystemExit(f"source checkout does not contain target commit {args.target_sha}")

    os.environ.setdefault("NICO_ALLOW_PROJECT_COMMANDS", "true")
    os.environ.setdefault("NICO_NODE_OPTIONS", "--max-old-space-size=2048")
    os.environ.setdefault("NICO_MAX_SCANNER_PARSE_BYTES", str(256 * 1024 * 1024))

    first = run_once(
        source=source,
        target_sha=args.target_sha,
        repository=args.repository,
        output_root=output,
        run_number=1,
    )
    second = run_once(
        source=source,
        target_sha=args.target_sha,
        repository=args.repository,
        output_root=output,
        run_number=2,
    )
    comparison = equivalence(first, second)
    proof = {
        "schema": "nico.frozen_scanner_proof.v1",
        "pipeline_version": VERSION,
        "repository": args.repository,
        "target_commit_sha": args.target_sha,
        "generated_at": now_iso(),
        "required_tools": list(REQUIRED_EVIDENCE_TOOLS),
        "run_one_ready": first.get("scanner_evidence_ready") is True,
        "run_two_ready": second.get("scanner_evidence_ready") is True,
        "comparison": comparison,
        "two_consecutive_clean_runs": (
            first.get("scanner_evidence_ready") is True
            and second.get("scanner_evidence_ready") is True
            and comparison["equivalent"] is True
        ),
    }
    (output / "frozen-scanner-proof.json").write_text(
        json.dumps(proof, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if proof["two_consecutive_clean_runs"] is not True:
        print(json.dumps(proof, indent=2, sort_keys=True), file=sys.stderr)
        return 1
    print(json.dumps(proof, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
