from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any, Callable

PATCH_VERSION = "nico.language_aware_pattern_reconciliation.v1"
_PATCH_MARKER = "_nico_language_aware_pattern_reconciliation_v1"
_SCRIPT_EXTENSIONS = {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"}


def _finding_path(note: str) -> str:
    text = str(note or "").strip()
    if not text:
        return ""
    # Findings use `path:line: rule - description`. Split from the right so
    # Windows drive letters or other colons in prose do not affect the suffix.
    prefix = text.split(" - ", 1)[0]
    parts = prefix.rsplit(":", 2)
    return parts[0].strip().replace("\\", "/") if len(parts) >= 2 else ""


def _is_cross_language_python_exec_hit(note: str) -> bool:
    lower = str(note or "").lower()
    path = _finding_path(note)
    suffix = PurePosixPath(path).suffix.lower()
    return "python_eval_exec" in lower and suffix in _SCRIPT_EXTENSIONS


def install_language_aware_pattern_reconciliation() -> dict[str, Any]:
    """Prevent Python eval/exec rules from scoring JavaScript RegExp.exec calls.

    The built-in textual scanner can see `.exec(` inside JavaScript or TypeScript
    and label it with the Python-only `python_eval_exec` rule. That is a language
    mismatch, not evidence of Python dynamic execution. The finding remains
    available as review metadata but is excluded from production-risk scoring.
    """

    from nico import assessment_quality

    current: Callable[[str], str] = assessment_quality._classify_static_hit
    if getattr(current, _PATCH_MARKER, False):
        return {
            "status": "already_installed",
            "version": PATCH_VERSION,
            "cross_language_python_exec_scored": False,
        }

    def classify_language_aware(note: str) -> str:
        if _is_cross_language_python_exec_hit(note):
            return "language_rule_mismatch"
        return current(note)

    setattr(classify_language_aware, _PATCH_MARKER, True)
    setattr(classify_language_aware, "_nico_previous", current)
    assessment_quality._classify_static_hit = classify_language_aware
    return {
        "status": "installed",
        "version": PATCH_VERSION,
        "script_extensions": sorted(_SCRIPT_EXTENSIONS),
        "cross_language_python_exec_scored": False,
        "evidence_retained_for_review": True,
        "human_review_required": True,
    }


__all__ = [
    "PATCH_VERSION",
    "_finding_path",
    "_is_cross_language_python_exec_hit",
    "install_language_aware_pattern_reconciliation",
]
