from __future__ import annotations

from typing import Any

from nico.comprehensive_truth_reconciliation_v7 import (
    DISPOSITION_MODEL,
    SCORING_MODEL,
    VERSION,
    WORKFLOW_MODEL,
    install_comprehensive_truth_reconciliation_v7 as _install,
)

_INSTALLED = False
_RESULT: dict[str, Any] = {}


def install_comprehensive_truth_reconciliation_v7() -> dict[str, Any]:
    global _INSTALLED, _RESULT
    if _INSTALLED:
        return {
            **_RESULT,
            "status": "already_installed",
            "reentry_guarded": True,
        }
    _RESULT = dict(_install())
    _RESULT["reentry_guarded"] = True
    _INSTALLED = True
    return dict(_RESULT)


__all__ = [
    "DISPOSITION_MODEL",
    "SCORING_MODEL",
    "VERSION",
    "WORKFLOW_MODEL",
    "install_comprehensive_truth_reconciliation_v7",
]
