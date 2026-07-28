from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "apps" / "web"
OUT = ROOT / "phase9-node-scanner-evidence"
REVISION = os.environ.get("PHASE9_REVISION") or subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(name: str, command: list[str], *, accepted_codes: set[int]) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(command, cwd=WEB, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    log = OUT / f"{name}.log"
    log.write_text(proc.stdout or "no output\n", encoding="utf-8")
    status = "completed" if proc.returncode in accepted_codes else "failed"
    record = {
        "scanner": name,
        "status": status,
        "commit_sha": REVISION,
        "command": " ".join(command),
        "raw_exit_code": proc.returncode,
        "artifact_path": str(log),
        "artifact_sha256": sha256(log),
    }
    (OUT / f"{name}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    if status != "completed":
        raise SystemExit(f"{name} failed with exit code {proc.returncode}")
    return record


def main() -> None:
    if not (WEB / "package-lock.json").exists():
        raise SystemExit("package-lock.json is required for deterministic scanner execution")
    subprocess.run(["npm", "ci", "--ignore-scripts"], cwd=WEB, check=True)
    typescript = run("typescript", ["npx", "tsc", "--noEmit", "--pretty", "false"], accepted_codes={0})

    package = json.loads((WEB / "package.json").read_text(encoding="utf-8"))
    has_eslint = "eslint" in package.get("devDependencies", {}) or "eslint" in package.get("dependencies", {})
    if has_eslint:
        eslint = run("eslint", ["npx", "eslint", ".", "--format", "json"], accepted_codes={0, 1})
    else:
        eslint = {
            "scanner": "eslint",
            "status": "not_applicable",
            "commit_sha": REVISION,
            "reason": "ESLint is not declared in the immutable repository package manifest; TypeScript is the configured lint boundary.",
        }
        (OUT / "eslint.json").write_text(json.dumps(eslint, indent=2), encoding="utf-8")

    manifest = {"immutable_revision": REVISION, "typescript": typescript, "eslint": eslint}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
