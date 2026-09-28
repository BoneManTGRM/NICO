"""Exercise C++ selection through the installed Comprehensive provider."""
from copy import deepcopy

import pytest
from fastapi import FastAPI

from nico import comprehensive_native_providers as native
from nico.comprehensive_native_providers_v5 import install_native_comprehensive_providers


RELEASE = "a" * 40
COMMIT = "b" * 40
TREE = "c" * 40
IMAGE = "sha256:" + "d" * 64


@pytest.fixture
def configured(monkeypatch):
    settings = {
        "NICO_CPP_CONFIGURE_FIRST_ENABLED": "1",
        "NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED": "1",
        "NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID": IMAGE,
        "NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE": RELEASE,
        "NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_RUN_ID": "12345",
        "NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256": "e" * 64,
    }
    for key, value in settings.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("nico.github_actions_proof_auth_v1.expected_release_sha", lambda: RELEASE)
    observed = []

    def start(payload, **kwargs):
        observed.append((deepcopy(payload), deepcopy(kwargs)))
        return {"status": "queued", "scan_id": "scan_selected"}

    monkeypatch.setattr(native, "start_snapshot_scan", start)
    provider = install_native_comprehensive_providers(FastAPI())["scanner_suite"]
    return provider, observed


def context(runtime=False):
    paths = ["CMakeLists.txt", "src/main.cpp"]
    if runtime:
        paths += ["test/functional/test_runner.py", "test/fuzz/test_runner.py",
                  "src/test/fuzz/CMakeLists.txt", "src/test/fuzz/connect_block.cpp"]
    snapshot = {
        "status": "attached", "provider": "github", "repository": "example/project",
        "snapshot_id": "snapshot_cpp", "commit_sha": COMMIT, "tree_sha": TREE,
        "exact_commit_verified": True, "access_mode": "anonymous_public",
        "credential_used": False,
    }
    evidence = {"execution_input_manifest": {
        "schema": "nico.snapshot-execution-inputs.v1", "snapshot_commit_sha": COMMIT,
        "snapshot_tree_sha": TREE, "snapshot_identity_verified": True,
        "inventory_complete": True, "inventory_paths": paths,
    }}
    return {
        "run_id": "comprun_cpp_selection", "repository": "example/project",
        "commit_sha": COMMIT, "evidence_ledger_id": "ledger_cpp",
        "customer_id": "customer_cpp", "project_id": "project_cpp",
        "prior_stage_results": {
            "immutable_repository_snapshot": {"status": "complete", "snapshot": snapshot},
            "repository_and_delivery_evidence": {"status": "complete", "repository_evidence": evidence},
        },
    }


@pytest.mark.parametrize("runtime", [False, True])
def test_comprehensive_enqueues_the_qualified_cpp_child(configured, runtime):
    provider, observed = configured
    original = context(runtime)
    before = deepcopy(original)
    result = provider(original)
    assert result["status"] == "running"
    assert result["client_delivery_allowed"] is False
    payload, kwargs = observed[0]
    contract = kwargs["cpp_contract"]
    assert contract["profile"] == "cpp-configure-first-v2"
    assert contract["image_digest"] == IMAGE
    assert contract["configuration"]["expected_tree_sha"] == TREE
    assert contract["configuration"]["baseline_execution"]["schema"] == "nico.cpp-baseline-execution.v2"
    assert ("runtime_scope" in contract["configuration"]) is runtime
    assert payload["snapshot_commit_sha"] == COMMIT
    assert payload["provider_access_mode"] == "anonymous_public"
    assert payload["provider_credential_used"] is False
    assert original == before


@pytest.mark.parametrize("fault", [
    "disabled", "dispatch_disabled", "wrong_release", "image_missing", "qualification_missing",
    "private", "incomplete_inventory", "wrong_tree", "wrong_commit", "not_cpp", "stage_incomplete",
])
def test_comprehensive_does_not_dispatch_unqualified_cpp(configured, monkeypatch, fault):
    provider, observed = configured
    value = context()
    stages = value["prior_stage_results"]
    snapshot = stages["immutable_repository_snapshot"]["snapshot"]
    manifest = stages["repository_and_delivery_evidence"]["repository_evidence"]["execution_input_manifest"]
    if fault == "disabled":
        monkeypatch.delenv("NICO_CPP_CONFIGURE_FIRST_ENABLED")
    elif fault == "dispatch_disabled":
        monkeypatch.setenv("NICO_ASSESSMENT_WORKER_DISPATCH_ENABLED", "0")
    elif fault == "wrong_release":
        monkeypatch.setenv("NICO_CPP_CONFIGURE_FIRST_QUALIFIED_RELEASE", "f" * 40)
    elif fault == "image_missing":
        monkeypatch.delenv("NICO_CPP_CONFIGURE_FIRST_IMAGE_CONFIG_ID")
    elif fault == "qualification_missing":
        monkeypatch.delenv("NICO_CPP_CONFIGURE_FIRST_QUALIFICATION_ARTIFACT_SHA256")
    elif fault == "private":
        snapshot.update(access_mode="authenticated_read_only", credential_used=True)
    elif fault == "incomplete_inventory":
        manifest["inventory_complete"] = False
    elif fault == "wrong_tree":
        manifest["snapshot_tree_sha"] = "f" * 40
    elif fault == "wrong_commit":
        manifest["snapshot_commit_sha"] = "f" * 40
    elif fault == "not_cpp":
        manifest["inventory_paths"] = ["README.md", "app.py"]
    else:
        stages["repository_and_delivery_evidence"]["status"] = "running"
    # Caller-controlled fields must not substitute a qualified internal contract.
    value["cpp_contract"] = {"profile": "untrusted"}
    value["worker_contract"] = {"profile": "untrusted"}
    result = provider(value)
    assert result["status"] == "running"
    assert observed[0][1] == {}
    assert "cpp_contract" not in observed[0][0]
    assert "worker_contract" not in observed[0][0]


def test_existing_failed_scan_is_preserved_without_reselection_or_new_dispatch(configured, monkeypatch):
    provider, observed = configured
    value = context(True)
    value["prior_stage_results"]["dependency_security_static_analysis"] = {"scan_id": "scan_failed"}
    monkeypatch.setattr(native, "get_scan", lambda scan_id: {
        "scan_id": scan_id, "status": "unavailable", "snapshot_match": False,
        "unavailable_data_notes": ["retained checkout failure"],
    })
    monkeypatch.setattr("nico.assessment_cpp_production_selection.select_configure_first_contract",
                        lambda *args, **kwargs: pytest.fail("must not reselect an existing scan"))
    result = provider(value)
    assert result["status"] == "blocked"
    assert result["reason"] == "snapshot_scanner_not_verified"
    assert result["scan_id"] == "scan_failed"
    assert result["unavailable_data_notes"] == ["retained checkout failure"]
    assert observed == []
