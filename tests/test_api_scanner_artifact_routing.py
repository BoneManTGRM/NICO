from __future__ import annotations

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


def _patch_post_processors(monkeypatch):
    monkeypatch.setattr(api, "attach_existing_worker_evidence", lambda result, payload: result)
    monkeypatch.setattr(api, "enrich_payload_with_scanner_evidence", lambda result: result)
    monkeypatch.setattr(api, "apply_report_accuracy", lambda result: result)
    monkeypatch.setattr(api, "attach_express_review_target", lambda result, payload: result)
    monkeypatch.setattr(api, "polish_express_result", lambda result: result)
    monkeypatch.setattr(api, "finalize_express_result_consistency", lambda result: result)
    monkeypatch.setattr(api.STORE, "put", lambda *args, **kwargs: None)


def test_github_assessment_uses_standard_path_without_scanner_artifact(monkeypatch):
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
    result = api.hosted_github_assessment(req)

    assert calls == ["standard"]
    assert result["scanner_worker_evidence_attached"] is False


def test_github_assessment_uses_worker_wrapper_with_scanner_artifact(monkeypatch):
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
    result = api.hosted_github_assessment(req)

    assert calls == ["worker-aware"]
    assert result["scanner_worker_evidence_attached"] is True


def test_github_assessment_accepts_worker_artifact_alias(monkeypatch):
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
    result = api.hosted_github_assessment(req)

    assert calls == ["worker-aware"]
    assert result["scanner_worker_evidence_attached"] is True
