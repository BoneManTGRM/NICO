"""Owned Git objects only: these tests never compile or execute assessed files."""
import hashlib
import subprocess
from pathlib import Path

import pytest

from nico import repository_snapshot as snapshot
from nico import snapshot_repository_evidence as evidence


@pytest.fixture
def frozen_git(tmp_path):
    root = tmp_path / "objects.git"
    root.mkdir()
    env = snapshot._git_environment(tmp_path)

    def git(*args, data=None):
        result = subprocess.run(["git", "-c", "user.name=NICO synthetic control",
            "-c", "user.email=synthetic@example.invalid", "-c", "core.hooksPath=/dev/null", *args],
            cwd=root, env=env, input=data, capture_output=True, check=True)
        return result.stdout.strip().decode("ascii")

    git("init", "--bare", ".")
    files = {"raw.cpp": b"// original bytes: \xff\r\nint value() { return 1; }\r\n",
             "value.hpp": b"int value();\n"}
    blobs = {name: git("hash-object", "-w", "--stdin", data=raw) for name, raw in files.items()}
    tree = git("mktree", "-z", data=b"".join(
        f"100644 blob {blobs[name]}\t{name}".encode() + b"\0" for name in sorted(files)))
    revision = git("commit-tree", tree, "-m", "Owned inert C++ source fixture")
    return root, env, git, files, tree, revision


def materialize(frozen_git, destination, **overrides):
    root, env, _, files, tree, revision = frozen_git
    values = {"git_dir": root, "commit_sha": revision,
        "expected_tree_sha": tree, "inputs": {p: hashlib.sha256(b).hexdigest() for p, b in files.items()},
        "destination": destination, "max_files": 4, "max_file_bytes": 1024,
        "max_total_bytes": 2048, "timeout_seconds": 5}
    values.update(overrides)
    return evidence.materialize_exact_git_inputs(**values)


def test_original_bytes_and_complete_input_membership_survive_materialization(frozen_git, tmp_path):
    output = tmp_path / "executor-input"
    receipt = materialize(frozen_git, output)
    files = frozen_git[3]
    assert {p.name: p.read_bytes() for p in output.iterdir()} == files
    assert receipt["commit_sha"] == frozen_git[5]
    assert receipt["tree_sha"] == frozen_git[4]
    assert receipt["required_count"] == receipt["materialized_count"] == 2
    assert receipt["source_bytes"] == sum(map(len, files.values()))
    assert receipt["inputs"] == {p: hashlib.sha256(b).hexdigest() for p, b in files.items()}
    assert receipt["analyzed_count"] is None
    assert receipt["authorized"] is False
    assert receipt["assessed_code_executed"] is False


def test_wrong_digest_fails_without_publishing_partial_inputs(frozen_git, tmp_path):
    output = tmp_path / "executor-input"
    with pytest.raises(ValueError, match="input_digest_mismatch"):
        materialize(frozen_git, output, inputs={"raw.cpp": "0" * 64})
    assert not output.exists()


def test_lost_worker_lease_interrupts_git_acquisition_without_partial_publication(frozen_git, tmp_path):
    calls = []
    def checkpoint():
        calls.append(True)
        if len(calls) == 3:
            raise ValueError('synthetic_lease_lost')
    destination = tmp_path / 'cancelled-input'
    with pytest.raises(ValueError, match='synthetic_lease_lost'):
        materialize(frozen_git, destination, checkpoint=checkpoint)
    assert len(calls) == 3 and not destination.exists()


def test_git_object_compatibility_digest_works_when_security_sha1_is_disabled(frozen_git, tmp_path, monkeypatch):
    original = hashlib.sha1
    def restricted_sha1(data=b'', *, usedforsecurity=True):
        if usedforsecurity:
            raise ValueError('security_sha1_disabled')
        return original(data, usedforsecurity=False)
    monkeypatch.setattr(hashlib, 'sha1', restricted_sha1)
    output = tmp_path / 'fips-input'
    assert materialize(frozen_git, output)['materialized_count'] == 2
    with pytest.raises(ValueError, match='input_digest_mismatch'):
        materialize(frozen_git, tmp_path / 'wrong-input', inputs={'raw.cpp': '0' * 64})


@pytest.mark.parametrize("corruption", ["truncate", "append", "header", "bytes"])
def test_corrupted_batch_never_publishes_inputs(frozen_git, tmp_path, monkeypatch, corruption):
    original = evidence._bounded_git_bytes
    def corrupt(*args, **kwargs):
        raw = original(*args, **kwargs)
        if "cat-file" in args[2]:
            if corruption == "truncate":
                return raw[:-2]
            if corruption == "append":
                return raw + b"unexpected extra object"
            if corruption == "header":
                return b"0" * 40 + raw[40:]
            return raw.replace(b"int value", b"INT value", 1)
        return raw
    monkeypatch.setattr(evidence, "_bounded_git_bytes", corrupt)
    output = tmp_path / "executor-input"
    with pytest.raises(ValueError):
        materialize(frozen_git, output)
    assert not output.exists()


def test_git_capture_enforces_actual_output_and_expired_deadline(frozen_git):
    import time
    root, env, _, _, _, revision = frozen_git
    with pytest.raises(ValueError, match="output_budget_exceeded"):
        evidence._bounded_git_bytes(root, env, ["show", revision + ":raw.cpp"],
                                    limit=8, deadline=time.monotonic() + 5)
    with pytest.raises(ValueError, match="acquisition_timed_out"):
        evidence._bounded_git_bytes(root, env, ["show", revision],
                                    limit=1000, deadline=time.monotonic() - 1)


def test_materialization_never_inherits_credential_or_git_overrides(frozen_git, tmp_path, monkeypatch):
    original = evidence._bounded_git_bytes
    observed = []
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-do-not-forward")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    def capture(git_dir, environment, *args, **kwargs):
        observed.append(dict(environment))
        return original(git_dir, environment, *args, **kwargs)
    monkeypatch.setattr(evidence, "_bounded_git_bytes", capture)
    materialize(frozen_git, tmp_path / "executor-input")
    assert observed
    assert all("GITHUB_TOKEN" not in env and "GIT_CONFIG_COUNT" not in env for env in observed)
    assert all(env["GIT_NO_LAZY_FETCH"] == "1" and env["GIT_CONFIG_NOSYSTEM"] == "1" for env in observed)


@pytest.mark.parametrize("change", [{"max_files": 1}, {"max_file_bytes": 8}, {"max_total_bytes": 8}])
def test_required_inputs_cannot_be_dropped_to_fit_budget(frozen_git, tmp_path, change):
    output = tmp_path / "executor-input"
    with pytest.raises(ValueError, match="input_budget_exceeded"):
        materialize(frozen_git, output, **change)
    assert not output.exists()


@pytest.mark.parametrize("path", ["../raw.cpp", "/raw.cpp", "a/../raw.cpp", "a//raw.cpp",
    "a\\raw.cpp", ".git/config", "a\nraw.cpp", "missing.cpp"])
def test_unsafe_or_missing_required_path_cannot_become_complete(frozen_git, tmp_path, path):
    output = tmp_path / "executor-input"
    with pytest.raises(ValueError):
        materialize(frozen_git, output, inputs={path: "0" * 64})
    assert not output.exists()


def test_wrong_revision_or_tree_is_rejected(frozen_git, tmp_path):
    for change in [{"commit_sha": "f" * 40}, {"expected_tree_sha": "f" * 40}]:
        with pytest.raises(ValueError):
            materialize(frozen_git, tmp_path / "executor-input", **change)


def test_existing_directory_is_never_repurposed(frozen_git, tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    (output / "unrelated").write_bytes(b"keep")
    with pytest.raises(ValueError, match="destination_exists"):
        materialize(frozen_git, output)
    assert (output / "unrelated").read_bytes() == b"keep"


@pytest.mark.parametrize("kind", ["symlink", "submodule", "lfs"])
def test_nonmaterialized_content_is_explicitly_unsupported(frozen_git, tmp_path, kind):
    root, env, git, _, _, revision = frozen_git
    content = b"version https://git-lfs.github.com/spec/v1\noid sha256:" + b"a" * 64 + b"\nsize 9\n"
    blob = git("hash-object", "-w", "--stdin", data=content)
    mode, typ, oid = ("120000", "blob", blob) if kind == "symlink" else (
        ("160000", "commit", revision) if kind == "submodule" else ("100644", "blob", blob))
    tree = git("mktree", data=f"{mode} {typ} {oid}\tvalue.cpp\n".encode())
    commit = git("commit-tree", tree, "-m", "Inert unsupported input fixture")
    output = tmp_path / "executor-input"
    with pytest.raises(ValueError, match="input_type_unsupported"):
        materialize(frozen_git, output, commit_sha=commit, expected_tree_sha=tree,
                    inputs={"value.cpp": hashlib.sha256(content).hexdigest()})
    assert not output.exists()
