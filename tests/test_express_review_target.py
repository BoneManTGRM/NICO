from nico.express_review_target import attach_express_review_target, express_run_id, final_review_url


def test_express_run_id_uses_generated_at_when_no_explicit_id():
    assert express_run_id({"generated_at": "2026-07-07T16:15:00Z"}) == "2026-07-07T16_15_00Z"


def test_final_review_url_includes_scope():
    url = final_review_url("run_1", "customer_a", "project_b")

    assert url == "/final-review?run_id=run_1&customer_id=customer_a&project_id=project_b"


def test_attach_express_review_target_sets_scope_before_scoring():
    result = {"status": "complete", "generated_at": "2026-07-07T16:15:00Z"}
    request_payload = {"customer_id": "customer_a", "project_id": "project_b"}

    updated = attach_express_review_target(result, request_payload)

    assert updated["customer_id"] == "customer_a"
    assert updated["project_id"] == "project_b"
    assert updated["run_id"] == "2026-07-07T16_15_00Z"
    assert updated["final_review"]["url"] == "/final-review?run_id=2026-07-07T16_15_00Z&customer_id=customer_a&project_id=project_b"
    assert "Final review target:" in updated["next_steps"][0]
