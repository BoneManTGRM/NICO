from __future__ import annotations

from typing import Any

import nico.assessment_score_integrity as integrity
import nico.assessment_score_integrity_compat as legacy
import nico.exact_snapshot_secret_history as history
import nico.full_assessment_scorecard as scorecard


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _has_structured_history(scanner: dict[str, Any]) -> bool:
    for item in _list(scanner.get("scanner_results")):
        if not isinstance(item, dict):
            continue
        if str(item.get("scanner") or "").lower() not in {"gitleaks", "trufflehog"}:
            continue
        if any(key in item for key in ("execution_completed", "full_history_covered", "history_commit_count")):
            return True
    return False


def compatible_history_secrets_section(repo: dict[str, Any], scanner: dict[str, Any]) -> dict[str, Any]:
    """Use the history model only when the run actually carries its structured fields."""

    if _has_structured_history(scanner):
        return history.history_secrets_section(repo, scanner)
    return legacy.calibrated_secrets_section(repo, scanner)


def install_secret_history_score_compatibility() -> dict[str, Any]:
    installed = bool(getattr(history, "_nico_secret_history_score_compat_installed", False))
    scorecard._secrets_section = compatible_history_secrets_section
    integrity.calibrated_secrets_section = compatible_history_secrets_section
    history._nico_secret_history_score_compat_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "rule": "Legacy scanner records retain their established scoring; exact history scoring activates only when structured depth and execution fields are present.",
    }


__all__ = ["compatible_history_secrets_section", "install_secret_history_score_compatibility"]
