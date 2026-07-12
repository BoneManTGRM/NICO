from __future__ import annotations

import re
from typing import Any

import nico.assessment_score_integrity as score_integrity

TYPESCRIPT_COMPLEXITY_SYNTAX_VERSION = "nico-typescript-complexity-syntax-v1"

_BRANCH_PATTERNS = (
    r"\bif\s*\(",
    r"\bfor\s*\(",
    r"\bwhile\s*\(",
    r"\bcase\b",
    r"\bcatch\s*\(",
    r"\?\?",
    r"&&",
    r"\|\|",
    # A ternary question mark is a branch. TypeScript optional properties and
    # optional parameters use `?:` and are type syntax, not runtime branches.
    # Optional chaining (`?.`) and nullish coalescing (`??`) are handled
    # separately and must not be counted again here.
    r"\?(?![?.:])",
)


def count_runtime_branches(text: str) -> int:
    return sum(len(re.findall(pattern, str(text or ""))) for pattern in _BRANCH_PATTERNS)


def install_typescript_complexity_syntax() -> dict[str, Any]:
    installed = bool(getattr(score_integrity, "_nico_typescript_complexity_syntax_installed", False))
    score_integrity._branch_count = count_runtime_branches
    score_integrity._nico_typescript_complexity_syntax_installed = True
    return {
        "status": "already_installed" if installed else "installed",
        "version": TYPESCRIPT_COMPLEXITY_SYNTAX_VERSION,
        "rule": "TypeScript optional property and parameter markers are excluded from runtime cyclomatic complexity; ternaries, nullish coalescing, logical branches, loops, conditions, cases, and catches remain counted.",
    }


__all__ = [
    "TYPESCRIPT_COMPLEXITY_SYNTAX_VERSION",
    "count_runtime_branches",
    "install_typescript_complexity_syntax",
]
