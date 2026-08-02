from __future__ import annotations

from nico.comprehensive_pre_render_scanner_truth_v64 import (
    canonicalize_stage_results_before_render,
)

TOOLS = [
    "pip-audit",
    "npm-audit",
    "osv-scanner",
    "bandit",
    "semgrep",
    "eslint",
    "typescript",
    "gitleaks",
    "trufflehog",
]


def test_unknown_incomplete_alias_and_generic_blocker_are_never_silently_removed() -> None:
    stages = {
        "dependency_security_static_analysis": {
            "status": "complete",
            "scanner": {
                "status": "complete",
                "tools_requested": list(TOOLS),
                "tools_run": list(TOOLS),
                "failed_tools": [],
                "unavailable_tools": [],
                "timed_out_tools": [],
            },
            "evidence": {
                "incomplete_analyzers": [
                    "pip-audit",
                    "unidentified custom analyzer evidence requires review",
                ],
                "analyzer_evidence_blockers": [
                    "pip-audit retained an obsolete copied blocker",
                    "An unidentified analyzer result could not be classified.",
                ],
                "flattened": [
                    "contract.incomplete_analyzers[0]: pip-audit",
                    "contract.incomplete_analyzers[1]: unidentified custom analyzer result",
                ],
            },
        }
    }

    cleaned, manifest = canonicalize_stage_results_before_render(stages)
    evidence = cleaned["dependency_security_static_analysis"]["evidence"]

    assert manifest["incomplete"] == []
    assert evidence["incomplete_analyzers"] == [
        "unidentified custom analyzer evidence requires review"
    ]
    assert evidence["analyzer_evidence_blockers"] == [
        "An unidentified analyzer result could not be classified."
    ]
    assert evidence["flattened"] == [
        "contract.incomplete_analyzers[1]: unidentified custom analyzer result"
    ]
    assert manifest["unknown_evidence_preserved_fail_closed"] is True
    assert manifest["removed_stale_alias_count"] == 3
