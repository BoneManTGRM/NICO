from nico.score_regression_guard import build_score_regression_guard


def test_score_regression_guard_flags_two_point_drop():
    result = build_score_regression_guard(
        {"maturity_signal": {"score": 91}},
        {"maturity_signal": {"score": 89}},
    )

    assert result["status"] == "regression_review_required"
    assert "technical_maturity" in result["regressions"]


def test_score_regression_guard_keeps_score_types_separate():
    result = build_score_regression_guard(
        {"maturity_signal": {"score": 91}, "max_target_status": {"overall_score": 60}},
        {"maturity_signal": {"score": 91}, "max_target_status": {"overall_score": 58}},
    )

    assert result["status"] == "regression_review_required"
    assert "technical_maturity" not in result["regressions"]
    assert "max_target_readiness" in result["regressions"]


def test_score_regression_guard_allows_one_point_noise():
    result = build_score_regression_guard(
        {"maturity_signal": {"score": 91}},
        {"maturity_signal": {"score": 90}},
    )

    assert result["status"] == "ok"
