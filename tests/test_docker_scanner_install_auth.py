from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]


def _timeout_minutes(block: str) -> int:
    match = re.search(r"(?m)^\s+timeout-minutes:\s*(\d+)\s*$", block)
    assert match is not None
    return int(match.group(1))


def test_docker_scanner_install_requires_no_build_secret() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")

    assert "RUN --mount=type=secret" not in dockerfile
    assert "/run/secrets/github_token" not in dockerfile
    assert "python scripts/install_hosted_scanner_binaries.py" in dockerfile
    assert "command -v osv-scanner" in dockerfile
    assert "command -v gitleaks" in dockerfile
    assert "command -v trufflehog" in dockerfile

    # Authentication must never be persisted in image configuration or build history.
    assert "ARG GITHUB_TOKEN" not in dockerfile
    assert "ENV GITHUB_TOKEN" not in dockerfile
    assert "COPY github_token" not in dockerfile


def test_nico_ci_passes_repository_token_only_as_an_ephemeral_build_secret() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nico-ci.yml").read_text(
        encoding="utf-8"
    )

    quality = workflow.split("  quality:", maxsplit=1)[1]
    quality = quality.split("  test_shards:", maxsplit=1)[0]
    docker_step = quality.split("- name: Run Docker build check", maxsplit=1)[1]
    docker_step = docker_step.split("- name: Run file integrity regression test", maxsplit=1)[0]

    # CI may still provide its ephemeral token to BuildKit for compatibility,
    # but the production Dockerfile and default pinned installer do not require it.
    assert "GITHUB_TOKEN: ${{ github.token }}" in docker_step
    assert 'DOCKER_BUILDKIT: "1"' in docker_step
    assert "--secret id=github_token,env=GITHUB_TOKEN" in docker_step
    assert "--build-arg GITHUB_TOKEN" not in docker_step


def test_nico_ci_isolates_every_test_file_and_preserves_one_final_gate() -> None:
    workflow = (ROOT / ".github" / "workflows" / "nico-ci.yml").read_text(
        encoding="utf-8"
    )

    quality = workflow.split("  quality:", maxsplit=1)[1]
    quality = quality.split("  test_shards:", maxsplit=1)[0]
    shards = workflow.split("  test_shards:", maxsplit=1)[1]
    shards, gate = shards.split("  test:\n", maxsplit=1)

    assert "-stable-v11" in workflow
    assert _timeout_minutes(quality) == 35
    docker_step = quality.split("- name: Run Docker build check", maxsplit=1)[1]
    docker_step = docker_step.split("- name: Run file integrity regression test", maxsplit=1)[0]
    assert _timeout_minutes(docker_step) == 20

    assert "name: test-shard-${{ matrix.shard }}" in shards
    assert _timeout_minutes(shards) == 35
    assert "shard: [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]" in shards
    assert 'NICO_TEST_SHARDS: "12"' in shards
    assert 'Path("tests").rglob("test_*.py")' in shards
    assert "set(assigned) != set(files)" in shards
    assert "NICO test sharding did not assign every file exactly once" in shards

    # Every selected test file runs in a fresh process. This prevents cumulative
    # interpreter state, leaked descendants, or one blocked file from wedging a
    # complete multi-file shard without identifying the responsible file.
    assert "for index, path in enumerate(selected, start=1):" in shards
    assert '"-m",\n                    "pytest"' in shards
    assert "str(path)" in shards
    assert "start_new_session=True" in shards
    assert "process.wait(timeout=5 * 60)" in shards
    assert "os.killpg(process.pid, signal.SIGTERM)" in shards
    assert "os.killpg(process.pid, signal.SIGKILL)" in shards
    assert "pytest-file-results-${{ matrix.shard }}/" in shards
    assert "pytest-summary-${{ matrix.shard }}.json" in shards
    assert "pytest-timeout-${{ matrix.shard }}.txt" in shards
    assert "pytest-shard-${{ matrix.shard }}.log" in shards
    assert 'PYTHONUNBUFFERED: "1"' in shards
    assert '"coverage_complete": len(completed) == len(selected)' in shards
    assert "if failures or len(completed) != len(selected):" in shards

    # The process boundary is external to pytest. No per-test timeout plugin,
    # skip rule, threshold reduction, or early max-fail shortcut is introduced.
    assert "pip install pytest-timeout" not in workflow
    assert "--timeout=" not in workflow
    assert "--timeout-method=" not in workflow
    assert "--maxfail" not in workflow
    assert "-x" not in workflow

    assert 'PYTHONFAULTHANDLER: "1"' in shards
    assert "if: always()" in shards
    assert "pytest-shard-${{ matrix.shard }}.txt" in shards

    assert "name: test" in gate
    assert "needs: [quality, test_shards]" in gate
    assert "QUALITY_RESULT: ${{ needs.quality.result }}" in gate
    assert "SHARDS_RESULT: ${{ needs.test_shards.result }}" in gate
    assert 'test "$QUALITY_RESULT" = "success"' in gate
    assert 'test "$SHARDS_RESULT" = "success"' in gate
