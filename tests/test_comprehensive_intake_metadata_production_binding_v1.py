from __future__ import annotations

from fastapi import FastAPI

import nico.comprehensive_api_routes as routes
from nico.comprehensive_production_capabilities import PROVIDER_STATE_KEY
from nico.strategic_human_evidence_binding_v1 import (
    _CAPABILITY_MODULES,
    install_strategic_human_evidence_binding,
)


def _provider(_context: dict[str, object]) -> dict[str, object]:
    return {"status": "complete", "evidence": {}}


def test_production_human_evidence_binding_installs_durable_intake_metadata_boundary() -> None:
    app = FastAPI()
    setattr(
        app.state,
        PROVIDER_STATE_KEY,
        {capability: _provider for capability in _CAPABILITY_MODULES},
    )
    original_intake = routes._intake
    try:
        status = install_strategic_human_evidence_binding(app)

        assert status["bound"] is True
        assert status["intake_display_metadata_bound"] is True
        assert status["commercial_display_metadata_durable"] is True
        assert status["intake_display_metadata"]["direct_controller_payload"] is True
        assert status["intake_display_metadata"]["durable_report_display_metadata_fallback"] is True
        assert status["intake_display_metadata"]["contextvar_required_for_display_metadata"] is False
        assert getattr(routes._intake, "_nico_direct_display_metadata_v2", False) is True
    finally:
        routes._intake = original_intake


def test_production_binding_fails_closed_if_intake_metadata_binding_is_not_durable(monkeypatch) -> None:
    import nico.strategic_human_evidence_binding_v1 as binding

    app = FastAPI()
    setattr(
        app.state,
        PROVIDER_STATE_KEY,
        {capability: _provider for capability in _CAPABILITY_MODULES},
    )
    monkeypatch.setattr(
        binding,
        "install_comprehensive_intake_display_metadata_v2",
        lambda: {
            "bound": False,
            "direct_controller_payload": False,
            "durable_report_display_metadata_fallback": False,
            "contextvar_required_for_display_metadata": True,
        },
    )

    status = binding.install_strategic_human_evidence_binding(app)

    assert status["bound"] is False
    assert status["intake_display_metadata_bound"] is False
    assert status["commercial_display_metadata_durable"] is False
