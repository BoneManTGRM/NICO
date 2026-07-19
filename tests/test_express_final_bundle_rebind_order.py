from __future__ import annotations

import base64


def _pdf() -> str:
    return base64.b64encode(b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n").decode("ascii")


def test_final_transport_rebinds_exact_express_bundle_after_replacement(monkeypatch) -> None:
    from nico.api import main as api_main
    from nico.express_backend_completion_transport import install_express_backend_completion_transport

    calls = {"shared": 0}

    def replacement(result: dict) -> dict:
        calls["shared"] += 1
        return {**result, "shared_called": True}

    monkeypatch.setattr(api_main, "attach_evidence_artifact_bundle", replacement)
    install_express_backend_completion_transport()

    result = api_main.attach_evidence_artifact_bundle(
        {
            "run_id": "express_run_final_binding",
            "reports": {
                "markdown": "# Report",
                "html": "<h1>Report</h1>",
                "pdf_base64": _pdf(),
            },
            "sections": [{"id": "architecture", "score": 80}],
            "maturity_signal": {"score": 80},
        }
    )

    assert calls["shared"] == 0
    assert result["assessment_type"] == "express"
    assert result["service_tier"] == "express"
    assert result["evidence_artifact_bundle"]["bounded"] is True


def test_final_transport_preserves_mid_shared_bundle(monkeypatch) -> None:
    from nico.api import main as api_main
    from nico.express_backend_completion_transport import install_express_backend_completion_transport

    calls = {"shared": 0}

    def replacement(result: dict) -> dict:
        calls["shared"] += 1
        return {**result, "shared_called": True}

    monkeypatch.setattr(api_main, "attach_evidence_artifact_bundle", replacement)
    install_express_backend_completion_transport()

    result = api_main.attach_evidence_artifact_bundle({"assessment_type": "mid", "run_id": "mid_run_1"})
    assert calls["shared"] == 1
    assert result["shared_called"] is True


def test_final_transport_is_last_installer_in_package() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "nico" / "__init__.py").read_text(encoding="utf-8")
    assert source.rindex("install_express_backend_completion_transport()") > source.rindex(
        "install_express_async_contract_metadata()"
    )
    assert source.rindex("install_express_backend_completion_transport()") > source.rindex(
        "install_report_quality_gate_compat()"
    )
