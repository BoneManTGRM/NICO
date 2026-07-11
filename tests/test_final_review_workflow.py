from nico import final_review_workflow as review


def test_request_final_review_creates_pending_approval(monkeypatch):
    approvals = []

    def fake_create(payload):
        item = {
            "approval_id": "approval_review_1",
            "status": "pending",
            "approver": "",
            "audit_log": [],
            **payload,
        }
        return item

    def fake_put(table, item_id, payload):
        if table == "approvals":
            approvals.append(dict(payload))
        return payload

    def fake_list(table, customer_id=None, project_id=None):
        if table == "assessment_runs":
            return [
                {
                    "id": "2026-07-07T15_00_00Z",
                    "workflow": "express",
                    "customer_id": "default_customer",
                    "project_id": "default_project",
                    "payload": {
                        "status": "complete",
                        "generated_at": "2026-07-07T15:00:00Z",
                        "repository": "BoneManTGRM/NICO",
                        "maturity_signal": {"level": "Senior", "score": 92},
                        "release_readiness": {"status": "provisionally_ready_for_human_review"},
                    },
                }
            ]
        return []

    monkeypatch.setattr(review, "create_approval", fake_create)
    monkeypatch.setattr(review, "list_approvals", lambda customer_id=None, project_id=None: approvals)
    monkeypatch.setattr(review.STORE, "put", fake_put)
    monkeypatch.setattr(review.STORE, "list", fake_list)
    monkeypatch.setattr(review.STORE, "audit", lambda *args, **kwargs: {"status": "ok"})

    result = review.request_final_review({"run_id": "2026-07-07T15_00_00Z", "customer_id": "default_customer", "project_id": "default_project"})

    assert result["status"] == "pending_review"
    assert result["approval"]["requested_action"] == review.FINAL_REVIEW_ACTION
    assert result["approval"]["run_id"] == "2026-07-07T15_00_00Z"
    assert result["approval"]["review_snapshot"]["maturity_score"] == 92
    assert result["review"]["review_status"] == "pending"


def test_final_review_transition_allows_approved_for_final_review(monkeypatch):
    item = {
        "approval_id": "approval_review_1",
        "customer_id": "default_customer",
        "project_id": "default_project",
        "requested_action": review.FINAL_REVIEW_ACTION,
        "status": "pending",
        "run_id": "fullrun_review_1",
        "report_id": "report_review_1",
    }
    report = {
        "status": "complete",
        "report_id": "report_review_1",
        "run_id": "fullrun_review_1",
        "formats": {"json": {"report_path": "full_run"}, "pdf": "draft"},
    }
    saved = {"report": report}
    artifact = {
        "status": "complete",
        "artifact_type": "approved_full_assessment_pdf",
        "approval_id": "approval_review_1",
        "report_id": "report_review_1",
        "run_id": "fullrun_review_1",
        "approver": "cody",
        "approved_at": "2026-07-11T16:30:00Z",
        "client_delivery_allowed": True,
        "pdf_base64": "approved-pdf",
        "pdf_filename": "approved.pdf",
        "pdf_sha256": "a" * 64,
        "source_draft_pdf_sha256": "b" * 64,
        "approval_identity_sha256": "c" * 64,
    }

    monkeypatch.setattr(review.STORE, "get", lambda table, item_id: item)

    def fake_put(table, item_id, payload):
        saved[table] = dict(payload)
        if table == "reports":
            saved["report"] = dict(payload)
        return payload

    monkeypatch.setattr(review.STORE, "put", fake_put)
    monkeypatch.setattr(review.STORE, "audit", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr(review, "list_approvals", lambda customer_id=None, project_id=None: [saved.get("approvals", item)])
    monkeypatch.setattr(review, "_report_for_run", lambda run_id: saved.get("report", {}))
    monkeypatch.setattr(
        review,
        "final_review_validation",
        lambda approval: {
            "status": "ready_for_human_decision",
            "ready_for_approval": True,
            "run_id": approval.get("run_id"),
            "report_id": approval.get("report_id"),
            "checks": [],
            "blockers": [],
        },
    )
    monkeypatch.setattr(review, "build_approved_delivery_artifact", lambda report_value, approval, approved_at: {**artifact, "approved_at": approved_at})
    monkeypatch.setattr(review, "transition_approval", lambda approval_id, state, actor="human_reviewer", note="": {**item, "status": state, "approver": actor})

    result = review.transition_final_review("approval_review_1", "approved", actor="cody", note="accepted")

    assert result["status"] == "ok"
    assert result["approval"]["status"] == "approved"
    assert result["approval"]["approver"] == "cody"
    assert result["approval"]["review_validation"]["ready_for_approval"] is True
    assert result["approved_delivery"]["client_delivery_allowed"] is True
    assert saved["report"]["delivery_status"] == "approved"
    assert saved["report"]["formats"]["pdf"] == "draft"
    assert saved["report"]["approved_delivery"]["pdf_filename"] == "approved.pdf"


def test_final_review_transition_blocks_non_final_review_approval(monkeypatch):
    monkeypatch.setattr(
        review.STORE,
        "get",
        lambda table, item_id: {"approval_id": "approval_other", "requested_action": "draft_pr", "status": "pending"},
    )

    result = review.transition_final_review("approval_other", "approved")

    assert result["status"] == "blocked"
    assert "not a final report review" in result["error"]


def test_final_review_transition_rejects_invalid_state():
    result = review.transition_final_review("approval_review_1", "executed")

    assert result["status"] == "blocked"
    assert "Invalid final review state" in result["error"]
