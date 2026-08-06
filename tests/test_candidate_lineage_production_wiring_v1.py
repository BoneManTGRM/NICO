from __future__ import annotations

from pathlib import Path

from nico import candidate_lineage_runtime_patch_v1 as runtime_patch
from nico import comprehensive_report_content_render_v66 as content


_BOOTSTRAP = Path("nico/api/comprehensive_production_bootstrap.py")
_STALE_LIMITATION = "The prior structured risk register was unavailable"


def test_production_bootstrap_binds_lineage_before_native_provider_install() -> None:
    source = _BOOTSTRAP.read_text(encoding="utf-8")
    lineage_call = "candidate_lineage_runtime = install_candidate_lineage_runtime_patch()"
    provider_call = (
        "native_providers = "
        "native_provider_v5.install_native_comprehensive_providers(target)"
    )

    assert "from nico import comprehensive_native_providers_v5 as native_provider_v5" in source
    assert "from nico.candidate_lineage_runtime_patch_v1 import (" in source
    assert lineage_call in source
    assert provider_call in source
    assert source.index(lineage_call) < source.index(provider_call)
    assert '"candidate_lineage_runtime_bound": candidate_lineage_runtime_bound' in source
    assert 'reason = "candidate_lineage_runtime_binding_incomplete"' in source


def test_complete_lineage_removes_stale_prior_register_limitation(monkeypatch) -> None:
    def legacy_candidate_stage(canonical, renderer):
        del canonical, renderer
        return {
            "summary": "Scanner candidates remain human-review work.",
            "evidence": ["Raw scanner candidates: 666."],
            "unavailable": [
                _STALE_LIMITATION
                + ", so exact-SHA production complexity hotspots were restored."
            ],
            "unavailable_data_notes": [_STALE_LIMITATION],
        }

    monkeypatch.setattr(content, "_candidate_stage", legacy_candidate_stage)
    assert runtime_patch._patch_candidate_stage() is True

    lineage = {
        "status": "complete",
        "prior_target_commit_sha": "9c876ba4e3e9bb152de52567232038e52a6bbb3e",
        "prior_candidate_count": 662,
        "current_candidate_count": 666,
        "carried_forward_exact": 620,
        "carried_forward_location_changed": 20,
        "carried_forward_evidence_changed": 10,
        "newly_observed": 16,
        "no_longer_observed": 12,
        "human_approval_carried_forward": False,
        "client_delivery_allowed": False,
    }
    stage = content._candidate_stage({"candidate_lineage": lineage}, object())

    combined = "\n".join(
        [
            str(stage.get("summary") or ""),
            *(str(item) for item in stage.get("evidence") or []),
            *(str(item) for item in stage.get("unavailable") or []),
            *(str(item) for item in stage.get("unavailable_data_notes") or []),
        ]
    ).casefold()
    assert _STALE_LIMITATION.casefold() not in combined
    assert "prior candidate register imported from exact commit" in combined
    assert "prior candidates: 662; current candidates: 666" in combined
    assert stage["candidate_lineage"]["human_approval_carried_forward"] is False
    assert stage["candidate_lineage"]["client_delivery_allowed"] is False
