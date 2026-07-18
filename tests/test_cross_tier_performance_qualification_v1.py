from nico.cross_tier_performance_qualification_v1 import qualify_cross_tier_performance


def _record(**overrides):
    value = {
        "repository_files": 250000,
        "evidence_items": 50000,
        "runtime_seconds": 600,
        "peak_memory_mb": 1024,
        "renderer_seconds": 60,
        "worker_recoveries": 1,
        "artifact_success_rate": 1.0,
        "snapshot_sha": "a" * 40,
        "completed": True,
    }
    value.update(overrides)
    return value


def _evidence():
    return {
        "express": _record(runtime_seconds=500),
        "mid": _record(runtime_seconds=1800, peak_memory_mb=2500),
        "full": _record(runtime_seconds=7200, peak_memory_mb=6000, renderer_seconds=600),
    }


def test_all_tiers_qualify_with_bounded_metrics():
    result = qualify_cross_tier_performance(_evidence())
    assert result["delivery_allowed"] is True
    assert result["status"] == "qualified"


def test_missing_tier_fails_closed():
    evidence = _evidence()
    del evidence["mid"]
    result = qualify_cross_tier_performance(evidence)
    assert result["delivery_allowed"] is False
    assert "mid:missing_evidence" in result["failures"]


def test_runtime_memory_renderer_and_recovery_limits_block():
    evidence = _evidence()
    evidence["full"] = _record(
        runtime_seconds=10801,
        peak_memory_mb=8193,
        renderer_seconds=901,
        worker_recoveries=6,
    )
    result = qualify_cross_tier_performance(evidence)
    assert result["delivery_allowed"] is False
    assert "full:runtime_seconds:limit_exceeded" in result["failures"]
    assert "full:peak_memory_mb:limit_exceeded" in result["failures"]
    assert "full:renderer_seconds:limit_exceeded" in result["failures"]
    assert "full:worker_recoveries:limit_exceeded" in result["failures"]


def test_partial_artifact_generation_blocks_release():
    evidence = _evidence()
    evidence["express"] = _record(artifact_success_rate=0.99)
    result = qualify_cross_tier_performance(evidence)
    assert "express:artifact_success_rate:below_required" in result["failures"]


def test_identity_and_completion_are_required():
    evidence = _evidence()
    evidence["mid"] = _record(snapshot_sha="", completed=False)
    result = qualify_cross_tier_performance(evidence)
    assert "mid:missing_snapshot_sha" in result["failures"]
    assert "mid:not_completed" in result["failures"]


def test_prior_delivery_block_is_preserved():
    result = qualify_cross_tier_performance(_evidence(), prior_delivery_allowed=False)
    assert result["delivery_allowed"] is False
    assert "prior_delivery_block" in result["failures"]
