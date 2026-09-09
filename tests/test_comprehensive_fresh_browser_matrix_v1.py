from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from nico.complete_assessment_gate_v1 import ScannerEvidenceBlocked

from scripts import comprehensive_fresh_browser_matrix_v1 as proof


def visibility_page(monkeypatch, responses):
    clock = [0.0]
    seen = []
    values = iter(responses)
    def get(url, **kwargs):
        seen.append(url.rsplit("/", 1)[-1])
        status, payload = next(values)
        return SimpleNamespace(status=status, ok=status < 400, json=lambda: payload)
    monkeypatch.syspath_prepend(str(proof.ROOT / "scripts"))
    monkeypatch.setattr(proof.time, "monotonic", lambda: clock[0])
    return SimpleNamespace(request=SimpleNamespace(get=get),
                           wait_for_timeout=lambda ms: clock.__setitem__(0, clock[0] + ms / 1000)), seen


def test_async_intake_visibility_wait_preserves_same_run_and_commit(monkeypatch):
    page, seen = visibility_page(monkeypatch, [
        (404, {}), (202, {"intake_reserved": True, "operation": "intake_pending", "terminal": False}),
        (200, {"run_id": "run-a", "commit_sha": "a" * 40}),
    ])
    evidence = proof.wait_for_immutable_capture(page, "run-a", "a" * 40)
    assert seen == ["run-a"] * 3
    assert evidence == {"visibility_read_attempts": 3, "visibility_404_reads": 1,
                        "visibility_reserved_reads": 1}


@pytest.mark.parametrize("status,payload", [
    (403, {}), (500, {}),
    (200, {"run_id": "wrong", "commit_sha": "a" * 40}),
    (200, {"run_id": "run-a", "commit_sha": "b" * 40}),
    (200, {"intake_reserved": True, "operation": "failed", "terminal": True}),
    (200, {"run_id": "run-a", "terminal": True}),
])
def test_visibility_wait_does_not_retry_denial_or_wrong_identity(monkeypatch, status, payload):
    page, seen = visibility_page(monkeypatch, [(status, payload)])
    with pytest.raises(AssertionError):
        proof.wait_for_immutable_capture(page, "run-a", "a" * 40)
    assert seen == ["run-a"]


def test_visibility_wait_is_bounded_without_replacement_intake(monkeypatch):
    page, seen = visibility_page(monkeypatch, [(404, {})] * 360)
    with pytest.raises(AssertionError, match="within 180 seconds"):
        proof.wait_for_immutable_capture(page, "run-a", "a" * 40)
    assert seen == ["run-a"] * 360


def test_fresh_continuations_must_target_the_original_run():
    request = {"method": "POST", "path": "/api/nico/assessment/comprehensive-run/run-a/continue"}
    assert proof.verify_continuations([request, request], "run-a") == 2
    with pytest.raises(AssertionError, match="different run"):
        proof.verify_continuations([request], "run-b")


def intake(language="en", project="TEST — matrix"):
    return {"method": "POST", "path": "/api/nico/assessment/comprehensive-intake",
            "body": json.dumps({"report_language": language, "client_name": proof.CLIENT,
                                "project_name": project, "password": "must-not-be-retained"})}


def test_fresh_intake_is_required_and_duplicate_or_wrong_language_rejected():
    for requests in ([], [intake(), intake()], [intake("es-MX")]):
        with pytest.raises(AssertionError):
            proof.verify_intake(requests, "en", "TEST — matrix")
    result = proof.verify_intake([intake()], "en", "TEST — matrix")
    assert result["intake_request_count"] == 1
    assert "must-not-be-retained" not in json.dumps(result)


def test_device_conditions_are_explicit_and_required_cells_are_distinct():
    assert set(proof.CELLS) == {
        ("mobile-chromium-en", "chromium", "en"),
        ("iphone-webkit-en", "webkit", "en"),
        ("iphone-webkit-es-MX", "webkit", "es-MX"),
    }
    for _, engine, language in proof.CELLS:
        conditions = proof.context_options(engine, language)
        assert conditions["viewport"] == {"width": 390, "height": 844}
        assert conditions["is_mobile"] and conditions["has_touch"]
        assert conditions["device_scale_factor"] == 3
        assert conditions["locale"] == ("en-US" if language == "en" else "es-MX")


def test_terminal_label_does_not_substitute_for_matching_identity_or_scanner_receipts():
    canonical = {"identity": {"run_id": "run-a", "commit_sha": "a" * 40}}
    state = {"run_id": "run-a", "commit_sha": "a" * 40, "terminal": True,
             "human_review_required": True, "client_delivery_allowed": False}
    with pytest.raises(AssertionError):
        proof.verify_terminal(state, canonical, "run-a", "b" * 40)
    # Even matching terminal labels are insufficient when retained scanner evidence is absent.
    with pytest.raises(ScannerEvidenceBlocked):
        proof.verify_terminal(state, canonical, "run-a", "a" * 40)
    for field, invalid in (("client_delivery_allowed", True), ("human_review_required", False), ("terminal", False)):
        with pytest.raises(AssertionError):
            proof.verify_terminal({**state, field: invalid}, canonical, "run-a", "a" * 40)


def test_retained_files_have_real_byte_identity_without_session_headers(tmp_path):
    class Response:
        status = 200
        headers = {"x-nico-run-id": "run-a", "set-cookie": "secret", "x-nico-operator-session": "secret"}
    data = b"%PDF-bilingual-\xc3\xb1"
    result = proof.retain(tmp_path / "report.pdf", data, response=Response())
    assert (tmp_path / result["path"]).read_bytes() == data
    assert result["size_bytes"] == len(data)
    assert result["sha256"] == "ae115f79ea8f4fdc9d490c211b36c7683efd6d5b51a45f874c1ca0df0ba40711"
    assert result["identity_headers"] == {"x-nico-run-id": "run-a"}


def test_matrix_is_a_required_push_producer_step_with_unchanged_auth_scope():
    workflow = Path(".github/workflows/spanish-comprehensive-production-proof.yml").read_text()
    assert "python -m playwright install --with-deps chromium webkit" in workflow
    assert "id: fresh_browser_matrix\n        if: steps.exclusion_proof.outcome == 'success'" in workflow
    assert 'test "${{ steps.fresh_browser_matrix.outcome }}" = "success"' in workflow
    assert "audit-results/fresh-browser-matrix/**" in workflow
    assert "contents: read\n  statuses: write\n  id-token: write" in workflow
