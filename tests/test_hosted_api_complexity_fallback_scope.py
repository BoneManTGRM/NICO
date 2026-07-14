from __future__ import annotations

from typing import Any

import nico.hosted_assessment as hosted
from nico.hosted_api_complexity_fallback import fetch_repository_profile_with_complexity
from nico.hosted_api_complexity_fallback_compat import install_hosted_api_complexity_fallback


class _LegacyProfileClient:
    """Implements the original profile contract and deliberately has no get_json."""

    def get_tree(self, repository: str, ref: str):
        assert repository == "owner/repository"
        assert ref == "main"
        return [{"type": "blob", "path": "requirements.txt", "size": 16}], None

    def get_contents(self, repository: str, path: str = ""):
        assert repository == "owner/repository"
        assert path == ""
        return [{"name": "requirements.txt"}], None

    def get_text_file(self, repository: str, path: str):
        assert repository == "owner/repository"
        assert path == "requirements.txt"
        return "fastapi==0.116\n", None


def test_shared_repository_profile_behavior_remains_compatible() -> None:
    result = install_hosted_api_complexity_fallback()

    assert result["status"] in {"installed", "already_installed"}
    assert result["shared_profile_override"] is False
    assert result["concurrent_express_requests_supported"] is True
    assert hosted.fetch_repository_profile is not fetch_repository_profile_with_complexity

    profile = hosted.fetch_repository_profile(
        _LegacyProfileClient(),
        "owner/repository",
        {"default_branch": "main"},
    )
    assert profile["files"] == {"requirements.txt": "fastapi==0.116\n"}
    assert profile["unavailable"] == []


def test_installer_is_idempotent_without_changing_active_profile_behavior() -> None:
    before = hosted.fetch_repository_profile
    first = install_hosted_api_complexity_fallback()
    second = install_hosted_api_complexity_fallback()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert second["concurrent_express_requests_supported"] is True
    assert hosted.fetch_repository_profile is before
