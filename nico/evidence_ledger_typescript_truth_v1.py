from __future__ import annotations

from functools import wraps
from typing import Callable

from nico import evidence_ledger


VERSION = "nico.evidence_ledger_typescript_truth.v1"
_MARKER = "_nico_evidence_ledger_typescript_truth_v1"

# Language, parser, and complexity evidence must not be promoted into proof that
# the TypeScript type-checker/static analyzer executed. Structured scanner
# artifacts already bypass the text classifier and remain authoritative.
_EXPLICIT_EXECUTION_MARKERS = (
    "typescript scanner execution",
    "typescript analyzer execution",
    "typescript type-check execution",
    "typescript typecheck execution",
    "typescript compiler check execution",
    "tsc execution",
    "tsc --noemit",
    "tsc --noemit",
)
_NON_EXECUTION_MARKERS = (
    "typescript ast",
    "typescript compiler ast",
    "typescript parser",
    "javascript and typescript metrics",
    "javascript/typescript metrics",
    "typescript complexity",
    "typescript source",
    "typescript files",
)


def _strict_text_detector(
    delegate: Callable[[str], str | None],
) -> Callable[[str], str | None]:
    @wraps(delegate)
    def detect(text: str) -> str | None:
        tool = delegate(text)
        if tool != "typescript":
            return tool

        lowered = str(text or "").casefold()
        if any(marker in lowered for marker in _NON_EXECUTION_MARKERS):
            return None
        if any(marker in lowered for marker in _EXPLICIT_EXECUTION_MARKERS):
            return "typescript"

        # A bare language mention is not tool-execution evidence. Explicit
        # structured scanner records with tool=typescript are handled separately
        # by evidence_ledger._scanner_artifact_entries and are not affected here.
        return None

    setattr(detect, _MARKER, True)
    setattr(detect, "_nico_previous", delegate)
    return detect


def install_evidence_ledger_typescript_truth_v1() -> dict[str, object]:
    current = evidence_ledger._detect_tool_from_text
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": VERSION,
            "generic_language_mentions_verify_tool": False,
            "structured_scanner_artifacts_remain_authoritative": True,
        }

    evidence_ledger._detect_tool_from_text = _strict_text_detector(current)
    return {
        "status": "installed",
        "version": VERSION,
        "generic_language_mentions_verify_tool": False,
        "structured_scanner_artifacts_remain_authoritative": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_evidence_ledger_typescript_truth_v1"]
