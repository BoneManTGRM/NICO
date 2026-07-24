from __future__ import annotations

from types import SimpleNamespace

import nico.exact_commit_binding as binding
import nico.repository_snapshot as snapshot
from nico.storage import MemoryAdapter


class MetadataUnavailableClient:
    def get_repo(self, repository: str):
        return None, "GitHub API rate limit exceeded"


class NeverCallClient:
    def get_repo(self, repository: str):
        raise AssertionError("preverified resolution must not call GitHub")


class AuditMemoryStore(MemoryAdapter):
    def audit(self, action, payload, customer_id=None, project_id=None):
        return self.put(
            "audit_log",
            f"audit_{action}",
            {
                "action": action,
                "payload": payload,
                "customer_id": customer_id,
                "project_id": project_id,
            },
        )


def _context(expected: str) -> dict:
    return {
        "run_id": "express_run_exact_resolution_v2",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_v2",
        "project_id": "project_v2",
        "authorized_by": f"production_acceptance;expected_commit_sha={expected}",
        "expected_commit_sha": expected,
    }


def _public_resolution(expected: str) -> dict:
    return {
        "sha": expected,
        "commit": {
            "committer": {"date": "2026-07-24T00:00:00Z"},
            "author": {"date": "2026-07-24T00:00:00Z"},
            "tree": {"sha": "b" * 40},
            "message": "Exact deployed release",
        },
    }


def test_metadata_exhaustion_can_be_proven_by_anonymous_exact_sha_git(monkeypatch) -> None:
    expected = "a" * 40
    monkeypatch.setattr(
        snapshot,
        "_public_git_exact_commit",
        lambda repository, sha: (_public_resolution(sha), None),
    )

    result = snapshot.resolve_repository_commit(
        _context(expected),
        client=MetadataUnavailableClient(),
    )

    assert result["status"] == "attached"
    assert result["commit_sha"] == expected
    assert result["exact_commit_verified"] is True
    assert result["commit_capture_method"] == "public_git_exact_sha"
    assert result["public_git_fallback_used"] is True
    assert result["repository_metadata_available"] is False
    assert result["repository_visibility"] == "public_verified_by_anonymous_git"


def test_metadata_exhaustion_stays_fail_closed_when_anonymous_git_fails(monkeypatch) -> None:
    expected = "c" * 40
    monkeypatch.setattr(
        snapshot,
        "_public_git_exact_commit",
        lambda repository, sha: (None, "public_git_exact_sha_fetch_failed"),
    )

    result = snapshot.resolve_repository_commit(
        _context(expected),
        client=MetadataUnavailableClient(),
    )

    assert result["status"] == "unavailable"
    assert result["public_git_fallback_attempted"] is True
    assert result["resolution_failure_code"] == "public_git_exact_sha_fetch_failed"
    assert result["repository_metadata_available"] is False


def test_snapshot_reuses_preverified_binding_without_second_api_lookup() -> None:
    expected = "d" * 40
    context = _context(expected)
    context["exact_commit_resolution"] = {
        "status": "attached",
        "repository": "BoneManTGRM/NICO",
        "source": "public_git_read_only",
        "commit_capture_method": "public_git_exact_sha",
        "api_commit_lookup_attempts": 0,
        "public_git_fallback_attempted": True,
        "public_git_fallback_used": True,
        "repository_metadata_available": False,
        "default_branch": "",
        "requested_ref": expected,
        "expected_commit_sha": expected,
        "commit_binding_source": "explicit_request",
        "exact_commit_verified": True,
        "commit_sha": expected,
        "tree_sha": "e" * 40,
        "commit_date": "2026-07-24T00:00:00Z",
        "commit_message": "Exact release",
        "repository_pushed_at": "",
        "repository_visibility": "public_verified_by_anonymous_git",
        "human_review_required": True,
        "client_delivery_allowed": False,
    }

    result = snapshot.capture_repository_snapshot(
        context,
        client=NeverCallClient(),
        store=AuditMemoryStore(),
    )

    assert result["status"] == "attached"
    assert result["commit_sha"] == expected
    assert result["commit_capture_method"] == "public_git_exact_sha"
    assert result["idempotent_reuse"] is False


def test_exact_binding_passes_preverified_resolution_into_assessment(monkeypatch) -> None:
    expected = "f" * 40
    seen: list[dict] = []
    resolution = {
        "status": "attached",
        "repository": "BoneManTGRM/NICO",
        "source": "public_git_read_only",
        "commit_capture_method": "public_git_exact_sha",
        "api_commit_lookup_attempts": 0,
        "public_git_fallback_used": True,
        "repository_metadata_available": False,
        "requested_ref": expected,
        "expected_commit_sha": expected,
        "commit_binding_source": "explicit_request",
        "exact_commit_verified": True,
        "commit_sha": expected,
        "tree_sha": "a" * 40,
    }
    monkeypatch.setattr(binding, "_resolve_commit_details", lambda payload: dict(resolution))

    def current(payload: dict) -> dict:
        seen.append(payload)
        return {
            "status": "complete",
            "repository": "BoneManTGRM/NICO",
            "commit_sha": "0" * 40,
            "scanner_worker_auto_ran": False,
        }

    api = SimpleNamespace(run=current)
    binding._install_assessment_binding(api, "run")
    output = api.run(_context(expected))

    assert seen[0]["expected_commit_sha"] == expected
    assert seen[0]["commit_sha"] == expected
    assert seen[0]["ref"] == expected
    assert seen[0]["exact_commit_resolution"]["commit_capture_method"] == "public_git_exact_sha"
    assert output["commit_sha"] == expected
    assert output["repository_snapshot"]["source"] == "public_git_read_only"
    assert output["repository_snapshot"]["public_git_fallback_used"] is True
    assert output["exact_commit_binding"]["version"] == binding.EXACT_COMMIT_BINDING_VERSION
    assert output["commit_identity_conflict"]["observed"] == "0" * 40
