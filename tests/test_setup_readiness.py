from nico.setup_readiness import setup_readiness_snapshot


def test_setup_readiness_identifies_missing_live_gates():
    result = setup_readiness_snapshot({"frontend_url": "https://app.nicoaudit.com"})

    assert result["status"] == "red"
    assert "backend_url_configured" in result["remaining"]
    assert "persistence_active" in result["remaining"]
    assert result["next_setup_action"] == "Set NEXT_PUBLIC_NICO_API_URL in Vercel to the Railway backend URL."


def test_setup_readiness_green_when_all_gates_present():
    result = setup_readiness_snapshot(
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

    assert result["status"] == "green"
    assert result["score"] == 100
    assert result["remaining"] == []
