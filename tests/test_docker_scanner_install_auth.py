from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _timeout_minutes(block: str) -> int:
    match = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", block)
    assert match is not None
    return int(match.group(1))


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

    quality = workflow.split("  quality:", maxsplit=1)[1]
    quality = quality.split("  test_shards:", maxsplit=1)[0]
    docker_step = quality.split("- name: Run Docker build check", maxsplit=1)[1]
    docker_step = docker_step.split("- name: Run file integrity regression test", maxsplit=1)[0]

    assert "GITHUB_TOKEN: ${{ github.token }}" in docker_step
    assert 'DOCKER_BUILDKIT: "1"' in docker_step
    assert "--secret id=github_token,env=GITHUB_TOKEN" in docker_step
    assert "--build-arg GITHUB_TOKEN" not in docker_step


def test_nico_ci_isolates_the_full_suite_and_preserves_one_final_test_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nico-ci.yml").read_text(
        encoding="utf-8"
    )

    quality = workflow.split("  quality:", maxsplit=1)[1]
    quality = quality.split("  test_shards:", maxsplit=1)[0]
    shards = workflow.split("  test_shards:", maxsplit=1)[1]
    shards, gate = shards.split("  test:\n", maxsplit=1)

    assert "-stable-v3" in workflow
    assert _timeout_minutes(quality) == 35
    docker_step = quality.split("- name: Run Docker build check", maxsplit=1)[1]
    docker_step = docker_step.split("- name: Run file integrity regression test", maxsplit=1)[0]
    assert _timeout_minutes(docker_step) == 20

    assert "name: test-shard-${{ matrix.shard }}" in shards
    assert "shard: [0, 1, 2, 3]" in shards
    assert 'Path("tests").rglob("test_*.py")' in shards
    assert "subprocess.call(command)" in shards
    assert '"-m",\n            "pytest"' in shards
    assert "pytest-timeout" not in workflow
    assert "SIGABRT" not in workflow
    assert "timeout --signal" not in workflow

    assert "name: test" in gate
    assert "needs: [quality, test_shards]" in gate
    assert "QUALITY_RESULT: ${{ needs.quality.result }}" in gate
    assert "SHARDS_RESULT: ${{ needs.test_shards.result }}" in gate
    assert 'test "$QUALITY_RESULT" = "success"' in gate
    assert 'test "$SHARDS_RESULT" = "success"' in gate
