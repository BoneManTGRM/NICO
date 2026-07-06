from fastapi.testclient import TestClient

from nico.api.main import app
from nico.approval_queue import create_approval, draft_pr_request, transition_approval
from nico.customer_access import can
from nico.evidence import validate_content_type
from nico.scanner_worker import start_scan
from nico.storage import STORE
from nico.tenancy import authorization_record, enforce_scope


def test_worker_scan_requires_authorization():
    result = start_scan({"authorized": False, "repository": "BoneManTGRM/NICO"})
    assert result["status"] == "blocked"


def test_worker_scan_records_safe_mvp_job():
    result = start_scan({"authorized": True, "repository": "BoneManTGRM/NICO", "customer_id": "c1", "project_id": "p1"})
    assert result["status"] in {"queued", "running", "complete"}
    assert result["code_modification_allowed"] is False
    assert result["scan_id"].startswith("scan_")


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


def test_health_and_targets_endpoints():
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"
    targets = client.get("/targets")
    assert targets.status_code == 200
    assert "coverage_targets" in targets.json()
