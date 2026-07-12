from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable

import nico.assessment_score_integrity as score_integrity
import nico.full_assessment_scorecard as scorecard

TYPESCRIPT_VALIDATION_VERSION = "nico-typescript-validation-bridge-v1"
_DELEGATE_STATIC_SECTION: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]] | None = None


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _scanner_result(scanner: dict[str, Any], name: str) -> dict[str, Any]:
    for item in _list(scanner.get("scanner_results")):
        if isinstance(item, dict) and str(item.get("scanner") or "").lower() == name:
            return item
    return {}


def ci_typescript_validation(repo: dict[str, Any]) -> dict[str, Any]:
    workflows = _dict(repo.get("workflow_evidence"))
    commands = [str(item).strip().lower() for item in _list(workflows.get("commands_detected"))]
    successes = _int(workflows.get("successful_runs"))
    recognized = [
        command
        for command in commands
        if "npm run lint" in command or "tsc --noemit" in command.replace(" ", "") or command == "tsc"
    ]
    return {
        "completed": bool(recognized and successes > 0),
        "commands": recognized,
        "successful_workflow_runs": successes,
    }


def static_section_with_typescript_validation(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    if _DELEGATE_STATIC_SECTION is None:
        raise RuntimeError("Static score delegate is unavailable.")
    section = deepcopy(_DELEGATE_STATIC_SECTION(repo, scanner))
    eslint = _scanner_result(scanner, "eslint")
    eslint_completed = str(eslint.get("status") or "") == "passed"
    validation = ci_typescript_validation(repo)
    completed = bool(validation.get("completed"))
    evidence = [str(item) for item in _list(section.get("evidence"))]
    unavailable = [str(item) for item in _list(section.get("unavailable"))]
    if completed:
        commands = ", ".join(validation.get("commands") or [])
        evidence.append(
            f"CI-backed TypeScript validation completed through {commands or 'the frontend lint/typecheck command'} with "
            f"{validation.get('successful_workflow_runs')} successful workflow run(s)."
        )
        unavailable = [
            item
            for item in unavailable
            if "javascript/typescript semantic lint coverage remains unavailable" not in item.lower()
        ]
        if not eslint_completed:
            unavailable.append(
                "CI-backed TypeScript compilation/typechecking is available, but it is not equivalent to exact-snapshot ESLint rule coverage."
            )
        material = _int(_dict(section.get("static_triage")).get("material_finding_count"))
        if not material:
            section["score"] = min(90, _int(section.get("score")) + 4)
    section["status"] = "green" if _int(section.get("score")) >= 80 else "yellow" if _int(section.get("score")) >= 55 else "red"
    section["evidence"] = list(dict.fromkeys(evidence))
    section["verified_claims"] = section["evidence"]
    section["unavailable"] = list(dict.fromkeys(unavailable))
    section["unverified_claims"] = section["unavailable"]
    triage = deepcopy(_dict(section.get("static_triage")))
    triage["typescript_validation"] = {
        "version": TYPESCRIPT_VALIDATION_VERSION,
        "ci_backed_completed": completed,
        "commands": list(validation.get("commands") or []),
        "successful_workflow_runs": _int(validation.get("successful_workflow_runs")),
        "eslint_exact_snapshot_completed": eslint_completed,
    }
    section["static_triage"] = triage
    return section


def install_typescript_validation_bridge() -> dict[str, Any]:
    global _DELEGATE_STATIC_SECTION
    installed = bool(getattr(scorecard, "_nico_typescript_validation_bridge_installed", False))
    if not installed:
        _DELEGATE_STATIC_SECTION = scorecard._static_section
    scorecard._static_section = static_section_with_typescript_validation
    score_integrity.calibrated_static_section = static_section_with_typescript_validation
    scorecard._nico_typescript_validation_bridge_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": TYPESCRIPT_VALIDATION_VERSION,
        "rule": "Successful CI-backed TypeScript validation is evidence of compilation/typecheck coverage but is never represented as exact-snapshot ESLint coverage.",
    }


__all__ = [
    "TYPESCRIPT_VALIDATION_VERSION",
    "ci_typescript_validation",
    "install_typescript_validation_bridge",
    "static_section_with_typescript_validation",
]
