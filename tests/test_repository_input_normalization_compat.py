from __future__ import annotations

import pytest

import nico.hosted_assessment as hosted
from nico.repository_input_normalization_compat import (
    canonical_repository_input,
    install_repository_input_normalization,
)


def test_canonical_repository_input_removes_only_separator_whitespace() -> None:
    assert canonical_repository_input(" BoneManTGRM /NICO ") == "BoneManTGRM/NICO"
    assert canonical_repository_input("BoneManTGRM / NICO") == "BoneManTGRM/NICO"
    assert canonical_repository_input("https://github.com/BoneManTGRM / NICO.git") == "https://github.com/BoneManTGRM/NICO.git"
    assert canonical_repository_input("git@github.com: BoneManTGRM / NICO.git") == "git@github.com:BoneManTGRM/NICO.git"


def test_installed_parser_accepts_harmless_separator_whitespace() -> None:
    install_repository_input_normalization()

    assert hosted.normalize_repository("BoneManTGRM /NICO") == "BoneManTGRM/NICO"
    assert hosted.normalize_repository("https://github.com/BoneManTGRM / NICO.git") == "BoneManTGRM/NICO"
    assert hosted.normalize_repository("git@github.com: BoneManTGRM / NICO.git") == "BoneManTGRM/NICO"


def test_internal_segment_whitespace_and_invalid_characters_remain_blocked() -> None:
    install_repository_input_normalization()

    with pytest.raises(ValueError, match="repository must be owner/name"):
        hosted.normalize_repository("Bone ManTGRM/NICO")
    with pytest.raises(ValueError, match="repository must be owner/name"):
        hosted.normalize_repository("BoneManTGRM/NI CO")
    with pytest.raises(ValueError, match="repository must be owner/name"):
        hosted.normalize_repository("BoneManTGRM/NICO?token=unsafe")


def test_installer_is_idempotent_and_preserves_truth_boundary() -> None:
    first = install_repository_input_normalization()
    second = install_repository_input_normalization()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert second["separator_whitespace_only"] is True
    assert second["strict_segment_validation_preserved"] is True
