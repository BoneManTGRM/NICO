from __future__ import annotations

from fastapi.testclient import TestClient

from nico.api.main import app


def test_full_run_api_exposes_same_run_repository_evidence() -> None:
    client = TestClient(app)

    response = client.post(
        "/assessment/full-run",
        json={
            "repository": "BoneManTGRM/NICO",
            "authorization_confirmed": True,
            "authorized": True,
            "authorized_by": "tester",
            "customer_id": "cust-repo-evidence",
            "project_id": "proj-repo-evidence",
            "run_scanners": False,
            "timeframe_days": 120,
        },
    )

    assert response.status_code == 200
    data = response.json()
    evidence = data["repository_evidence"]
    progress = {item["step"]: item for item in data["progress"]}

    assert evidence["status"] == "attached"
    assert evidence["run_id"] == data["run_id"]
    assert evidence["repository"] == "BoneManTGRM/NICO"
    assert evidence["customer_id"] == "cust-repo-evidence"
    assert evidence["project_id"] == "proj-repo-evidence"
    assert evidence["source"] == "github_api_read_only"
    assert progress["repo_evidence"]["status"] == "complete"
    assert progress["repo_evidence"]["evidence"]["evidence_id"] == evidence["evidence_id"]
    assert progress["repo_evidence"]["evidence"]["repository_evidence"]["run_id"] == data["run_id"]
    assert data["human_review_required"] is True
    assert data["client_ready"] is False
