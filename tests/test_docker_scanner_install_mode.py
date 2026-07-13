from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
CI = ROOT / ".github" / "workflows" / "nico-ci.yml"


def test_production_docker_build_keeps_strict_scanner_install_by_default() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG NICO_SCANNER_INSTALL_STRICT=true" in source
    assert "ENV NICO_SCANNER_INSTALL_STRICT=${NICO_SCANNER_INSTALL_STRICT}" in source
    assert "--mount=type=secret" not in source


def test_ci_can_validate_image_without_external_release_download_being_a_hard_gate() -> None:
    source = CI.read_text(encoding="utf-8")

    assert "docker build --build-arg NICO_SCANNER_INSTALL_STRICT=false" in source
    assert "--secret id=github_token" not in source
