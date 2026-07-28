from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from typing import Mapping, Sequence

VERSION = "nico.scanner_preflight.v1"


@dataclass(frozen=True)
class ScannerRequirement:
    name: str
    executable: str
    version_args: tuple[str, ...] = ("--version",)
    applicable: bool = True


DEFAULT_REQUIREMENTS: tuple[ScannerRequirement, ...] = (
    ScannerRequirement("osv-scanner", "osv-scanner"),
    ScannerRequirement("pip-audit", "pip-audit"),
    ScannerRequirement("npm-audit", "npm"),
    ScannerRequirement("bandit", "bandit"),
    ScannerRequirement("semgrep", "semgrep"),
    ScannerRequirement("gitleaks", "gitleaks"),
    ScannerRequirement("trufflehog", "trufflehog"),
)


def run_preflight(
    requirements: Sequence[ScannerRequirement] = DEFAULT_REQUIREMENTS,
    *,
    timeout_seconds: int = 20,
    environment: Mapping[str, str] | None = None,
) -> dict:
    records = []
    incomplete = []
    for requirement in requirements:
        if not requirement.applicable:
            records.append({"tool": requirement.name, "status": "not_applicable"})
            continue
        path = shutil.which(requirement.executable)
        if not path:
            records.append({"tool": requirement.name, "status": "missing", "executable": requirement.executable})
            incomplete.append(requirement.name)
            continue
        try:
            completed = subprocess.run(
                [path, *requirement.version_args],
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=dict(environment) if environment is not None else None,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            records.append({"tool": requirement.name, "status": "unusable", "reason": type(exc).__name__})
            incomplete.append(requirement.name)
            continue
        version_text = (completed.stdout or completed.stderr or "").strip().splitlines()[:1]
        status = "ready" if completed.returncode == 0 else "unusable"
        records.append({
            "tool": requirement.name,
            "status": status,
            "executable": path,
            "exit_code": completed.returncode,
            "version": version_text[0] if version_text else "unknown",
        })
        if status != "ready":
            incomplete.append(requirement.name)
    return {
        "version": VERSION,
        "complete": not incomplete,
        "client_delivery_allowed": False,
        "incomplete_tools": sorted(set(incomplete)),
        "records": records,
    }


def require_complete_preflight(result: Mapping) -> None:
    if not result.get("complete"):
        raise RuntimeError("Scanner preflight incomplete: " + ", ".join(result.get("incomplete_tools") or []))


__all__ = ["DEFAULT_REQUIREMENTS", "ScannerRequirement", "require_complete_preflight", "run_preflight"]
