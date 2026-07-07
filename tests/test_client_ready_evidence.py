from nico.client_ready_evidence import build_client_ready_evidence


def test_client_ready_evidence_requires_review_rerun_and_acceptance():
    result = build_client_ready_evidence(
        {
            "storage": {"persistence_available": True},
            "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
            "reports": {"markdown": "# report"},
        }
    )

    assert result["target"] == 85
    assert "review_requested" in result["missing"]
    assert "review_approved" in result["missing"]
    assert "acceptance_green" in result["missing"]
    assert result["status"] != "green"


def test_client_ready_evidence_reaches_target_with_all_gates():
    result = build_client_ready_evidence(
        {
            "storage": {"persistence_available": True},
            "run_id": "run_1",
            "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
            "final_review_status": "approved",
            "client_acceptance": {"status": "accepted"},
            "reports": {"markdown": "# report", "html": "<p>report</p>"},
            "delivery_notes": ["Reviewed and ready"],
        }
    )

    assert result["score"] == 85
    assert result["missing"] == []
    assert result["status"] == "green"
