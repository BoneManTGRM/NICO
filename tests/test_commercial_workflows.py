from fastapi.testclient import TestClient

from nico.api.main import app
from nico.approval_queue import create_approval, draft_pr_request, transition_approval
from nico.customer_access import can
from nico.evidence import validate_content_type
from nico.repair_intelligence import repair_quality_policy, suggest_repair
from nico.scanner_worker import SHELL_EXECUTION_ALLOWED, redact, start_scan
from nico.storage import STORE
from nico.tenancy import authorization_record, enforce_scope


def authorized_scan_payload():
    return {
        "authorized": True,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "c1",
        "project_id": "p1",
        "authorized_by": "tester",
        "authorization_scope": "repository assessment only",
        "tools": ["definitely-not-installed"],
    }


def test_worker_scan_requires_authorization():
    result = start_scan({"authorized": False, "repository": "BoneManTGRM/NICO"})
    assert result["status"] == "blocked"


def test_worker_scan_requires_authorized_by():
    result = start_scan({"authorized": True, "repository": "BoneManTGRM/NICO", "authorization_scope": "repo"})
    assert result["status"] == "blocked"
    assert "authorized_by" in result["error"]


def test_worker_scan_records_safe_job():
    result = start_scan(authorized_scan_payload())
    assert result["status"] in {"queued", "running", "complete"}
    assert result["code_modification_allowed"] is False
    assert result["scan_id"].startswith("scan_")
    assert result["human_review_required"] is True


def test_scanner_redacts_sensitive_output_and_disables_shell():
    output, changed = redact("token='abc12345678900000000'\nnormal line")
    assert changed is True
    assert "abc12345678900000000" not in output
    assert SHELL_EXECUTION_ALLOWED is False


def test_approval_queue_blocks_draft_pr_without_approval():
    item = create_approval({"customer_id": "c1", "project_id": "p1", "requested_action": "draft_pr"})
    blocked = draft_pr_request({"approval_id": item["approval_id"], "repository": "BoneManTGRM/NICO"})
    assert blocked["status"] == "blocked"


def test_approval_queue_allows_draft_pr_stub_after_approval():
    item = create_approval({"customer_id": "c1", "project_id": "p1", "requested_action": "draft_pr"})
    approved = transition_approval(item["approval_id"], "approved", actor="tester")
    assert approved["status"] == "approved"
    draft = draft_pr_request({"approval_id": item["approval_id"], "repository": "BoneManTGRM/NICO"})
    assert draft["status"] == "unavailable"
    assert draft["approval_id"] == item["approval_id"]


def test_repair_intelligence_suggests_evidence_bound_fix():
    result = suggest_repair({
        "issue": "missing dependency causes test failure",
        "evidence": ["CI reports missing package"],
        "affected_files": ["requirements.txt"],
        "customer_id": "c1",
        "project_id": "p1",
    })
    assert result["status"] == "complete"
    assert result["human_review_required"] is True
    assert result["strategy"] == "dependency_or_runtime_contract_fix"
    assert result["root_cause_hypothesis"]
    assert result["patch_steps"]
    assert result["patch_prompt"]
    assert result["test_plan"]
    assert result["rollback_plan"]
    policy = repair_quality_policy()
    assert policy["status"] == "ok"
    assert policy["quality_checklist"]


def test_storage_fallback_and_schema_available():
    status = STORE.status()
    assert "persistence_available" in status
    assert "CREATE TABLE" in STORE.schema()


def test_evidence_file_validation():
    ok, _ = validate_content_type("text/plain")
    assert ok is True
    ok, message = validate_content_type("application/x-msdownload")
    assert ok is False
    assert "Unsupported" in message


def test_tenant_scope_helpers():
    item = {"customer_id": "c1", "project_id": "p1"}
    assert enforce_scope(item, customer_id="c1", project_id="p1") is True
    assert enforce_scope(item, customer_id="c2") is False
    record = authorization_record({"customer_id": "c1", "project_id": "p1", "repository": "BoneManTGRM/NICO", "authorized_by": "tester"})
    assert record["authorized_by"] == "tester"
    assert record["authorized_target"] == "BoneManTGRM/NICO"


def test_customer_roles():
    assert can("owner", "scan") is True
    assert can("viewer", "approve") is False


def test_health_targets_worker_and_usage_endpoints():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    targets = client.get("/targets")
    assert targets.status_code == 200
    assert "coverage_targets" in targets.json()
    scan = client.post("/worker/scan", json=authorized_scan_payload())
    assert scan.status_code == 200
    assert scan.json()["scan_id"].startswith("scan_")
    guide = client.get("/usage/guide")
    assert guide.status_code == 200
    assert guide.json()["status"] == "ok"
    assert "How to Use NICO" in guide.json()["content"]
