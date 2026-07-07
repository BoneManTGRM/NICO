from nico.mid_evidence_upgrade import build_mid_evidence_upgrade


def test_mid_evidence_upgrade_flags_missing_human_inputs():
    result = build_mid_evidence_upgrade({"maturity_signal": {"level": "Senior"}})

    assert result["target"] == 85
    assert "stakeholder_inputs" in result["missing"]
    assert "platform_parity" in result["missing"]
    assert result["question_bank"]["stakeholder_inputs"]


def test_mid_evidence_upgrade_reaches_target_with_full_evidence():
    result = build_mid_evidence_upgrade(
        {
            "maturity_signal": {"level": "Senior"},
            "qa_evidence": "Login works on iOS and Android\nCheckout has one Android bug",
            "parity_notes": "Feature set matches except notifications",
            "stakeholder_notes": "Business goal: stabilize release cadence",
            "known_risks": "Notification parity could delay launch",
            "roadmap_notes": "Month 1 stabilize\nMonth 2 close parity",
            "resourcing_plan": {"Product Quality Engineer": "needed"},
            "executive_review": {"status": "prepared"},
        }
    )

    assert result["score"] == 85
    assert result["missing"] == []
    assert result["status"] == "green"
