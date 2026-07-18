from nico.real_report_value_benchmark_v1 import qualify_real_report_value


def _record(tier, **overrides):
    values = {
        "assessment_id": f"{tier}-assessment",
        "report_sha256": "a" * 64,
        "snapshot_sha": "b" * 40,
        "reviewer": "independent-reviewer",
        "expert_equivalence_score": {"express": 75, "mid": 85, "full": 92}[tier],
        "decision_usefulness_score": {"express": 80, "mid": 88, "full": 94}[tier],
        "estimated_replacement_value": {"express": 1500, "mid": 4500, "full": 10000}[tier],
        "real_generated_report": True,
        "evidence_verified": True,
        "findings_non_duplicate": True,
        "client_would_act": True,
        "independent_review_complete": True,
        "material_false_positives": 0,
    }
    values.update(overrides)
    return values


def _benchmarks():
    return {tier: _record(tier) for tier in ("express", "mid", "full")}


def test_complete_real_report_benchmarks_qualify():
    result = qualify_real_report_value(_benchmarks())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_tier_fails_closed():
    benchmarks = _benchmarks()
    del benchmarks["mid"]
    result = qualify_real_report_value(benchmarks)
    assert "mid:missing_benchmark" in result["failures"]


def test_weak_or_low_value_report_blocks():
    benchmarks = _benchmarks()
    benchmarks["full"] = _record(
        "full",
        expert_equivalence_score=60,
        decision_usefulness_score=65,
        estimated_replacement_value=500,
    )
    result = qualify_real_report_value(benchmarks)
    assert "full:low_expert_equivalence" in result["failures"]
    assert "full:low_decision_usefulness" in result["failures"]
    assert "full:insufficient_replacement_value" in result["failures"]


def test_padded_unverified_or_false_positive_report_blocks():
    benchmarks = _benchmarks()
    benchmarks["mid"] = _record(
        "mid",
        evidence_verified=False,
        findings_non_duplicate=False,
        client_would_act=False,
        independent_review_complete=False,
        material_false_positives=2,
    )
    result = qualify_real_report_value(benchmarks)
    assert "mid:evidence_verified:failed" in result["failures"]
    assert "mid:findings_non_duplicate:failed" in result["failures"]
    assert "mid:client_would_act:failed" in result["failures"]
    assert "mid:independent_review_complete:failed" in result["failures"]
    assert "mid:material_false_positives" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_real_report_value(_benchmarks(), prior_release_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_release_block" in result["failures"]
