import hashlib
import pytest

from scripts.comprehensive_recovery_observation_v1 import recovery_boundary_observed, retryable_recovery_read, validate_recovered_pdf


def test_old_terminal_acknowledgement_and_active_revision_are_not_results():
    assert not recovery_boundary_observed({"revision": 40, "terminal": True}, initial_revision=40)
    assert not recovery_boundary_observed({"revision": 41, "terminal": False}, initial_revision=40)
    assert recovery_boundary_observed({"revision": 42, "terminal": True}, initial_revision=40)


def test_missing_or_invalid_revision_cannot_certify_recovery():
    for revision in (None, True, "42", 39):
        assert not recovery_boundary_observed({"revision": revision, "terminal": True}, initial_revision=40)


def test_completed_stage_resumes_downstream_without_waiting_for_terminal_run():
    assert recovery_boundary_observed({"revision": 42, "terminal": False, "current_stage_complete": True}, initial_revision=41)
    assert not recovery_boundary_observed({"revision": 42, "terminal": False, "current_stage_complete": True}, initial_revision=42)


def test_gateway_absence_can_retry_but_missing_run_or_authorization_cannot():
    assert retryable_recovery_read(404, '{"code":404,"message":"Application not found"}')
    assert retryable_recovery_read(503, '')
    assert not retryable_recovery_read(404, '{"detail":{"code":"comprehensive_run_not_found"}}')
    assert not retryable_recovery_read(401, '')
    assert not retryable_recovery_read(404, 'not JSON')


@pytest.mark.parametrize("alteration", [None, "x-nico-run-id", "x-nico-commit-sha", "x-nico-pdf-sha256", "x-nico-human-review-required", "x-nico-client-delivery-allowed"])
def test_pdf_requires_matching_source_bytes_and_review_gates(alteration):
    data = b"%PDF-1.7\nsynthetic\n%%EOF\n"
    headers = {"content-type": "application/pdf", "x-nico-run-id": "comprun_test",
               "x-nico-commit-sha": "a" * 40, "x-nico-pdf-sha256": hashlib.sha256(data).hexdigest(),
               "x-nico-human-review-required": "true", "x-nico-client-delivery-allowed": "false"}
    if alteration:
        headers[alteration] = "mismatch"
        with pytest.raises(ValueError, match="recovered_pdf_binding_invalid"):
            validate_recovered_pdf(data, headers, run_id="comprun_test", commit_sha="a" * 40)
    else:
        assert validate_recovered_pdf(data, headers, run_id="comprun_test", commit_sha="a" * 40)["exact_run_pdf_verified"] is True
