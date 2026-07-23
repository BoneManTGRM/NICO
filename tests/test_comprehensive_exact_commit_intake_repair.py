from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "nico" / "comprehensive_exact_commit_intake_repair.py"
SHA = "76274f2d54025efb5080d2922c12f83397ad685d"


def _load_module() -> ModuleType:
    spec = importlib.util.spec_from_file_location("comprehensive_exact_commit_intake_repair_under_test", MODULE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeClient:
    def __init__(self, responses: dict[str, tuple[Any, str | None]]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str] | None]] = []

    @staticmethod
    def repo_url(repository: str, path: str) -> str:
        return f"https://api.github.test/repos/{repository}{path}"

    def get_json(self, url: str, params: dict[str, str] | None = None):
        self.calls.append((url, params))
        return self.responses.get(url, (None, "not found"))


def test_git_commit_api_fallback_reconstructs_commit_shape() -> None:
    module = _load_module()
    repository = "BoneManTGRM/NICO"
    git_url = FakeClient.repo_url(repository, f"/git/commits/{SHA}")
    client = FakeClient(
        {
            git_url: (
                {
                    "sha": SHA,
                    "message": "Release commit",
                    "author": {"date": "2026-07-23T16:52:55Z"},
                    "committer": {"date": "2026-07-23T16:52:55Z"},
                    "tree": {"sha": "a" * 40},
                },
                None,
            )
        }
    )

    commit, error = module._git_commit_fallback(client, repository, SHA)

    assert error is None
    assert commit is not None
    assert commit["sha"] == SHA
    assert commit["commit"]["message"] == "Release commit"
    assert commit["commit"]["tree"]["sha"] == "a" * 40
    assert commit["verification_source"] == "github_git_commit_api"


def test_contents_exact_ref_fallback_verifies_sha_when_commit_endpoint_is_limited() -> None:
    module = _load_module()
    repository = "BoneManTGRM/NICO"
    git_url = FakeClient.repo_url(repository, f"/git/commits/{SHA}")
    contents_url = FakeClient.repo_url(repository, "/contents")
    client = FakeClient(
        {
            git_url: (None, "GitHub returned 422"),
            contents_url: ([{"name": "README.md", "type": "file"}], None),
        }
    )

    commit, error = module._git_commit_fallback(client, repository, SHA)

    assert error is None
    assert commit is not None
    assert commit["sha"] == SHA
    assert commit["verification_source"] == "github_contents_exact_ref"
    assert client.calls[-1] == (contents_url, {"ref": SHA})


def test_fallback_never_invents_success_when_all_exact_ref_reads_fail() -> None:
    module = _load_module()
    repository = "BoneManTGRM/NICO"
    client = FakeClient({})

    commit, error = module._git_commit_fallback(client, repository, SHA)

    assert commit is None
    assert error
