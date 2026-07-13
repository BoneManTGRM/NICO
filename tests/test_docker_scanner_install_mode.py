from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = ROOT / "Dockerfile"
CI = ROOT / ".github" / "workflows" / "nico-ci.yml"


def test_railway_dockerfile_does_not_require_a_buildkit_secret() -> None:
    source = DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG NICO_SCANNER_INSTALL_STRICT=false" in source
    assert "ENV NICO_SCANNER_INSTALL_STRICT=${NICO_SCANNER_INSTALL_STRICT}" in source
    assert "--mount=type=secret" not in source
    assert "python scripts/install_hosted_scanner_binaries.py" in source


def test_ci_validates_scanner_downloads_without_coupling_them_to_image_build() -> None:
    source = CI.read_text(encoding="utf-8")

    assert "Validate hosted scanner release installation" in source
    assert "NICO_SCANNER_INSTALL_STRICT: \"true\"" in source
    assert "GITHUB_TOKEN: ${{ github.token }}" in source
    assert "docker build --build-arg NICO_SCANNER_INSTALL_STRICT=false" in source
    assert "--secret id=github_token" not in source
