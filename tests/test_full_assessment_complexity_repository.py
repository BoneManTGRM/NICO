from __future__ import annotations

from nico.full_assessment_complexity_repository import collect_repository_complexity_evidence
from nico.storage import MemoryAdapter


class FakeGitHubClient:
    def __init__(self) -> None:
        self.calls = 0
        self.files = {
            "nico/alpha.py": """
from nico.storage import STORE

def calculate(value):
    if value > 0:
        return value + 1
    return 0
""",
            "nico/beta.py": """
from .alpha import calculate

def run(value):
    return calculate(value)
""",
            "tests/test_alpha.py": "def test_alpha():\n    assert True\n",
        }

    def get_repo(self, repo: str):
        self.calls += 1
        return {
            "full_name": repo,
            "default_branch": "main",
            "private": True,
            "visibility": "private",
        }, None

    def get_tree(self, _repo: str, _branch: str):
        self.calls += 1
        return [{"type": "blob", "path": path, "size": len(text)} for path, text in self.files.items()], None

    def get_contents(self, _repo: str, path: str = ""):
        self.calls += 1
        if path:
            return None, "404"
        return [{"name": "nico"}, {"name": "tests"}], None

    def get_text_file(self, _repo: str, path: str):
        self.calls += 1
        if path in self.files:
            return self.files[path], None
        return None, "404"


class UnexpectedClient:
    def get_repo(self, _repo: str):
        raise AssertionError("persisted same-run complexity evidence should be reused")


class DeniedClient:
    def get_repo(self, _repo: str):
        return None, "GitHub returned 403: provider secret detail"


def _context(run_id: str = "fullrun_complexity") -> dict:
    return {
        "run_id": run_id,
        "repository": "BoneManTGRM/NICO",
        "customer_id": "cust-complexity",
        "project_id": "proj-complexity",
        "authorization_scope": "repository assessment only",
    }


def test_repository_complexity_evidence_is_run_bound_and_persisted() -> None:
    store = MemoryAdapter()
    result = collect_repository_complexity_evidence(
        _context(),
        client=FakeGitHubClient(),
        store=store,
    )

    assert result["status"] == "attached"
    assert result["run_id"] == "fullrun_complexity"
    assert result["repository"] == "BoneManTGRM/NICO"
    assert result["source"] == "github_api_bounded_complexity_analysis"
    assert result["files_analyzed"] == 2
    assert result["functions_measured"] == 2
    assert result["evidence_id"].startswith("evidence_complexity_")
    record = store.get("evidence_items", result["evidence_id"])
    assert record is not None
    assert record["run_id"] == "fullrun_complexity"
    assert record["filename"] == "full-assessment-complexity-evidence.json"
    assert record["evidence"]["analyzer_version"] in {
        "nico-bounded-complexity-v1",
        "nico-bounded-complexity-v2",
    }


def test_repository_complexity_evidence_reuses_same_run_artifact() -> None:
    store = MemoryAdapter()
    first = collect_repository_complexity_evidence(
        _context("fullrun_complexity_reuse"),
        client=FakeGitHubClient(),
        store=store,
    )
    second = collect_repository_complexity_evidence(
        _context("fullrun_complexity_reuse"),
        client=UnexpectedClient(),
        store=store,
    )

    assert first["evidence_id"] == second["evidence_id"]
    assert second["idempotent_reuse"] is True
    assert len(store.list("evidence_items")) == 1


def test_repository_complexity_access_failure_is_sanitized() -> None:
    store = MemoryAdapter()
    result = collect_repository_complexity_evidence(
        _context("fullrun_complexity_denied"),
        client=DeniedClient(),
        store=store,
    )

    assert result["status"] == "unavailable"
    assert result["human_review_required"] is True
    note = result["unavailable_data_notes"][0]
    assert "lacks required read access" in note
    assert "provider secret detail" not in note
    assert store.get("evidence_items", result["evidence_id"]) is not None


def test_complexity_evidence_identity_changes_with_run_id() -> None:
    store = MemoryAdapter()
    first = collect_repository_complexity_evidence(
        _context("fullrun_complexity_a"),
        client=FakeGitHubClient(),
        store=store,
    )
    second = collect_repository_complexity_evidence(
        _context("fullrun_complexity_b"),
        client=FakeGitHubClient(),
        store=store,
    )

    assert first["evidence_id"] != second["evidence_id"]
