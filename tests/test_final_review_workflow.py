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
    }
    monkeypatch.setattr(review.STORE, "get", lambda table, item_id: item)
    monkeypatch.setattr(review.STORE, "audit", lambda *args, **kwargs: {"status": "ok"})
    monkeypatch.setattr(review, "transition_approval", lambda approval_id, state, actor="human_reviewer", note="": {**item, "status": state, "approver": actor})

    result = review.transition_final_review("approval_review_1", "approved", actor="cody", note="accepted")

    assert result["status"] == "ok"
    assert result["approval"]["status"] == "approved"
    assert result["approval"]["approver"] == "cody"


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
