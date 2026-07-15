from __future__ import annotations

from typing import Any

_COMPAT_MARKER = "_nico_complexity_score_integrity_compat_v1"


def _dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def install_complexity_score_integrity_compat() -> dict[str, Any]:
    """Preserve the legacy attachment marker without overwriting measured profiles.

    Older report-state tests and consumers expect a `complexity_engine` key whenever
    all complexity tools are attached. The evidence-integrity patch deliberately does
    not treat artifact presence as score-eligible proof. This wrapper retains the
    non-scoring key only when no measured profile was selected.
    """

    from nico import evidence_status

    current = evidence_status._apply_complexity_language
    if getattr(current, _COMPAT_MARKER, False):
        return {
            "status": "already_installed",
            "placeholder_score_eligible": False,
            "measured_profile_overwrite_allowed": False,
        }

    original = current

    def apply_complexity_language_with_attachment_compat(
        result: dict[str, Any],
        status: dict[str, Any],
    ) -> None:
        original(result, status)
        tools = _dict(status.get("complexity_tools"))
        tools_complete = bool(tools) and all(
            isinstance(tool, dict) and tool.get("status") == "completed_clean"
            for tool in tools.values()
        )
        if not tools_complete or isinstance(result.get("complexity_engine"), dict):
            return
        result["complexity_engine"] = {
            "status": "attached",
            "source": "current-run scanner artifact evidence",
            "artifact": "complexity-profile.json",
            "risk_level": "review_required",
            "score_eligible": False,
            "guardrail": (
                "Artifact presence confirms attachment only. Positive same-run analyzed-file, "
                "LOC, and function-unit measurements are required for scoring."
            ),
        }

    setattr(apply_complexity_language_with_attachment_compat, _COMPAT_MARKER, True)
    setattr(apply_complexity_language_with_attachment_compat, "_nico_previous", original)
    evidence_status._apply_complexity_language = apply_complexity_language_with_attachment_compat
    return {
        "status": "installed",
        "placeholder_score_eligible": False,
        "measured_profile_overwrite_allowed": False,
    }


__all__ = ["install_complexity_score_integrity_compat"]
