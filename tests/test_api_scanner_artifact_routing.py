from __future__ import annotations

import json

from nico.api import main as api


def _complete_result(**extra):
    result = {
        "status": "complete",
        "generated_at": "2026-07-08T00:00:00Z",
        "sections": [],
        "findings": [],
    }
    result.update(extra)
    return result


def _response_payload(response):
    if isinstance(response, dict):
        return response
    body = getattr(response, "body", b"")
    if isinstance(body, bytes):
        return json.loads(body.decode("utf-8"))
    return json.loads(str(body))


def _patch_post_processors(monkeypatch):
    monkeypatch.setattr(api, "attach_existing_worker_evidence", lambda result, payload: result)
    monkeypatch.setattr(api, "enrich_payload_with_scanner_evidence", lambda result: result)
    monkeypatch.setattr(api, "apply_report_accuracy", lambda result: result)
    monkeypatch.setattr(api, "attach_express_review_target", lambda result, payload: result)
    monkeypatch.setattr(api, "polish_express_result", lambda result: result)
    monkeypatch.setattr(api, "finalize_express_result_consistency", lambda result: result)
    monkeypatch.setattr(api.STORE, "put", lambda *args, **kwargs: None)


def test_github_assessment_uses_standard_path_when_scanner_autorun_disabled(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "false")
    _patch_post_processors(monkeypatch)
    calls: list[str] = []

    def fake_standard(payload):
        calls.append("standard")
        return _complete_result(scanner_worker_evidence_attached=False)

    def fake_worker_aware(payload):
        calls.append("worker-aware")
        return _complete_result(scanner_worker_evidence_attached=True)

    monkeypatch.setattr(api, "run_github_assessment", fake_standard)
    monkeypatch.setattr(api, "run_github_assessment_with_scanner_artifacts", fake_worker_aware)

    req = api.GithubAssessmentRequest(repository="BoneManTGRM/NICO", authorized=True)
    result = _response_payload(api.hosted_github_assessment(req))

    assert calls == ["standard"]
    assert result["scanner_worker_evidence_attached"] is False


def test_github_assessment_uses_worker_wrapper_for_authorized_autorun(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "true")
    _patch_post_processors(monkeypatch)
    calls: list[str] = []

    def fake_standard(payload):
        calls.append("standard")
        return _complete_result(scanner_worker_evidence_attached=False)

    def fake_worker_aware(payload):
        calls.append("worker-aware")
        assert payload["repository"] == "BoneManTGRM/NICO"
        assert payload["authorized"] is True
        return _complete_result(scanner_worker_evidence_attached=True, scanner_worker_auto_ran=True)

    monkeypatch.setattr(api, "run_github_assessment", fake_standard)
    monkeypatch.setattr(api, "run_github_assessment_with_scanner_artifacts", fake_worker_aware)

    req = api.GithubAssessmentRequest(repository="BoneManTGRM/NICO", authorized=True)
    result = _response_payload(api.hosted_github_assessment(req))

    assert calls == ["worker-aware"]
    assert result["scanner_worker_evidence_attached"] is True
    assert result["scanner_worker_auto_ran"] is True


def test_github_assessment_uses_worker_wrapper_with_scanner_artifact(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "false")
    _patch_post_processors(monkeypatch)
    calls: list[str] = []

    def fake_standard(payload):
        calls.append("standard")
        return _complete_result(scanner_worker_evidence_attached=False)

    def fake_worker_aware(payload):
        calls.append("worker-aware")
        assert payload["scanner_worker_artifact"] == {"tools": {}}
        return _complete_result(scanner_worker_evidence_attached=True)

    monkeypatch.setattr(api, "run_github_assessment", fake_standard)
    monkeypatch.setattr(api, "run_github_assessment_with_scanner_artifacts", fake_worker_aware)

    req = api.GithubAssessmentRequest(
        repository="BoneManTGRM/NICO",
        authorized=True,
        scanner_worker_artifact={"tools": {}},
    )
    result = _response_payload(api.hosted_github_assessment(req))

    assert calls == ["worker-aware"]
    assert result["scanner_worker_evidence_attached"] is True


def test_github_assessment_accepts_worker_artifact_alias(monkeypatch):
    monkeypatch.setenv("NICO_ENABLE_HOSTED_SCANNER_AUTORUN", "false")
    _patch_post_processors(monkeypatch)
    calls: list[str] = []

    monkeypatch.setattr(api, "run_github_assessment", lambda payload: calls.append("standard") or _complete_result())
    monkeypatch.setattr(
        api,
        "run_github_assessment_with_scanner_artifacts",
        lambda payload: calls.append("worker-aware") or _complete_result(scanner_worker_evidence_attached=True),
    )

    req = api.GithubAssessmentRequest(
        repository="BoneManTGRM/NICO",
        authorized=True,
        worker_artifact={"tools": {}},
    )
    result = _response_payload(api.hosted_github_assessment(req))

    assert calls == ["worker-aware"]
    assert result["scanner_worker_evidence_attached"] is True
