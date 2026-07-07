from nico.max_target_readiness_packet import build_max_target_readiness_packet


def test_readiness_packet_lists_disclosures_and_steps():
    result = build_max_target_readiness_packet({})

    assert result["ready_for_all_max"] is False
    assert result["step_count"] > 0
    assert result["first_step"]
    assert result["disclosures"]
    assert len(result["service_cards"]) == 4


def test_readiness_packet_client_summary_changes_when_ready():
    payload = {
        "repository": "BoneManTGRM/NICO",
        "source_scope": "authorized",
        "maturity_signal": {"level": "Senior", "score": 95},
        "maturity_semaphore": {"Code Audit": "green"},
        "next_steps": ["quick wins", "action plan", "resourcing plan"],
        "resourcing_plan": {"Product Engineering Architect": "included"},
        "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
        "final_review_status": "approved",
        "client_acceptance": {"status": "accepted"},
        "storage": {"persistence_available": True},
        "run_id": "run_1",
        "reports": {"markdown": "# report", "html": "<p>report</p>", "pdf_base64": "abc"},
        "delivery_notes": ["ready"],
        "sections": [
            {"id": "code_audit", "score": 90},
            {"id": "dependency_health", "score": 90},
            {"id": "ci_cd", "score": 90},
            {"id": "architecture_debt", "score": 90},
            {"id": "velocity_complexity", "score": 90},
        ],
        "technical_audit": {"status": "complete"},
        "qa_evidence": "Login works on iOS and Android",
        "parity_notes": "Feature parity checked",
        "stakeholder_notes": "Business goals captured",
        "known_risks": "Release risk tracked",
        "roadmap_notes": "Month 1 stabilize\nMonth 2 close parity",
        "executive_review": {"status": "prepared"},
        "sprint_cadence": {"length": "2 weeks"},
        "release_notes": "Release candidate ready",
        "issues": "Issue owner assigned",
        "review_queue": ["go/no-go"],
        "weekly_status_report": ["completed work"],
        "quality_traceability": {"linked": True},
        "client_update": "prepared",
    }

    result = build_max_target_readiness_packet(payload)

    assert result["ready_for_all_max"] is True
    assert result["step_count"] == 0
    assert result["client_summary"] == "Ready for max targets."
