from nico.hosted_complexity_engine_attachment_patch import (
    build_complexity_attachment_summary,
    install_hosted_complexity_engine_attachment_patch,
)


def complexity_profile():
    return {
        "artifact_schema": "nico.complexity.v1",
        "source_file_count": 12,
        "total_loc": 900,
        "total_functions": 45,
        "call_graph_edge_count": 120,
        "max_file_cyclomatic_complexity": 18,
        "complexity_score": 88,
        "architecture_score": 90,
        "velocity_score": 88,
        "risk_level": "low",
        "evidence": ["Complexity engine analyzed 12 source file(s)."],
        "findings": [],
        "hotspots": [
            {
                "path": "nico/app.py",
                "hotspot_score": 12.4,
                "loc": 120,
                "cyclomatic_complexity": 6,
                "churn": 14,
                "primary_owner": "dev@example.com",
                "owner_concentration": 0.8,
            }
        ],
    }


def test_complexity_attachment_summary_marks_valid_profile_completed():
    summary = build_complexity_attachment_summary(complexity_profile())

    assert summary["artifact_schema"] == "nico.complexity_attachment.v1"
    assert summary["status"] == "completed"
    assert summary["current_run"] is True
    assert summary["verified_for_this_report"] is True
    assert summary["source_file_count"] == 12
    assert summary["hotspot_count"] == 1
    assert summary["top_hotspots"][0]["path"] == "nico/app.py"
    assert summary["artifact_hash"]


def test_complexity_attachment_summary_marks_missing_profile_unavailable():
    summary = build_complexity_attachment_summary({})

    assert summary["status"] == "unavailable"
    assert summary["current_run"] is False
    assert summary["verified_for_this_report"] is False
    assert "missing or incomplete" in summary["unavailable_reason"]


def test_attach_scanner_worker_artifacts_exposes_complexity_summary(monkeypatch):
    from nico import hosted_scanner_artifacts

    artifact = {"tools": {}, "complexity_engine": complexity_profile()}
    result = {
        "status": "complete",
        "sections": [
            {"id": "architecture_debt", "score": 72, "status": "yellow", "summary": "", "evidence": [], "findings": [], "unavailable": []},
            {"id": "velocity_complexity", "score": 73, "status": "yellow", "summary": "", "evidence": [], "findings": [], "unavailable": []},
        ],
        "findings": [],
    }

    install_hosted_complexity_engine_attachment_patch()
    output = hosted_scanner_artifacts.attach_scanner_worker_artifacts(result, {"scanner_worker_artifact": artifact})

    assert output["complexity_engine_summary"]["status"] == "completed"
    assert output["complexity_engine_summary"]["architecture_score"] == 90
    assert output["complexity_engine_summary"]["velocity_score"] == 88
    assert output["complexity_engine_summary"]["top_hotspots"][0]["path"] == "nico/app.py"


def test_hosted_scanner_worker_artifact_gets_complexity_summary(monkeypatch):
    from nico import hosted_scanner_worker

    install_hosted_complexity_engine_attachment_patch()

    def fake_worker(payload):
        return {"tools": {}, "complexity_engine": complexity_profile()}

    monkeypatch.setattr(hosted_scanner_worker, "_nico_original_run_hosted_scanner_worker_complexity_attachment", fake_worker)

    output = hosted_scanner_worker.run_hosted_scanner_worker({"repository": "BoneManTGRM/NICO", "authorized": True})

    assert output["complexity_engine_summary"]["status"] == "completed"
    assert output["complexity_engine_summary"]["verified_for_this_report"] is True
