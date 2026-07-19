from __future__ import annotations

import base64


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def test_exact_express_run_identity_uses_bounded_bundle_without_tier_metadata(monkeypatch) -> None:
    from nico.api import main as api_main
    from nico.express_async_contract_metadata import install_express_async_contract_metadata

    calls = {"shared": 0}

    def shared_bundle(result: dict) -> dict:
        calls["shared"] += 1
        return {**result, "shared_bundle_called": True}

    monkeypatch.setattr(api_main, "attach_evidence_artifact_bundle", shared_bundle)
    install_express_async_contract_metadata()

    value = {
        "run_id": "express_run_exact_identity",
        "repository": "BoneManTGRM/NICO",
        "reports": {
            "markdown": "# Report",
            "html": "<h1>Report</h1>",
            "pdf_base64": _pdf(),
        },
        "sections": [{"id": "architecture", "score": 80}],
        "maturity_signal": {"score": 80},
    }
    result = api_main.attach_evidence_artifact_bundle(value)

    assert calls["shared"] == 0
    assert result["assessment_type"] == "express"
    assert result["service_tier"] == "express"
    assert result["evidence_artifact_bundle"]["bounded"] is True
    assert result["evidence_artifact_bundle"]["artifacts"]["pdf"]["structurally_valid"] is True


def test_non_express_without_exact_run_identity_preserves_shared_bundle(monkeypatch) -> None:
    from nico.api import main as api_main
    from nico.express_async_contract_metadata import install_express_async_contract_metadata

    calls = {"shared": 0}

    def shared_bundle(result: dict) -> dict:
        calls["shared"] += 1
        return {**result, "shared_bundle_called": True}

    monkeypatch.setattr(api_main, "attach_evidence_artifact_bundle", shared_bundle)
    install_express_async_contract_metadata()

    result = api_main.attach_evidence_artifact_bundle({"assessment_type": "mid", "run_id": "mid_run_1"})
    assert calls["shared"] == 1
    assert result["shared_bundle_called"] is True
