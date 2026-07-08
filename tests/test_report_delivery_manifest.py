from __future__ import annotations

from nico.report_delivery_manifest import build_report_delivery_manifest


def _ready_payload():
    return {
        "report": {
            "run_id": "run-1",
            "delivery_readiness": {"status": "delivery_ready", "delivery_allowed": True},
            "final_review": {"status": "approved"},
            "client_acceptance": {"status": "accepted"},
            "evidence_artifact_bundle": {"artifacts": [{"type": "readiness"}]},
        }
    }


def test_report_delivery_manifest_allows_delivery_when_ready():
    result = build_report_delivery_manifest(_ready_payload())

    assert result["artifact_schema"] == "nico.report_delivery_manifest.v1"
    assert result["status"] == "ready_for_client_delivery"
    assert result["delivery_allowed"] is True
    assert result["report_id"] == "run-1"
    assert result["missing"] == []
    assert result["blockers"] == []


def test_report_delivery_manifest_blocks_missing_review_and_acceptance():
    result = build_report_delivery_manifest(
        {
            "report": {
                "run_id": "run-1",
                "delivery_readiness": {"status": "delivery_ready", "delivery_allowed": True},
                "evidence_artifact_bundle": {"artifacts": [{"type": "readiness"}]},
            }
        }
    )

    assert result["status"] == "blocked_client_delivery"
    assert result["delivery_allowed"] is False
    assert "final_review" in result["missing"]
    assert "client_acceptance" in result["missing"]


def test_report_delivery_manifest_blocks_failed_readiness():
    payload = _ready_payload()
    payload["report"]["delivery_readiness"] = {"status": "delivery_blocked", "delivery_allowed": False}

    result = build_report_delivery_manifest(payload)

    assert result["status"] == "blocked_client_delivery"
    assert result["delivery_allowed"] is False
    assert any("Delivery readiness blocks" in item for item in result["blockers"])


def test_report_delivery_manifest_requires_evidence_artifacts():
    payload = _ready_payload()
    payload["report"]["evidence_artifact_bundle"] = {"artifacts": []}

    result = build_report_delivery_manifest(payload)

    assert result["status"] == "blocked_client_delivery"
    assert "evidence_artifact_bundle.artifacts" in result["missing"]
