from nico.comprehensive_phase7_truth_gateway import build_truth_bound_comprehensive_assessment


def test_missing_control_evidence_is_not_redistributed(monkeypatch):
    monkeypatch.setattr(
        "nico.comprehensive_phase7_truth_gateway.build_decision_grade_assessment",
        lambda **_: {
            "sections": [
                {"section_id": "complete", "presented_score": 90, "evidence": ["proof"], "unavailable": []},
                {"section_id": "missing", "presented_score": 90, "evidence": [], "unavailable": ["scanner failed"]},
            ],
            "findings_register": [],
            "unavailable_data_notes": ["scanner failed"],
            "limitation_metrics": {"review_required_findings": 0},
            "maturity_signal": {},
        },
    )
    result = build_truth_bound_comprehensive_assessment(
        repository="owner/repo",
        commit_sha="abc123",
        run_id="run-1",
        repo={},
        complexity={},
        scan={},
    )
    assert result["observed_performance"] == 90
    assert result["coverage_adjusted_maturity"] == 45
    assert result["evidence_adjusted_readiness"] < 45
    assert result["client_delivery_allowed"] is False
    assert result["truth_sha256"]


def test_report_identity_is_bound_to_immutable_revision(monkeypatch):
    monkeypatch.setattr(
        "nico.comprehensive_phase7_truth_gateway.build_decision_grade_assessment",
        lambda **_: {
            "sections": [{"section_id": "complete", "presented_score": 80, "evidence": ["proof"], "unavailable": []}],
            "findings_register": [],
            "unavailable_data_notes": [],
            "limitation_metrics": {"review_required_findings": 0},
            "maturity_signal": {},
        },
    )
    result = build_truth_bound_comprehensive_assessment(
        repository="owner/repo",
        commit_sha="deadbeef",
        run_id="run-2",
        repo={},
        complexity={},
        scan={},
    )
    assert result["assessment_identity"]["immutable_revision"] == "deadbeef"


def test_every_findings_surface_receives_the_same_deduplicated_records(monkeypatch):
    monkeypatch.setattr(
        "nico.comprehensive_phase7_truth_gateway.build_decision_grade_assessment",
        lambda **_: {
            "sections": [{"section_id": "complete", "presented_score": 80, "evidence": ["proof"], "unavailable": []}],
            "findings_register": [
                {
                    "id": "legacy",
                    "category": "architecture",
                    "title": "High-complexity code hotspot",
                    "location": "nico/report.py:50",
                    "verification_status": "verified",
                    "acceptance_criteria": ["Reduce complexity"],
                },
                {
                    "id": "enriched",
                    "category": "architecture",
                    "decision_title": "High-complexity code hotspot",
                    "location": "nico/report.py:50",
                    "verification_status": "verified",
                    "acceptance_criteria": ["Reduce complexity", "Reduce complexity"],
                },
            ],
            "unavailable_data_notes": [],
            "limitation_metrics": {"review_required_findings": 0},
            "maturity_signal": {},
        },
    )

    result = build_truth_bound_comprehensive_assessment(
        repository="owner/repo",
        commit_sha="deadbeef",
        run_id="run-3",
        repo={},
        complexity={},
        scan={},
    )

    assert len(result["canonical_findings"]) == 1
    assert result["findings_register"] == result["canonical_findings"]
    assert result["decision_grade_findings_register"] == result["canonical_findings"]
    assert result["executive_risk_register"] == result["canonical_findings"]
    assert len(result["canonical_findings"][0]["acceptance_criteria"]) == 1
