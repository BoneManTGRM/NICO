from __future__ import annotations

from nico import comprehensive_final_report_background_v1 as background
from nico import repository_snapshot
from nico import comprehensive_production_runtime_recovery_v1 as recovery


class _UnavailableMetadataClient:
    def get_repo(self, _repository: str):
        return None, "github metadata unavailable"


class _PrivateRepositoryClient:
    def get_repo(self, _repository: str):
        return {"private": True, "default_branch": "main"}, None

    def get_commit(self, _repository: str, _ref: str):
        return None, "private repository commit unavailable"


def _resolved_commit() -> dict:
    return {
        "sha": "a" * 40,
        "commit": {
            "committer": {"date": "2026-08-24T00:00:00Z"},
            "author": {"date": "2026-08-24T00:00:00Z"},
            "tree": {"sha": "b" * 40},
            "message": "test",
        },
    }


def test_metadata_outage_uses_bounded_public_default_head_fallback(monkeypatch) -> None:
    monkeypatch.setattr(recovery, "_public_default_head", lambda repository: (_resolved_commit(), None))
    status = recovery.install_comprehensive_production_runtime_recovery()
    result = repository_snapshot.resolve_repository_commit(
        {"repository": "BoneManTGRM/NICO"},
        client=_UnavailableMetadataClient(),
    )

    assert status["bound"] is True
    assert result["status"] == "attached"
    assert result["commit_sha"] == "a" * 40
    assert result["expected_commit_sha"] == "a" * 40
    assert result["commit_capture_method"] == "public_git_default_head"
    assert result["commit_binding_source"] == "public_default_head_resolved_once"
    assert result["exact_commit_verified"] is True
    assert result["immutable_snapshot"] is True


def test_private_repository_never_uses_anonymous_default_head_fallback(monkeypatch) -> None:
    recovery.install_comprehensive_production_runtime_recovery()

    def _must_not_run(_repository: str):
        raise AssertionError("anonymous fallback must not run for confirmed-private repositories")

    monkeypatch.setattr(recovery, "_public_default_head", _must_not_run)
    result = repository_snapshot.resolve_repository_commit(
        {"repository": "BoneManTGRM/NICO"},
        client=_PrivateRepositoryClient(),
    )

    assert result["status"] == "unavailable"
    assert result["resolution_failure_code"] == "private_repository_api_commit_unavailable"


def test_final_report_queue_and_render_deadlines_cannot_expand_to_multi_hour_stalls(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_QUEUE_SECONDS", "7200")
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_PUBLICATION_SECONDS", "7200")
    recovery.install_comprehensive_production_runtime_recovery()

    queue_seconds = background._max_queue_seconds()
    publication_seconds = background._max_publication_seconds()
    assert queue_seconds <= recovery._DEFAULT_QUEUE_CAP_SECONDS
    assert publication_seconds <= recovery._DEFAULT_RENDER_CAP_SECONDS
    assert queue_seconds >= publication_seconds + recovery._MIN_QUEUE_GRACE_SECONDS


def test_final_report_queue_cannot_expire_before_one_healthy_bounded_render(monkeypatch) -> None:
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_QUEUE_SECONDS", "120")
    monkeypatch.setenv("NICO_COMPREHENSIVE_FINAL_REPORT_MAX_PUBLICATION_SECONDS", "900")
    recovery.install_comprehensive_production_runtime_recovery()

    publication_seconds = background._max_publication_seconds()
    queue_seconds = background._max_queue_seconds()
    assert publication_seconds == 900.0
    assert queue_seconds >= publication_seconds + recovery._MIN_QUEUE_GRACE_SECONDS
    assert queue_seconds <= recovery._DEFAULT_QUEUE_CAP_SECONDS


def test_spanish_bootstrap_wires_same_shared_recovery_layer() -> None:
    source = open("nico/api/spanish_final_report_bootstrap.py", encoding="utf-8").read()
    assert "install_comprehensive_production_runtime_recovery" in source
    assert 'VERSION = "nico.api.spanish_final_report_bootstrap.v7"' in source
    assert "PRODUCTION_RUNTIME_RECOVERY" in source
