from __future__ import annotations

from copy import deepcopy

from nico.express_production_certification_v25 import build_express_production_certification
from nico.express_run_record_integrity import reconcile_record

SHA = "a" * 40


def _base() -> dict:
    return {
        "status": "complete",
        "current_stage": "complete",
        "progress_percent": 100,
        "report_generation_status": "complete",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": SHA,
        "reports": {
            "pdf_base64": "JVBERi0xLjQ=",
            "markdown": "# Express",
            "html": "<h1>Express</h1>",
        },
        "express_cross_format_contract": {"status": "complete", "truth_fingerprint": "truth-1"},
        "express_pdf_renderer_truth": {"status": "complete"},
        "express_pdf_bar_geometry": {
            "render_mode": "reportlab_vector_geometry",
            "verification_samples": [{"score": 0, "rendered_width": 0.0}],
        },
        "express_pdf_page_layout": {"status": "complete"},
        "express_visual_qa": {"status": "pass"},
        "express_pdf_pagination": {"status": "complete"},
        "express_terminal_contract": {"status": "complete"},
        "production_deployment": {"backend_sha": SHA, "frontend_sha": SHA},
        "restart_retrieval_proof": {
            "before_restart_run_id": "express_run_1",
            "after_restart_run_id": "express_run_1",
            "restart_executed": True,
            "artifact_digest_preserved": True,
            "storage_durable": True,
        },
        "same_sha_verification_runs": [
            {"run_id": "express_run_1", "commit_sha": SHA, "status": "complete", "truth_fingerprint": "truth-1", "artifact_digest": "artifact-1"},
            {"run_id": "express_run_2", "commit_sha": SHA, "status": "complete", "truth_fingerprint": "truth-1", "artifact_digest": "artifact-1"},
        ],
        "express_locale_parity": {
            "verified_locales": ["en", "es"],
            "section_count_equal": True,
            "score_status_equal": True,
            "artifact_formats_equal": True,
        },
    }


def _fully_certified() -> dict:
    payload = _base()
    first = build_express_production_certification(payload)
    digest = first["gates"]["artifact_manifest_integrity"]["computed_artifact_digest"]
    payload["express_artifact_manifest"] = {"artifact_digest": digest}
    return payload


def test_five_production_gates_complete_only_with_full_evidence() -> None:
    payload = _fully_certified()
    certification = build_express_production_certification(payload)
    assert certification["status"] == "complete"
    assert certification["verified_gate_count"] == 5
    assert certification["incomplete_gates"] == []
    assert all(gate["status"] == "complete" for gate in certification["gates"].values())


def test_each_missing_evidence_family_fails_closed() -> None:
    mutations = {
        "deployment_identity": lambda value: value.pop("production_deployment"),
        "restart_retrieval": lambda value: value.pop("restart_retrieval_proof"),
        "same_sha_repeatability": lambda value: value.__setitem__("same_sha_verification_runs", value["same_sha_verification_runs"][:1]),
        "english_spanish_parity": lambda value: value.__setitem__("express_locale_parity", {"verified_locales": ["en"]}),
        "artifact_manifest_integrity": lambda value: value.__setitem__("express_artifact_manifest", {"artifact_digest": "wrong"}),
    }
    for gate_name, mutate in mutations.items():
        payload = _fully_certified()
        mutate(payload)
        certification = build_express_production_certification(payload)
        assert certification["status"] == "degraded"
        assert gate_name in certification["incomplete_gates"]
        assert certification["gates"][gate_name]["status"] == "degraded"


def test_deployment_identity_requires_exact_full_sha_match() -> None:
    payload = _fully_certified()
    payload["production_deployment"]["backend_sha"] = "b" * 40
    certification = build_express_production_certification(payload)
    gate = certification["gates"]["deployment_identity"]
    assert gate["status"] == "degraded"
    assert gate["checks"]["backend_matches_assessed"] is False


def test_terminal_record_carries_certification_and_blocks_delivery() -> None:
    payload = _fully_certified()
    result = reconcile_record({}, payload)
    assert result["express_terminal_contract"]["status"] == "complete"
    assert result["express_production_certification"]["status"] == "complete"
    assert result["client_delivery_allowed"] is False
    assert result["human_review_required"] is True


def test_late_heartbeat_preserves_certification_evidence() -> None:
    complete = reconcile_record({}, _fully_certified())
    result = reconcile_record(
        {"response": deepcopy(complete)},
        {"status": "running", "current_stage": "scanner", "progress_percent": 70},
    )
    assert result["status"] == "complete"
    assert result["express_production_certification"]["status"] == "complete"
    assert result["production_deployment"]["backend_sha"] == SHA
    assert result["same_sha_verification_runs"][1]["run_id"] == "express_run_2"
