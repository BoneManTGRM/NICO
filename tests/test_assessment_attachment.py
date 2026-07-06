from nico.assessment_attachment import attach_existing_worker_evidence
from nico.storage import STORE


def test_attachment_requires_authorization():
    result = attach_existing_worker_evidence({"status": "complete", "sections": []}, {"repository": "owner/repo", "authorized": False})
    assert result["worker_evidence_attachment"]["status"] == "blocked"
    assert "scanner_results" not in result


def test_attachment_marks_missing_evidence_unavailable():
    result = attach_existing_worker_evidence({"status": "complete", "sections": []}, {"repository": "owner/missing", "authorized": True})
    assert result["worker_evidence_attachment"]["status"] == "unavailable"
    assert any("No completed worker evidence" in note for note in result["unavailable_data_notes"])


def test_attachment_uses_latest_matching_completed_run():
    STORE.put("scanner_runs", "test_attach_old", {"scan_id": "test_attach_old", "status": "complete", "repository": "owner/repo", "customer_id": "cust", "project_id": "proj", "completed_at": "2026-01-01T00:00:00Z", "scanner_results": [{"scanner": "old", "status": "passed", "evidence_summary": "old"}]})
    STORE.put("scanner_runs", "test_attach_new", {"scan_id": "test_attach_new", "status": "complete", "repository": "owner/repo", "customer_id": "cust", "project_id": "proj", "completed_at": "2026-01-02T00:00:00Z", "scanner_results": [{"scanner": "new", "status": "passed", "evidence_summary": "new"}]})
    result = attach_existing_worker_evidence({"status": "complete", "sections": []}, {"repository": "owner/repo", "authorized": True, "customer_id": "cust", "project_id": "proj"})
    assert result["worker_evidence_attachment"]["status"] == "complete"
    assert result["worker_evidence_attachment"]["scan_id"] == "test_attach_new"
    assert result["scanner_results"][0]["scanner"] == "new"
    assert result["evidence_readiness"]["existing_worker_evidence_attached"] is True
