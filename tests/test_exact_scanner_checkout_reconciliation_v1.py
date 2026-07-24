from __future__ import annotations

from pathlib import Path

from nico.exact_scanner_checkout_reconciliation_v1 import (
    VERSION,
    _checkout_sha_from_result,
    install_exact_scanner_checkout_reconciliation_v1,
)

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40
OTHER_SHA = "b" * 40


def _autorun_result(commit_sha: str = SHA, *, state: str = "completed") -> dict:
    return {
        "status": "complete",
        "scanner_worker_auto_ran": True,
        "scanner_worker_artifact": {
            "worker_execution_state": state,
            "checkout": {
                "commit_sha": commit_sha,
                "history_depth": "full",
                "full_history_secret_scan_requested": True,
            },
        },
    }


def test_completed_local_autorun_checkout_can_reconcile_exact_sha() -> None:
    assert _checkout_sha_from_result(_autorun_result(), SHA) == SHA
    assert _checkout_sha_from_result(_autorun_result(OTHER_SHA), SHA) == ""
    assert _checkout_sha_from_result(_autorun_result(state="checkout_failed"), SHA) == ""


def test_explicit_artifact_cannot_satisfy_autorun_exact_checkout_gate() -> None:
    result = _autorun_result()
    result["scanner_worker_auto_ran"] = False
    assert _checkout_sha_from_result(result, SHA) == ""


def test_installer_retains_safe_checkout_identity_and_remains_fail_closed() -> None:
    from nico import exact_commit_binding as binding
    from nico import hosted_scanner_artifacts as hosted

    status = install_exact_scanner_checkout_reconciliation_v1()
    normalized = hosted.normalize_scanner_worker_artifact(
        {
            "worker_execution_state": "completed",
            "run_id": "scanner_run_test",
            "artifact_hash": "hash_test",
            "checkout": {
                "commit_sha": SHA,
                "returncode": 0,
                "history_depth": "full",
                "full_history_secret_scan_requested": True,
                "commit_count": 42,
                "auth_mode": "github_app",
                "safe_output_preview": "must not be copied",
            },
            "tools": {},
        }
    )

    assert status["version"] == VERSION
    assert status["checkout_identity_retained"] is True
    assert status["completed_autorun_required"] is True
    assert status["exact_sha_match_required"] is True
    assert status["mismatched_or_untrusted_artifacts_blocked"] is True
    assert normalized["checkout"]["commit_sha"] == SHA
    assert normalized["checkout"]["commit_count"] == 42
    assert "safe_output_preview" not in normalized["checkout"]

    accepted = binding._bind_result(
        _autorun_result(),
        repository="BoneManTGRM/NICO",
        commit_sha=SHA,
        requested_sha=SHA,
        scanner_checkout_sha="",
        resolution={"status": "attached", "commit_sha": SHA},
    )
    assert accepted["status"] == "complete"
    assert accepted["exact_commit_binding"]["scanner_checkout_sha"] == SHA
    assert accepted["exact_commit_binding"]["scanner_exact_commit_verified"] is True

    blocked = binding._bind_result(
        _autorun_result(OTHER_SHA),
        repository="BoneManTGRM/NICO",
        commit_sha=SHA,
        requested_sha=SHA,
        scanner_checkout_sha="",
        resolution={"status": "attached", "commit_sha": SHA},
    )
    assert blocked["status"] == "blocked"
    assert blocked["code"] == "exact_scanner_checkout_unverified"


def test_production_bootstrap_enforces_reconciliation_contract() -> None:
    source = (ROOT / "nico" / "api" / "terminal_authority_bootstrap.py").read_text(
        encoding="utf-8"
    )
    assert "install_exact_scanner_checkout_reconciliation_v1" in source
    assert "EXACT_SCANNER_CHECKOUT_RECONCILIATION" in source
    assert 'get("checkout_identity_retained") is not True' in source
    assert 'get("exact_sha_match_required") is not True' in source
    assert 'get("mismatched_or_untrusted_artifacts_blocked") is not True' in source
