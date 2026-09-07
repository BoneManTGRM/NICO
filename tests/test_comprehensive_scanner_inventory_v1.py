from __future__ import annotations

from copy import deepcopy
import gzip
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from nico.specialist_access_v1 import install_specialist_access, issue_specialist_session, PRODUCTION_PROOF_SCOPE

RUN = "comprun_inventory"
COMMIT = "a" * 40
PATH = f"/assessment/comprehensive-run/{RUN}/scanner-evidence"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


@pytest.fixture
def inventory(tmp_path, monkeypatch):
    from nico import comprehensive_scanner_inventory_v1 as module

    monkeypatch.setenv("NICO_ADMIN_TOKEN", "inventory-test-owner")
    monkeypatch.setenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "inventory-test-scoped")
    monkeypatch.setenv("NICO_OPERATOR_SESSION_SIGNING_SECRET", "inventory-test-signing-secret-long-enough")
    monkeypatch.setattr(module, "DEFAULT_RAW_ROOT", str(tmp_path))
    raw = b'{"findings":[{"Secret":"DO-NOT-DISCLOSE-SYNTHETIC-SECRET"}]}'
    compressed = gzip.compress(raw, mtime=0)
    key = f"repo/{COMMIT}/scan/semgrep.gz"
    blob = tmp_path / key
    blob.parent.mkdir(parents=True)
    blob.write_bytes(compressed)
    artifact = {"storage_key": key, "sha256": digest(raw), "gzip_sha256": digest(compressed), "retained_bytes": len(raw), "gzip_bytes": len(compressed), "redacted": True}
    record = {"identity": {"run_id": RUN, "customer_id": "customer-test", "project_id": "project-test", "repository": "example/authorized", "commit_sha": COMMIT}, "revision": 7, "stage_results": {"dependency_security_static_analysis": {"scan_id": "scan_snapshot_inventory"}}}
    scan = {"scan_id": "scan_snapshot_inventory", "run_id": RUN, "customer_id": "customer-test", "project_id": "project-test", "repository": "example/authorized", "snapshot_commit_sha": COMMIT, "actual_commit_sha": COMMIT, "snapshot_match": True, "status": "complete", "tools_requested": ["semgrep"], "scanner_results": [{"tool": "semgrep", "status": "completed", "commit_sha": COMMIT, "snapshot_commit_sha": COMMIT, "raw_artifact": artifact, "artifact_hash": "b" * 64, "scanner_tool_version": "semgrep 1.130.0", "command_intent": "semgrep --config /private/path/rules.yml", "generated_config_sha256": "c" * 64, "configured_rule_count": 6, "returncode": 0, "output_capture_complete": True, "execution_observed_for_this_report": True, "raw_artifact_retention_complete": True, "raw_artifact_sha256": digest(raw), "findings": [{"Secret": "DO-NOT-DISCLOSE-SYNTHETIC-SECRET"}], "stderr": "DO-NOT-DISCLOSE-STDERR"}]}
    calls = {"run": [], "scan": []}

    def load(run_id):
        calls["run"].append(run_id)
        return deepcopy(record)

    def get_scan(scan_id):
        calls["scan"].append(scan_id)
        return deepcopy(scan)

    monkeypatch.setattr(module, "get_scan", get_scan)
    app = FastAPI()
    app.state.comprehensive_api_controller = SimpleNamespace(_service=SimpleNamespace(load_read_only=load))
    install_specialist_access(app)
    module.install_comprehensive_scanner_inventory(app)
    module.install_comprehensive_scanner_inventory(app)
    client = TestClient(app)
    owner, _ = issue_specialist_session({"authority": "nico_admin"})
    return SimpleNamespace(client=client, record=record, scan=scan, calls=calls, blob=blob, tmp_path=tmp_path, module=module, owner={"X-NICO-Operator-Session": owner})


def test_owner_reads_verified_metadata_without_raw_content_or_mutation(inventory):
    before = deepcopy((inventory.record, inventory.scan))
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "inventory_complete"
    assert value["run_id"] == RUN and value["commit_sha"] == COMMIT
    assert value["run_revision"] == 7 and value["read_only"] is True
    assert value["scanner_records"][0]["raw_artifact"]["availability"] == "verified"
    assert value["scanner_records"][0]["scanner_version"] == "1.130.0"
    assert value["scanner_records"][0]["configuration"]["generated_config_sha256"] == "c" * 64
    assert value["scanner_records"][0]["configuration"]["full_configuration_verified"] is False
    assert inventory.calls == {"run": [RUN], "scan": ["scan_snapshot_inventory"]}
    assert (inventory.record, inventory.scan) == before
    text = response.text
    for forbidden in ("DO-NOT-DISCLOSE", "/private/path", "storage_key", "findings", "stderr", str(inventory.tmp_path)):
        assert forbidden not in text
    assert "no-store" in response.headers["cache-control"]


@pytest.mark.parametrize("identity", ["anonymous", "scoped", "proof", "internal"])
def test_nonowners_denied_before_any_run_lookup(inventory, identity):
    headers = {}
    if identity == "scoped":
        token, _ = issue_specialist_session({"authority": "nico_comprehensive_operator"})
        headers = {"X-NICO-Operator-Session": token}
    elif identity == "internal":
        token, _ = issue_specialist_session({"authority": "nico_internal"})
        headers = {"X-NICO-Operator-Session": token}
    elif identity == "proof":
        token, _ = issue_specialist_session({"authority": "nico_admin"}, scope=PRODUCTION_PROOF_SCOPE, retained_claims={"repository": "example/authorized", "ref": "refs/heads/main", "sha": COMMIT, "workflow_ref": "example/authorized/.github/workflows/proof.yml@refs/heads/main", "run_id": "1", "run_attempt": "1"})
        headers = {"X-NICO-Operator-Session": token}
    existing = inventory.client.get(PATH, headers=headers)
    absent = inventory.client.get(PATH.replace(RUN, "comprun_absent"), headers=headers)
    assert existing.status_code in {401, 403}
    assert (existing.status_code, existing.content) == (absent.status_code, absent.content)
    assert inventory.calls == {"run": [], "scan": []}


def test_existing_owner_credential_supported_but_scoped_credential_not_promoted(inventory):
    assert inventory.client.get(PATH, headers={"X-NICO-Admin-Token": "inventory-test-owner"}).status_code == 200
    inventory.calls["run"].clear()
    inventory.calls["scan"].clear()
    assert inventory.client.get(PATH, headers={"X-NICO-Admin-Token": "inventory-test-scoped"}).status_code == 403
    assert inventory.calls == {"run": [], "scan": []}


@pytest.mark.parametrize("field", ["run_id", "customer_id", "project_id", "repository", "snapshot_commit_sha", "actual_commit_sha"])
def test_scanner_source_binding_mismatch_never_reads_blob(inventory, field, monkeypatch):
    inventory.scan[field] = "wrong-source"
    monkeypatch.setattr(inventory.module, "_raw_metadata", lambda *args, **kwargs: pytest.fail("must not touch blob after source mismatch"))
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "scanner_evidence_source_mismatch"
    assert "wrong-source" not in response.text


@pytest.mark.parametrize("change,expected", [("missing", "missing"), ("compressed", "compressed_checksum_mismatch"), ("raw", "raw_checksum_mismatch"), ("unbound", "checksum_unavailable"), ("traversal", "storage_reference_invalid"), ("wrong_record_source", "source_mismatch"), ("oversize", "verification_limit_exceeded")])
def test_incomplete_raw_evidence_is_not_clean(inventory, change, expected, monkeypatch):
    result = inventory.scan["scanner_results"][0]
    if change == "missing": inventory.blob.unlink()
    if change == "compressed": inventory.blob.write_bytes(b"changed")
    if change == "raw": result["raw_artifact"]["sha256"] = "d" * 64; result["raw_artifact_sha256"] = "d" * 64
    if change == "unbound": result["raw_artifact"].pop("gzip_sha256")
    if change == "traversal": result["raw_artifact"]["storage_key"] = "../../outside.gz"
    if change == "wrong_record_source": result["commit_sha"] = "e" * 40
    if change == "oversize": monkeypatch.setattr(inventory.module, "MAX_SCANNER_PARSE_BYTES", 2)
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 200
    value = response.json()
    assert value["status"] == "inventory_incomplete"
    assert value["scanner_records"][0]["raw_artifact"]["availability"] == expected


def test_requested_missing_tool_and_duplicate_records_remain_explicit(inventory):
    inventory.scan["tools_requested"].append("gitleaks")
    inventory.scan["scanner_results"].append(deepcopy(inventory.scan["scanner_results"][0]))
    response = inventory.client.get(PATH, headers=inventory.owner)
    value = response.json()
    assert value["status"] == "inventory_incomplete"
    assert value["scanner_records"][0]["scanner_name"] == "gitleaks"
    assert value["scanner_records"][0]["raw_artifact"]["availability"] == "scanner_record_missing"
    assert len(value["scanner_records"]) == 3
    assert value["duplicate_scanner_record_count"] == 1


def test_native_store_missing_and_unsafe_error_do_not_echo_details(inventory, monkeypatch):
    monkeypatch.setattr(inventory.module, "get_scan", lambda _: {"status": "not_found"})
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "scanner_evidence_unavailable"
    def bad(_): raise RuntimeError("DO-NOT-DISCLOSE-PRIVATE-PATH-OR-CREDENTIAL")
    monkeypatch.setattr(inventory.module, "get_scan", bad)
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 503
    assert "DO-NOT-DISCLOSE" not in response.text


def test_inventory_is_get_only_and_rejects_caller_supplied_storage_selection(inventory):
    assert inventory.client.post(PATH, headers=inventory.owner).status_code == 405
    response = inventory.client.get(PATH + "?scan_id=another&storage_key=anything", headers=inventory.owner)
    assert response.status_code == 422
    assert inventory.calls == {"run": [], "scan": []}


def test_missing_metadata_stays_unknown_and_decompression_is_bounded(inventory, monkeypatch):
    result = inventory.scan["scanner_results"][0]
    result.pop("scanner_tool_version")
    result.pop("output_capture_complete")
    result["raw_artifact"].pop("retained_bytes")
    raw = b"x" * 10000
    compressed = gzip.compress(raw)
    inventory.blob.write_bytes(compressed)
    result["raw_artifact"].update(sha256=digest(raw), gzip_sha256=digest(compressed), gzip_bytes=len(compressed))
    result["raw_artifact_sha256"] = digest(raw)
    monkeypatch.setattr(inventory.module, "MAX_SCANNER_PARSE_BYTES", 1000)
    response = inventory.client.get(PATH, headers=inventory.owner)
    row = response.json()["scanner_records"][0]
    assert row["scanner_version"] is None
    assert row["output_capture_complete"] is None
    assert row["raw_artifact"]["declared_raw_bytes"] is None
    assert row["raw_artifact"]["availability"] == "verification_limit_exceeded"
    assert row["raw_artifact"]["actual_raw_bytes"] is None
    assert row["raw_artifact"]["observed_raw_bytes"] == 1001
    inventory.scan.pop("scanner_results")
    assert inventory.client.get(PATH, headers=inventory.owner).json()["scanner_record_count"] is None


def test_symlink_escape_is_rejected_and_unknown_tool_names_not_echoed(inventory):
    outside = inventory.tmp_path.parent / "inventory-other-private-file"
    outside.write_bytes(b"synthetic private content")
    inventory.blob.unlink()
    inventory.blob.symlink_to(outside)
    inventory.scan["scanner_results"].append({"tool": "DO-NOT-DISCLOSE-UNKNOWN-TOOL"})
    response = inventory.client.get(PATH, headers=inventory.owner)
    value = response.json()
    assert value["scanner_records"][0]["raw_artifact"]["availability"] == "storage_reference_invalid"
    assert value["unknown_scanner_record_count"] == 1
    assert "DO-NOT-DISCLOSE" not in response.text


def test_ambiguous_run_scanner_reference_blocks_lookup(inventory):
    inventory.record["stage_results"]["deep_scanner_triage"] = {"scan_id": "scan_another"}
    response = inventory.client.get(PATH, headers=inventory.owner)
    assert response.status_code == 409
    assert inventory.calls["scan"] == []
