from nico.approvals.store import ApprovalDecision, ApprovalRequest, LocalApprovalSQLiteStore
from nico.audit.local_sqlite import LocalAuditRecord, LocalAuditSQLiteStore


def test_local_audit_sqlite_masks_and_reads(tmp_path):
    db_path = tmp_path / "nico.sqlite3"
    store = LocalAuditSQLiteStore(db_path)
    record = store.append(LocalAuditRecord(action="demo", detail={"token": "DEMO_PLACEHOLDER_VALUE"}))
    assert "DEMO_PLACEHOLDER_VALUE" not in str(record)
    latest = store.latest()
    assert latest
    assert "DEMO_PLACEHOLDER_VALUE" not in str(latest)


def test_local_approval_sqlite_pending_and_decision(tmp_path):
    db_path = tmp_path / "nico.sqlite3"
    store = LocalApprovalSQLiteStore(db_path)
    store.create_request(ApprovalRequest(request_id="demo-approval", action="report_export", detail={"token": "DEMO_PLACEHOLDER_VALUE"}))
    pending = store.pending()
    assert len(pending) == 1
    assert "DEMO_PLACEHOLDER_VALUE" not in str(pending)
    decision = store.decide(ApprovalDecision(request_id="demo-approval", decision="approved"))
    assert decision["decision"] == "approved"
    assert store.pending() == []
