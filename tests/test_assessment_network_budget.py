from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace

import nico.assessment_network_budget as budget
import nico.hosted_assessment as hosted
import nico.snapshot_repository_evidence as snapshot_evidence


class FakeResponse:
    status_code = 200

    def json(self):
        return {"ok": True}


class FakeClient:
    def __init__(self):
        self.headers = {"User-Agent": "test"}
        self._nico_collection_started = time.monotonic()
        self._nico_collection_deadline = self._nico_collection_started + budget.GITHUB_COLLECTION_BUDGET_SECONDS
        self.calls: list[str] = []

    def get_tree(self, _repo: str, _branch: str):
        return [
            {"type": "blob", "path": "README.md", "size": 12},
            {"type": "blob", "path": "requirements.txt", "size": 12},
            {"type": "blob", "path": "nico/a.py", "size": 12},
            {"type": "blob", "path": "nico/b.py", "size": 12},
        ], None

    def get_contents(self, _repo: str, path: str = ""):
        if not path:
            return [{"name": "nico"}, {"name": "README.md"}], None
        return None, "not used"

    def get_text_file(self, _repo: str, path: str):
        self.calls.append(path)
        return f"content:{path}", None


def test_collection_policy_is_finite_and_parallel():
    policy = budget.collection_policy()

    assert 2 <= policy["github_request_timeout_seconds"] <= 25
    assert 30 <= policy["github_collection_budget_seconds"] <= 180
    assert 1 <= policy["github_file_fetch_workers"] <= 12
    assert 2 <= policy["osv_request_timeout_seconds"] <= 20
    assert "returns instead of waiting indefinitely" in policy["rule"]


def test_bounded_get_json_refuses_new_network_call_after_budget(monkeypatch):
    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network should not be called after the budget expires")

    monkeypatch.setattr(budget.requests, "get", forbidden)
    client = SimpleNamespace(headers={}, _nico_collection_deadline=time.monotonic() - 1)

    value, error = budget._bounded_get_json(client, "https://api.github.com/example")

    assert value is None
    assert "time budget was exhausted" in str(error)
    assert called is False


def test_bounded_get_json_uses_short_remaining_timeout(monkeypatch):
    observed: dict[str, float] = {}

    def fake_get(_url, **kwargs):
        observed["timeout"] = float(kwargs["timeout"])
        return FakeResponse()

    monkeypatch.setattr(budget.requests, "get", fake_get)
    client = SimpleNamespace(headers={}, _nico_collection_deadline=time.monotonic() + 1.25)

    value, error = budget._bounded_get_json(client, "https://api.github.com/example")

    assert value == {"ok": True}
    assert error is None
    assert 0.5 <= observed["timeout"] <= 1.25


def test_parallel_fetch_runs_more_than_one_file_at_a_time():
    lock = threading.Lock()
    active = 0
    maximum = 0

    def fetch(path: str):
        nonlocal active, maximum
        with lock:
            active += 1
            maximum = max(maximum, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return f"text:{path}", None

    result = budget._parallel_fetch([f"file-{index}" for index in range(8)], fetch)

    assert len(result) == 8
    assert maximum > 1
    assert all(value[0] for value in result.values())


def test_express_repository_profile_fetches_selected_files_with_budget_metadata():
    client = FakeClient()

    profile = budget._bounded_repository_profile(client, "owner/repo", {"default_branch": "main"})

    assert set(profile["files"]) == {"README.md", "requirements.txt", "nico/a.py", "nico/b.py"}
    assert profile["root_items"] == ["nico", "README.md"]
    assert profile["collection_budget"]["budget_seconds"] == budget.GITHUB_COLLECTION_BUDGET_SECONDS
    assert profile["collection_budget"]["budget_exhausted"] is False


def test_installer_patches_hosted_and_snapshot_collectors_once():
    first = budget.install_assessment_network_budget()
    second = budget.install_assessment_network_budget()

    assert first["status"] in {"installed", "already_installed"}
    assert second["status"] == "already_installed"
    assert hosted.fetch_repository_profile is budget._bounded_repository_profile
    assert hosted.fetch_workflows is budget._bounded_workflows
    assert hosted.query_osv is budget._bounded_query_osv
    assert snapshot_evidence._profile is budget._bounded_snapshot_profile
    assert getattr(hosted.GitHubAssessmentClient, "_nico_budget_installed", False) is True


def test_frontend_guard_bounds_both_express_and_mid_requests():
    source = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "web"
        / "app"
        / "AssessmentRequestGuard.tsx"
    ).read_text(encoding="utf-8")
    layout = (
        Path(__file__).resolve().parents[1]
        / "apps"
        / "web"
        / "app"
        / "layout.tsx"
    ).read_text(encoding="utf-8")

    assert '"/assessment/github"' in source
    assert '"/assessment/mid-run"' in source
    assert "120_000" in source
    assert "AbortController" in source
    assert "controller.abort" in source
    assert "leaving the Run button spinning" in source
    assert "window.clearTimeout" in source
    assert 'import AssessmentRequestGuard from "./AssessmentRequestGuard"' in layout
    assert "<AssessmentRequestGuard />" in layout
