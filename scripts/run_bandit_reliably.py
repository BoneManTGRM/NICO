from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_sha(root: Path) -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=root, text=True
    ).strip()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Bandit with exact-revision, machine-readable evidence."
    )
    parser.add_argument("--root", default=".")
    parser.add_argument("--output-dir", default="scanner-evidence/bandit")
    parser.add_argument(
        "--targets",
        nargs="+",
        default=["nico", "scripts"],
        help="Python source roots to scan.",
    )
    parser.add_argument(
        "--exclude",
        default="tests,.venv,venv,node_modules,dist,build",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_dir = (root / args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    result_path = output_dir / "bandit-results.json"
    stderr_path = output_dir / "bandit-stderr.log"
    record_path = output_dir / "bandit-execution-record.json"

    revision = os.environ.get("EXPECTED_COMMIT_SHA") or git_sha(root)
    current_revision = git_sha(root)
    if revision != current_revision:
        raise SystemExit(
            f"Exact-revision mismatch: expected {revision}, checked out {current_revision}"
        )

    command = [
        sys.executable,
        "-m",
        "bandit",
        "-r",
        *args.targets,
        "-f",
        "json",
        "-o",
        str(result_path),
        "--exclude",
        args.exclude,
    ]
    process = subprocess.run(
        command,
        cwd=root,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    stderr_path.write_text(process.stderr or "", encoding="utf-8")

    # Bandit exit code 1 means findings were detected, not that execution failed.
    execution_succeeded = process.returncode in {0, 1} and result_path.exists()
    payload: dict[str, Any] = {}
    parse_error: str | None = None
    if result_path.exists():
        try:
            payload = json.loads(result_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            parse_error = str(exc)
            execution_succeeded = False
    else:
        parse_error = "Bandit did not create its JSON output artifact."

    findings = payload.get("results") if isinstance(payload, dict) else []
    findings = findings if isinstance(findings, list) else []
    metrics = payload.get("metrics") if isinstance(payload, dict) else {}

    try:
        version = subprocess.check_output(
            [sys.executable, "-m", "bandit", "--version"],
            cwd=root,
            text=True,
            stderr=subprocess.STDOUT,
        ).strip()
    except subprocess.CalledProcessError as exc:
        version = exc.output.strip() or "unknown"
        execution_succeeded = False

    record = {
        "scanner": "bandit",
        "status": "completed" if execution_succeeded else "failed",
        "verified_complete": execution_succeeded,
        "commit_sha": revision,
        "exact_commit_match": revision == current_revision,
        "command": command,
        "version": version,
        "raw_exit_code": process.returncode,
        "exit_code_interpretation": (
            "completed_with_findings"
            if process.returncode == 1 and execution_succeeded
            else "completed_clean"
            if process.returncode == 0 and execution_succeeded
            else "execution_failure"
        ),
        "finding_count": len(findings),
        "metrics": metrics,
        "artifact_path": str(result_path.relative_to(root)) if result_path.exists() else None,
        "artifact_sha256": sha256_file(result_path) if result_path.exists() else None,
        "stderr_path": str(stderr_path.relative_to(root)),
        "stderr_sha256": sha256_file(stderr_path),
        "parse_error": parse_error,
    }
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(record, indent=2, sort_keys=True))
    return 0 if execution_succeeded else 2


if __name__ == "__main__":
    raise SystemExit(main())
