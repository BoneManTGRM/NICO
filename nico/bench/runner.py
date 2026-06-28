from __future__ import annotations

from .fixtures import BENCH_FIXTURES
from .metrics import BENCH_METRICS, score_fixture


def run_bench_demo() -> dict:
    results = [score_fixture(fixture) for fixture in BENCH_FIXTURES]
    passed = sum(item["passed"] for item in results)
    total = sum(item["total"] for item in results)
    return {
        "mode": "fixture_based_local_only",
        "benchmark_claim": "demo_fixture_results_only_no_production_claim",
        "metrics": list(BENCH_METRICS),
        "fixtures": results,
        "passed": passed,
        "total": total,
        "score": 1.0 if total == 0 else passed / total,
    }
