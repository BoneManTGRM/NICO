from __future__ import annotations

import base64

from nico import comprehensive_spanish_final_report_runtime_cache_v94 as cache
from nico import phase17_canonical_artifact_rebuild_v1 as phase17
from nico import v2_premium_report_renderer as premium


def test_phase17_executes_only_one_expensive_premium_render(monkeypatch) -> None:
    from tests.test_v2_premium_report_renderer import _package

    steps = []
    functions = {
        "prepare": (phase17, "_prepare_client_artifact_package"),
        "populate": (phase17, "_populate_premium_stage_summaries"),
        "render": (phase17, "rebuild_single_pass_premium_artifacts"),
        "release": (cache, "release_comprehensive_spanish_render_input_cache_v94"),
    }
    for label, (module, name) in functions.items():
        original = getattr(module, name)

        def observed(*args, _label=label, _original=original, **kwargs):
            steps.append(_label)
            result = _original(*args, **kwargs)
            steps.append(_label + ":done")
            return result

        monkeypatch.setattr(module, name, observed)

    result = phase17.rebuild_client_artifacts(_package("es-MX"))

    assert result["json"]
    assert base64.b64decode(result["pdf_base64"], validate=True).startswith(b"%PDF-")
    assert steps.count("prepare") == 1
    assert steps.count("populate") == 1
    assert steps.count("render") == 1
    assert steps.count("release") == 1
    assert steps.index("prepare") < steps.index("populate")
    assert steps.index("populate:done") < steps.index("prepare:done") < steps.index("render")
    assert steps[-1] == "release:done"


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
