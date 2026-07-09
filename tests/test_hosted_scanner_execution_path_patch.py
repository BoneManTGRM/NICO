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


def test_worker_patch_attaches_tool_stubs_on_blocked(monkeypatch):
    from nico import hosted_scanner_worker

    install_hosted_scanner_execution_path_patch()

    def blocked(payload):
        return {
            "artifact_schema": "nico.scanner_worker.v1",
            "worker_execution_state": "blocked",
            "repository": payload.get("repository"),
            "generated_at": "2026-07-09T18:30:00Z",
            "tools": {},
            "unavailable_data_notes": ["blocked for test"],
        }

    monkeypatch.setattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_execution_path", blocked)
    artifact = hosted_scanner_worker.run_hosted_scanner_worker({"repository": "BoneManTGRM/NICO", "authorized": True, "authorized_by": "frontend-refresh-full-evidence"})

    assert artifact["tools"]["pip-audit"]["status"] == "unavailable"
    assert artifact["tool_records"]
    assert artifact["refresh_full_evidence_requested"] is True
