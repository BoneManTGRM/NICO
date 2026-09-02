from __future__ import annotations

from typing import Any

from nico.comprehensive_run_service import _prior_stage_results_for_stage


class _NoDeepcopy:
    def __deepcopy__(self, _memo: dict[int, Any]) -> "_NoDeepcopy":
        raise AssertionError("large retained scanner evidence must not be copied")


def test_deep_scanner_triage_uses_only_scan_identity_and_poll_marker() -> None:
    retained = {
        "authorization_and_scope": {"large_unrelated_payload": _NoDeepcopy()},
        "dependency_security_static_analysis": {
            "status": "complete",
            "scan_id": "scan_exact_sha_123",
            "scanner": {
                "status": "complete",
                "scan_id": "scan_exact_sha_123",
                "scanner_results": _NoDeepcopy(),
            },
            "evidence": _NoDeepcopy(),
        },
        "deep_scanner_triage": {
            "status": "running",
            "reason": "background_stage_execution_in_progress",
            "summary": "Scanner triage continues in the background.",
            "stage_progress_percent": 41,
            "stage_execution": {
                "task_id": "comprehensive_stage_exact",
                "background_poll_iteration": 3,
            },
            "scanner": _NoDeepcopy(),
            "evidence": _NoDeepcopy(),
        },
    }

    projected = _prior_stage_results_for_stage(
        "deep_scanner_triage",
        retained,
        [
            "authorization_and_scope",
            "dependency_security_static_analysis",
        ],
    )

    assert projected == {
        "dependency_security_static_analysis": {
            "scan_id": "scan_exact_sha_123",
            "scanner": {
                "scan_id": "scan_exact_sha_123",
                "status": "complete",
            },
        },
        "deep_scanner_triage": {
            "status": "running",
            "reason": "background_stage_execution_in_progress",
            "summary": "Scanner triage continues in the background.",
            "stage_progress_percent": 41,
            "stage_execution": {
                "task_id": "comprehensive_stage_exact",
                "background_poll_iteration": 3,
            },
        },
    }


def test_deep_scanner_triage_supports_nested_only_scan_identity() -> None:
    projected = _prior_stage_results_for_stage(
        "deep_scanner_triage",
        {
            "dependency_security_static_analysis": {
                "scanner": {
                    "scan_id": "scan_nested_only",
                    "status": "complete",
                }
            }
        },
        ["dependency_security_static_analysis"],
    )

    assert projected == {
        "dependency_security_static_analysis": {
            "scanner": {
                "scan_id": "scan_nested_only",
                "status": "complete",
            }
        }
    }
