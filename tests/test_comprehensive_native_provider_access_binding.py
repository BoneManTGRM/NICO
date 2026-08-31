from __future__ import annotations

from typing import Any

from nico import comprehensive_native_providers as native


def _context() -> dict[str, Any]:
    return {
        "run_id": "comprun_access_binding",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "evidence_ledger_id": "ledger_access_binding",
        "customer_id": "synthetic_customer",
        "project_id": "synthetic_project",
        "assessment_depth": "strategic",
        "report_language": "en",
    }


def _snapshot() -> dict[str, Any]:
    return {
        "status": "attached",
        "snapshot_id": "snapshot_access_binding",
        "run_id": "comprun_access_binding",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "provider": "github",
        "provider_access_observed": False,
        "access_mode": "",
        "credential_used": None,
    }


def test_snapshot_stage_freezes_anonymous_public_access_binding(monkeypatch) -> None:
    context = {
        **_context(),
        "repository_provider": "github",
        "provider_access_mode": "anonymous_public",
        "provider_credential_used": False,
    }
    monkeypatch.setattr(native, "capture_repository_snapshot", lambda _context: _snapshot())

    result = native.snapshot_provider(context)

    frozen = result["snapshot"]
    assert frozen["provider_access_observed"] is True
    assert frozen["access_mode"] == "anonymous_public"
    assert frozen["credential_used"] is False
    assert frozen["provider_access_mode"] == "anonymous_public"
    assert frozen["provider_credential_used"] is False


def test_snapshot_stage_freezes_authenticated_read_only_binding(monkeypatch) -> None:
    context = {
        **_context(),
        "repository_provider": "github",
        "provider_access_mode": "authenticated_read_only",
        "provider_credential_used": True,
    }
    monkeypatch.setattr(native, "capture_repository_snapshot", lambda _context: _snapshot())

    result = native.snapshot_provider(context)

    frozen = result["snapshot"]
    assert frozen["provider_access_observed"] is True
    assert frozen["access_mode"] == "authenticated_read_only"
    assert frozen["credential_used"] is True


def test_repository_collection_recovers_binding_only_from_observed_snapshot(
    monkeypatch,
) -> None:
    observed_snapshot = {
        **_snapshot(),
        "provider_access_observed": True,
        "access_mode": "anonymous_public",
        "credential_used": False,
        "provider_access_mode": "anonymous_public",
        "provider_credential_used": False,
    }
    context = {
        **_context(),
        "prior_stage_results": {
            "immutable_repository_snapshot": {"snapshot": observed_snapshot}
        },
    }
    captured: dict[str, Any] = {}

    def collect(collection_context, snapshot):
        captured.update(collection_context)
        assert snapshot is observed_snapshot
        return (
            {
                "status": "attached",
                "evidence_id": "repository_evidence",
                "snapshot_commit_sha": "a" * 40,
            },
            {"status": "attached", "evidence_id": "complexity_evidence"},
        )

    monkeypatch.setattr(native, "collect_snapshot_repository_evidence", collect)

    result = native.repository_evidence_provider(context)

    assert result["status"] == "complete"
    assert captured["provider_access_mode"] == "anonymous_public"
    assert captured["provider_credential_used"] is False


def test_unobserved_snapshot_cannot_invent_provider_access_binding(monkeypatch) -> None:
    context = {
        **_context(),
        "prior_stage_results": {
            "immutable_repository_snapshot": {
                "snapshot": {
                    **_snapshot(),
                    "access_mode": "anonymous_public",
                    "credential_used": False,
                }
            }
        },
    }
    captured: dict[str, Any] = {}

    def collect(collection_context, _snapshot_value):
        captured.update(collection_context)
        return (
            {"status": "unavailable", "unavailable_data_notes": ["missing binding"]},
            {"status": "unavailable"},
        )

    monkeypatch.setattr(native, "collect_snapshot_repository_evidence", collect)

    result = native.repository_evidence_provider(context)

    assert result["status"] == "blocked"
    assert "provider_access_mode" not in captured
    assert "provider_credential_used" not in captured
