from nico.bench import run_bench_demo


def test_nico_bench_demo_is_fixture_based():
    result = run_bench_demo()
    assert result["mode"] == "fixture_based_local_only"
    assert result["benchmark_claim"] == "demo_fixture_results_only_no_production_claim"
    assert result["total"] > 0
    assert result["score"] >= 0
    assert "masking_success" in result["metrics"]
