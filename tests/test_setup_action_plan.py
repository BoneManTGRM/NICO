from nico.setup_action_plan import setup_action_plan


def test_setup_action_plan_prioritizes_deployment_blockers():
    result = setup_action_plan({"frontend_url": "https://app.nicoaudit.com"})

    assert result["ready_for_max_target_validation"] is False
    assert result["next_action"]["id"] == "backend_url_configured"
    assert result["next_action"]["priority"] == "critical"
    assert result["next_action"]["system"] == "Vercel"


def test_setup_action_plan_ready_when_setup_complete():
    result = setup_action_plan(
        {
            "frontend_url": "https://app.nicoaudit.com",
            "backend_url": "https://nico-api.example.com",
            "backend_status": "ok",
            "storage": {"adapter": "postgres", "persistence_available": True},
            "run_id": "run_1",
            "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
            "final_review_status": "approved",
            "client_acceptance": {"status": "accepted"},
            "express_service_completion": {"score": 95},
        }
    )

    assert result["ready_for_max_target_validation"] is True
    assert result["readiness_score"] == 100
    assert result["next_action"] is None
    assert result["actions"] == []
