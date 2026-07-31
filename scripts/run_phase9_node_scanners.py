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
REVISION = os.environ.get("PHASE9_REVISION") or subprocess.check_output(
    ["git", "rev-parse", "HEAD"],
    text=True,
).strip()
ESLINT_AUDIT_PACKAGES = (
    "eslint@9",
    "@eslint/js@9",
    "@typescript-eslint/parser@8",
)
ESLINT_CONFIGS = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(
    name: str,
    command: list[str],
    *,
    accepted_codes: set[int],
) -> dict[str, Any]:
    OUT.mkdir(parents=True, exist_ok=True)
    proc = subprocess.run(
        command,
        cwd=WEB,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
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
    (OUT / f"{name}.json").write_text(
        json.dumps(record, indent=2),
        encoding="utf-8",
    )
    if status != "completed":
        raise SystemExit(f"{name} failed with exit code {proc.returncode}")
    return record


def _install_eslint_audit_client() -> dict[str, Any]:
    command = [
        "npm",
        "install",
        "--no-save",
        "--no-package-lock",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        *ESLINT_AUDIT_PACKAGES,
    ]
    proc = subprocess.run(
        command,
        cwd=WEB,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    log = OUT / "eslint-install.log"
    log.write_text(proc.stdout or "no output\n", encoding="utf-8")
    if proc.returncode != 0:
        raise SystemExit(
            f"supported ESLint audit client installation failed with exit code {proc.returncode}"
        )
    binary = WEB / "node_modules" / ".bin" / "eslint"
    if not binary.is_file():
        raise SystemExit("supported ESLint audit client did not install a local binary")
    version = subprocess.check_output(
        [str(binary), "--version"],
        cwd=WEB,
        text=True,
    ).strip()
    return {
        "packages": list(ESLINT_AUDIT_PACKAGES),
        "version": version,
        "installation_command": " ".join(command),
        "installation_artifact_path": str(log),
        "installation_artifact_sha256": sha256(log),
        "package_manifest_mutated": False,
        "package_lock_mutated": False,
        "scanner_environment": "ephemeral_exact_revision_audit",
    }


def main() -> None:
    if not (WEB / "package-lock.json").exists():
        raise SystemExit(
            "package-lock.json is required for deterministic scanner execution"
        )
    subprocess.run(
        ["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"],
        cwd=WEB,
        check=True,
    )
    typescript = run(
        "typescript",
        ["npx", "tsc", "--noEmit", "--pretty", "false"],
        accepted_codes={0},
    )

    configured = [name for name in ESLINT_CONFIGS if (WEB / name).is_file()]
    if configured:
        audit_client = _install_eslint_audit_client()
        binary = WEB / "node_modules" / ".bin" / "eslint"
        eslint = run(
            "eslint",
            [str(binary), ".", "--format", "json"],
            accepted_codes={0, 1},
        )
        eslint.update(
            {
                "configured": True,
                "configuration_files": configured,
                "audit_client": audit_client,
                "configuration_valid": True,
                "not_applicable": False,
            }
        )
        (OUT / "eslint.json").write_text(
            json.dumps(eslint, indent=2),
            encoding="utf-8",
        )
    else:
        eslint = {
            "scanner": "eslint",
            "status": "not_applicable",
            "commit_sha": REVISION,
            "configured": False,
            "configuration_files": [],
            "reason": (
                "No ESLint configuration file exists at the immutable revision; "
                "TypeScript remains the configured source-validation boundary."
            ),
        }
        (OUT / "eslint.json").write_text(
            json.dumps(eslint, indent=2),
            encoding="utf-8",
        )

    manifest = {
        "immutable_revision": REVISION,
        "typescript": typescript,
        "eslint": eslint,
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(manifest))


if __name__ == "__main__":
    main()
