from __future__ import annotations

import nico.hosted_assessment as hosted
from nico.hosted_api_complexity_fallback import fetch_repository_profile_with_complexity
from nico.hosted_api_complexity_fallback_compat import install_hosted_api_complexity_fallback


def test_installer_does_not_replace_shared_repository_profile_collector() -> None:
    result = install_hosted_api_complexity_fallback()
    original = getattr(hosted, "_nico_original_fetch_repository_profile_api_complexity")

    assert result["status"] in {"installed", "already_installed"}
    assert result["shared_profile_override"] is False
    assert hosted.fetch_repository_profile is original
    assert hosted.fetch_repository_profile is not fetch_repository_profile_with_complexity


def test_installer_is_idempotent_without_global_profile_mutation() -> None:
    before = hosted.fetch_repository_profile
    first = install_hosted_api_complexity_fallback()
    second = install_hosted_api_complexity_fallback()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert hosted.fetch_repository_profile is before
