from nico.hosted_scanner_execution_path_patch import _ensure_tool_records, install_hosted_scanner_execution_path_patch
from nico.hosted_full_evidence_runtime_v2 import _payload_for_result, _raw_artifact


def test_blocked_artifact_gets_required_tool_records():
    artifact = {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "checkout_failed",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T18:30:00Z",
        "tools": {},
        "unavailable_data_notes": ["Hosted scanner worker could not check out the authorized repository."],
    }

    updated = _ensure_tool_records(artifact)
    records = {item["tool"]: item for item in updated["tool_records"]}

    assert records["pip-audit"]["status"] == "unavailable"
    assert records["pip-audit"]["reason"]
    assert records["trufflehog"]["status"] == "unavailable"
    assert updated["tools"]["semgrep"]["category"] == "static"


def test_runtime_raw_artifact_accepts_unavailable_tool_records():
    install_hosted_scanner_execution_path_patch()
    artifact = _ensure_tool_records(
        {
            "artifact_schema": "nico.scanner_worker.v1",
            "worker_execution_state": "blocked",
            "generated_at": "2026-07-09T18:30:00Z",
            "tools": {},
            "unavailable_data_notes": ["auto-run disabled"],
        }
    )

    assert _raw_artifact({"scanner_worker_artifact": artifact}) is artifact


def test_runtime_payload_for_result_preserves_refresh_execution_flags():
    install_hosted_scanner_execution_path_patch()
    payload = _payload_for_result(
        {
            "repository": "BoneManTGRM/NICO",
            "authorized_by": "frontend-refresh-full-evidence",
            "repository_metadata": {"default_branch": "main"},
        }
    )

    assert payload["authorized"] is True
    assert payload["refresh_full_evidence_requested"] is True
    assert payload["run_scanner_worker"] is True
    assert payload["scanner_worker_autorun"] is True
    assert payload["full_history_secret_scan"] is True
    assert payload["default_branch"] == "main"


def test_ensure_tool_records_preserves_completed_tool_payloads():
    artifact = {
        "artifact_schema": "nico.scanner_worker.v1",
        "worker_execution_state": "completed",
        "repository": "BoneManTGRM/NICO",
        "generated_at": "2026-07-09T18:30:00Z",
        "tools": {
            "bandit": {
                "tool": "bandit",
                "status": "completed",
                "category": "static",
                "returncode": 1,
                "findings": [{"test_id": "B101"}],
            }
        },
    }

    updated = _ensure_tool_records(artifact)
    records = {item["tool"]: item for item in updated["tool_records"]}

    assert updated["tools"]["bandit"]["status"] == "completed"
    assert records["bandit"]["findings_count"] == 1
    assert records["bandit"]["verified_for_this_report"] is True
    assert records["pip-audit"]["status"] == "unavailable"
