from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_docker_scanner_install_uses_ephemeral_buildkit_secret() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert dockerfile.startswith("# syntax=docker/dockerfile:")
    assert "RUN --mount=type=secret,id=github_token,required=false" in dockerfile
    assert "/run/secrets/github_token" in dockerfile
    assert 'export GITHUB_TOKEN="$(cat /run/secrets/github_token)"' in dockerfile

    # Authentication must never be persisted in the image configuration or build history.
    assert "ARG GITHUB_TOKEN" not in dockerfile
    assert "ENV GITHUB_TOKEN" not in dockerfile
    assert "COPY github_token" not in dockerfile


def test_nico_ci_passes_repository_token_only_as_a_docker_build_secret() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nico-ci.yml").read_text(
        encoding="utf-8"
    )

    docker_step = workflow.split("- name: Run Docker build check", maxsplit=1)[1]
    docker_step = docker_step.split("- name: Run file integrity regression test", maxsplit=1)[0]

    assert "GITHUB_TOKEN: ${{ github.token }}" in docker_step
    assert 'DOCKER_BUILDKIT: "1"' in docker_step
    assert "--secret id=github_token,env=GITHUB_TOKEN" in docker_step
    assert "--build-arg GITHUB_TOKEN" not in docker_step
