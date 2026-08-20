from __future__ import annotations

from pathlib import Path

from nico import comprehensive_spanish_final_report_runtime_cache_v94 as cache
from nico import phase17_canonical_artifact_rebuild_v1 as phase17
from nico import v2_premium_report_renderer as premium


def test_phase17_executes_only_one_expensive_premium_render() -> None:
    source = Path("nico/phase17_canonical_artifact_rebuild_v1.py").read_text(encoding="utf-8")
    function_source = source.split("def rebuild_client_artifacts", 1)[1]

    assert function_source.count("rebuild_single_pass_premium_artifacts(") == 1
    assert "_populate_premium_stage_summaries(prepared)" in function_source
    assert "release_comprehensive_spanish_render_input_cache_v94()" in function_source
    assert "finally:" in function_source


def test_stage_population_uses_runtime_bound_builder(monkeypatch) -> None:
    def derived(_canonical):
        return [
            {
                "stage_id": "risk_reduction_and_executive_briefing",
                "status": "review_required",
                "evidence": ["retained"],
            }
        ]

    monkeypatch.setattr(premium, "_canonical_stages", derived)
    result = phase17._populate_premium_stage_summaries(
        {"json": {"assessment": {"technical_score": 81}}}
    )

    canonical = result["json"]
    assert canonical["stage_summaries"] == [
        {
            "stage_id": "risk_reduction_and_executive_briefing",
            "status": "review_required",
            "evidence": ["retained"],
        }
    ]
    assert canonical["assessment"]["stage_summaries"] == canonical["stage_summaries"]
    assert canonical["assessment"]["technical_score"] == 81


def test_render_projection_cache_is_released_without_clearing_translation_cache() -> None:
    sentinel = {"report_language": "es-MX"}
    cache._RENDER_INPUT_CACHE[id(sentinel)] = (
        sentinel,
        ({}, {}, [], "2026-08-20T00:00:00Z"),
    )

    released = cache.release_comprehensive_spanish_render_input_cache_v94()

    assert released == 1
    assert not cache._RENDER_INPUT_CACHE


def test_cache_release_is_idempotent() -> None:
    cache.release_comprehensive_spanish_render_input_cache_v94()
    assert cache.release_comprehensive_spanish_render_input_cache_v94() == 0
