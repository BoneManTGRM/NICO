from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REQUIRED_RUNTIME_TOOLS = (
    {"tool": "python", "binary": "python", "category": "runtime", "required_for": "backend and Python scanners"},
    {"tool": "git", "binary": "git", "category": "runtime", "required_for": "authorized repository checkout and full-history scans"},
    {"tool": "node", "binary": "node", "category": "runtime", "required_for": "frontend dependency and TypeScript scanners"},
    {"tool": "npm", "binary": "npm", "category": "runtime", "required_for": "npm-audit, eslint, typescript"},
    {"tool": "pip-audit", "binary": "pip-audit", "category": "dependency", "required_for": "Python dependency proof"},
    {"tool": "npm-audit", "binary": "npm", "category": "dependency", "required_for": "npm dependency proof"},
    {"tool": "osv-scanner", "binary": "osv-scanner", "category": "dependency", "required_for": "OSV dependency proof"},
    {"tool": "bandit", "binary": "bandit", "category": "static", "required_for": "Python static analysis proof"},
    {"tool": "semgrep", "binary": "semgrep", "category": "static", "required_for": "multi-language static analysis proof"},
    {"tool": "eslint", "binary": "eslint", "category": "static", "required_for": "JavaScript/TypeScript lint evidence"},
    {"tool": "typescript", "binary": "tsc", "category": "static", "required_for": "TypeScript typecheck evidence"},
    {"tool": "gitleaks", "binary": "gitleaks", "category": "secret", "required_for": "full-history secret proof"},
    {"tool": "trufflehog", "binary": "trufflehog", "category": "secret", "required_for": "full-history secret proof"},
)

VERSION_COMMANDS: dict[str, tuple[str, ...]] = {
    "python": (sys.executable, "--version"),
    "git": ("git", "--version"),
    "node": ("node", "--version"),
    "npm": ("npm", "--version"),
    "pip-audit": ("pip-audit", "--version"),
    "osv-scanner": ("osv-scanner", "--version"),
    "bandit": ("bandit", "--version"),
    "semgrep": ("semgrep", "--version"),
    "eslint": ("eslint", "--version"),
    "typescript": ("tsc", "--version"),
    "gitleaks": ("gitleaks", "version"),
    "trufflehog": ("trufflehog", "--version"),
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).lower() == "true"


def _safe_version(tool: str, binary: str) -> dict[str, Any]:
    command = VERSION_COMMANDS.get(tool) or (binary, "--version")
    try:
        completed = subprocess.run(
            command,
            cwd=Path.cwd(),
            text=True,
            capture_output=True,
            timeout=12,
            check=False,
            env={
                "PATH": os.getenv("PATH", ""),
                "HOME": os.getenv("HOME", ""),
                "LANG": os.getenv("LANG", "C.UTF-8"),
                "LC_ALL": os.getenv("LC_ALL", "C.UTF-8"),
            },
        )
    except FileNotFoundError:
        return {"status": "not_installed", "returncode": None, "version": "", "reason": f"{binary} is not available on PATH"}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "returncode": None, "version": "", "reason": f"{tool} version command timed out"}
    except Exception as exc:  # pragma: no cover - defensive runtime diagnostics
        return {"status": "failed", "returncode": None, "version": "", "reason": str(exc)}
    text = (completed.stdout or completed.stderr or "").strip().splitlines()
    version = text[0][:300] if text else ""
    return {
        "status": "installed" if completed.returncode == 0 else "command_failed",
        "returncode": completed.returncode,
        "version": version,
        "reason": "" if completed.returncode == 0 else (completed.stderr or completed.stdout or "version command failed")[:1000],
    }


def _tool_record(spec: dict[str, str]) -> dict[str, Any]:
    tool = spec["tool"]
    binary = spec["binary"]
    path = shutil.which(binary)
    version = _safe_version(tool, binary) if path else {"status": "not_installed", "returncode": None, "version": "", "reason": f"{binary} is not available on PATH"}
    return {
        "tool": tool,
        "binary": binary,
        "category": spec["category"],
        "required_for": spec["required_for"],
        "path": path or "",
        "installed": bool(path) and version["status"] in {"installed", "command_failed"},
        "status": version["status"],
        "returncode": version["returncode"],
        "version": version["version"],
        "reason": version["reason"],
    }


def hosted_scanner_runtime_diagnostics() -> dict[str, Any]:
    tools = [_tool_record(spec) for spec in REQUIRED_RUNTIME_TOOLS]
    scanner_tools = [item for item in tools if item["category"] in {"dependency", "static", "secret"}]
    missing = [item["tool"] for item in scanner_tools if not item["installed"]]
    installed = [item["tool"] for item in scanner_tools if item["installed"]]
    config = {
        "NICO_ENABLE_HOSTED_SCANNER_AUTORUN": _bool_env("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "true"),
        "NICO_ALLOW_PROJECT_COMMANDS": _bool_env("NICO_ALLOW_PROJECT_COMMANDS", "false"),
        "NICO_ENABLE_FULL_HISTORY_SECRET_SCAN": _bool_env("NICO_ENABLE_FULL_HISTORY_SECRET_SCAN", "true"),
        "NICO_SCANNER_INSTALL_STRICT": _bool_env("NICO_SCANNER_INSTALL_STRICT", "false"),
        "NICO_SCANNER_INSTALL_DIR": os.getenv("NICO_SCANNER_INSTALL_DIR", "/usr/local/bin"),
    }
    blockers: list[str] = []
    if not config["NICO_ENABLE_HOSTED_SCANNER_AUTORUN"]:
        blockers.append("NICO_ENABLE_HOSTED_SCANNER_AUTORUN is false, so hosted scanner execution is disabled.")
    if not config["NICO_ALLOW_PROJECT_COMMANDS"]:
        blockers.append("NICO_ALLOW_PROJECT_COMMANDS is false, so ESLint/TypeScript project-command evidence will stay unavailable.")
    if not config["NICO_ENABLE_FULL_HISTORY_SECRET_SCAN"]:
        blockers.append("NICO_ENABLE_FULL_HISTORY_SECRET_SCAN is false, so gitleaks/trufflehog full-history coverage is disabled.")
    if missing:
        blockers.append("Scanner binaries missing from PATH: " + ", ".join(missing) + ".")
    return {
        "status": "ok",
        "generated_at": _now_iso(),
        "purpose": "Hosted scanner runtime verification. This reports deployed container tool availability only; it does not mark a scanner result clean.",
        "runtime": {
            "python_version": sys.version.split()[0],
            "platform": platform.platform(),
            "cwd": str(Path.cwd()),
            "path_entries": [entry for entry in os.getenv("PATH", "").split(os.pathsep) if entry],
        },
        "config": config,
        "tools": tools,
        "summary": {
            "scanner_tools_installed": installed,
            "scanner_tools_missing": missing,
            "installed_count": len(installed),
            "missing_count": len(missing),
            "required_scanner_tool_count": len(scanner_tools),
            "runtime_ready": not missing and not blockers,
        },
        "blockers": blockers,
        "guardrail": "Missing tools remain unavailable evidence. This endpoint never converts missing, failed, or unverified scanner output into green scoring evidence.",
    }


def register_hosted_scanner_runtime_diagnostics_routes(app: Any) -> None:
    @app.get("/diagnostics/hosted-scanner-runtime")
    def hosted_scanner_runtime_diagnostics_endpoint() -> dict[str, Any]:
        return hosted_scanner_runtime_diagnostics()
