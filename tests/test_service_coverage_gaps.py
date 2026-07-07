from nico.service_coverage_gaps import service_coverage_gap, service_coverage_gaps


def _section(section_id, score):
    return {"id": section_id, "label": section_id, "score": score, "status": "green", "summary": "ok", "evidence": ["ok"]}


def test_express_gap_keeps_human_review_missing_until_acceptance():
    payload = {
        "repository": "BoneManTGRM/NICO",
        "maturity_signal": {"level": "Senior", "score": 89},
        "maturity_semaphore": {"Code Audit": "green"},
        "next_steps": ["quick wins", "resourcing plan"],
        "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
        "reports": {"markdown": "# report"},
        "sections": [
            _section("code_audit", 86),
            _section("dependency_health", 88),
            _section("ci_cd", 95),
            _section("architecture_debt", 90),
            _section("velocity_complexity", 90),
        ],
    }

    result = service_coverage_gap(payload, "express")

    assert result["target"] == 95
    assert "human_review" in result["missing"]
    assert result["ready_for_max"] is False


def test_client_ready_requires_persistence_review_rerun_and_acceptance():
    payload = {
        "storage": {"adapter": "memory", "persistence_available": False},
        "final_review": {"run_id": "run_1", "url": "/final-review?run_id=run_1"},
        "reports": {"markdown": "# report"},
    }

    result = service_coverage_gap(payload, "client_ready")

    assert result["target"] == 85
    assert "persistent_storage" in result["missing"]
    assert "client_acceptance_green" in result["missing"]


def test_all_services_report_overall_gap():
    payload = {}

    result = service_coverage_gaps(payload)

    assert result["overall_target"] == 84
    assert result["overall_gap"] > 0
    assert set(result["services"]) == {"express", "mid", "retainer", "client_ready"}
    assert result["next_actions"]
