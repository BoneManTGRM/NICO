"""Actual collector/provider contract for bounded source architecture and coverage."""
from __future__ import annotations

import base64
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

from nico import snapshot_repository_evidence as snapshot_collector
from nico import hosted_provider_comprehensive_runtime_v1 as hosted_collector
from nico.comprehensive_native_providers import (
    architecture_data_flow_provider,
    deployment_review_provider,
)

SHA = "a" * 40
FILES = {
    "app.py": "import requests\nimport sqlite3\nimport subprocess\n\ndef work():\n    requests.get('https://example.invalid')\n    sqlite3.connect('local.db')\n    subprocess.run(['worker'])\n",
    "client.ts": "import client from './client';\nfetch('/api/items');\n// fetch('/not-executed');\n",
    "Dockerfile": "FROM python:3.12\nEXPOSE 8080\nUSER worker\nCMD [\"python\", \"app.py\"]\n",
    "vercel.json": '{"buildCommand":"npm run build"}',
    "package.json": '{"dependencies":{"example-package":"1.0.0"}}',
    "README.md": "# Repository\n",
}


class Store:
    def __init__(self):
        self.data = {}

    def get(self, collection, key):
        return self.data.get((collection, key))

    def put(self, collection, key, value):
        self.data[(collection, key)] = value
        return value

    def audit(self, *args, **kwargs):
        pass


class SnapshotClient:
    access_mode = "authenticated_read_only"
    credential_used = True
    headers = {}

    def __init__(self, files, *, truncated=False, missing=()):
        self.files = files
        self.truncated = truncated
        self.missing = set(missing)

    def repo_url(self, repository, path=""):
        return "https://api.github.test/repos/owner/repository" + path

    def get_json(self, url, params=None):
        path = url.split("/repos/owner/repository", 1)[-1]
        if path.startswith("/git/trees/"):
            return {"sha": "b" * 40, "truncated": self.truncated,
                    "tree": [{"type": "blob", "path": p, "size": len(t.encode())}
                             for p, t in self.files.items()]}, None
        if path == "/contents":
            return [{"name": p} for p in self.files], None
        if path.startswith("/contents/"):
            name = unquote(path.removeprefix("/contents/"))
            if name in self.missing:
                return None, "404"
            value = self.files.get(name)
            if value is not None:
                return {"type": "file", "size": len(value.encode()),
                        "content": base64.b64encode(value.encode()).decode()}, None
        if path == "/deployments":
            return [], None
        return None, "404"

    def get_commits(self, *args):
        return [], None

    def get_pulls(self, *args):
        return [], None

    def get_workflow_runs(self, *args):
        return [], None


def identities():
    context = {"run_id": "run_source_observation", "repository": "owner/repository",
               "commit_sha": SHA, "customer_id": "customer_test",
               "project_id": "project_test", "evidence_ledger_id": "ledger_test"}
    snapshot = {**context, "status": "attached", "snapshot_id": "snapshot_test",
                "tree_sha": "b" * 40, "captured_at": "2026-09-08T10:00:00Z"}
    return context, snapshot


def collect(kind, monkeypatch, tmp_path, files=None, *, truncated=False, missing=()):
    files = dict(FILES if files is None else files)
    context, snapshot = identities()
    store = Store()
    if kind == "snapshot":
        repository, complexity = snapshot_collector.collect_snapshot_repository_evidence(
            context, snapshot, store=store,
            client=SnapshotClient(files, truncated=truncated, missing=missing))
    else:
        for path, value in files.items():
            target = tmp_path / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(value, encoding="utf-8")
        snapshot["provider"] = "gitlab"
        monkeypatch.setattr(hosted_collector, "checkout_hosted_provider_snapshot",
                            lambda *args, **kwargs: (tmp_path, SHA, []))
        monkeypatch.setattr(hosted_collector, "_load_collection", lambda *args: {})
        envelope = SimpleNamespace(collection_limitations=(), ci_runs=(), ci_jobs=(),
                                   deployments=(), change_requests=(), exact_source_locators=(),
                                   capability_status=())
        monkeypatch.setattr(hosted_collector, "_adapt_payload",
                            lambda *args: SimpleNamespace(envelope=envelope, warnings=()))
        repository, complexity = hosted_collector.collect_hosted_provider_repository_evidence(
            context, snapshot, store=store)
    context["prior_stage_results"] = {
        "immutable_repository_snapshot": {"snapshot": snapshot},
        "repository_and_delivery_evidence": {
            "repository_evidence": repository, "complexity_evidence": complexity}}
    return context, repository, complexity, store


@pytest.mark.parametrize("kind", ["snapshot", "hosted"])
def test_actual_collectors_and_providers_use_source_bound_observations(kind, monkeypatch, tmp_path):
    context, repository, complexity, store = collect(kind, monkeypatch, tmp_path)
    observation = repository["architecture_evidence"]["source_observation"]
    assert observation["run_id"] == context["run_id"]
    assert observation["snapshot_id"] == "snapshot_test"
    assert observation["commit_sha"] == SHA
    assert observation["repository"] == context["repository"]
    assert observation["runtime_topology_verified"] is False
    assert any(row["kind"] == "http_call" for row in observation["interactions"])
    assert any(row["kind"] == "storage_call" for row in observation["interactions"])
    assert any(row["kind"] == "process_call" for row in observation["interactions"])
    assert any(row["kind"] == "import" and row["target"] == "./client" for row in observation["interactions"])
    assert all("retained_text_sha256" not in row for row in observation["input_inventory"])
    assert all(len(row["observed_text_sha256"]) == 64 for row in observation["input_inventory"])
    assert store.get("evidence_items", repository["evidence_id"])["evidence"]["architecture_evidence"] == repository["architecture_evidence"]
    architecture = architecture_data_flow_provider(context)
    deployment = deployment_review_provider(context)
    assert architecture["evidence"]["source_observation"] == observation
    assert architecture["evidence"]["runtime_topology_verified"] is False
    assert architecture["evidence"]["structured_tables"]
    assert deployment["evidence"]["declared_infrastructure"]
    assert deployment["evidence"]["runtime_topology_verified"] is False
    assert deployment["evidence"]["operational_history_is_runtime_topology_proof"] is False
    assert complexity["profile_coverage"]["inventory_complete"] is True
    assert complexity["profile_coverage"]["analyzed_source_files"] <= complexity["profile_coverage"]["sampled_eligible_source_files"]


@pytest.mark.parametrize("damage", ["run_id", "repository", "commit_sha", "snapshot_id", "observation_sha256", "input_hash"])
def test_real_provider_rejects_wrong_identity_and_corrupt_observations(damage, monkeypatch, tmp_path):
    context, repository, _, _ = collect("snapshot", monkeypatch, tmp_path)
    observation = repository["architecture_evidence"]["source_observation"]
    if damage == "input_hash":
        observation["input_inventory"][0]["observed_text_sha256"] = "f" * 64
    else:
        observation[damage] = "wrong"
    for provider in (architecture_data_flow_provider, deployment_review_provider):
        result = provider(context)
        assert result["evidence"]["source_observation_status"] == "unavailable"
        assert not result["evidence"].get("source_observation")
        assert not result["evidence"].get("structured_tables")
        assert result["unavailable_data_notes"]


def test_incomplete_inventory_and_unreadable_named_source_cannot_claim_whole_coverage(monkeypatch, tmp_path):
    context, repository, complexity, _ = collect(
        "snapshot", monkeypatch, tmp_path, truncated=True, missing=("app.py",))
    coverage = complexity["profile_coverage"]
    assert coverage["inventory_complete"] is False
    assert coverage["whole_repository_coverage_percent"] is None
    assert coverage["coverage_denominator_scope"] == "observed_paths_only"
    assert "app.py" in coverage["unavailable_paths"]
    assert any("app.py" in note for note in repository["unavailable_data_notes"])


@pytest.mark.parametrize("kind", ["snapshot", "hosted"])
def test_reordered_inputs_preserve_observation_and_sampling(kind, monkeypatch, tmp_path):
    first = collect(kind, monkeypatch, tmp_path, FILES)[1:]
    second = collect(kind, monkeypatch, tmp_path, dict(reversed(list(FILES.items()))))[1:]
    assert first[0]["architecture_evidence"]["source_observation"] == second[0]["architecture_evidence"]["source_observation"]
    assert first[1]["profile_coverage"] == second[1]["profile_coverage"]


def test_observation_does_not_invent_edges_from_comments_or_directory_names(monkeypatch, tmp_path):
    files = {"app.py": "# requests.get('fake')\ntext = 'sqlite3.connect(fake)'\n",
             "web.ts": "// fetch('/fake')\nconst text = 'fetch(fake)';\nconst regex = /fetch(fake)/;\n",
             "database/README.md": "# This directory is not deployment evidence\n"}
    _, repository, _, _ = collect("snapshot", monkeypatch, tmp_path, files)
    observation = repository["architecture_evidence"]["source_observation"]
    assert observation["interactions"] == []
    assert observation["declared_infrastructure"] == []
    assert observation["unknowns"]


def test_profile_keeps_budgets_parser_failures_and_honest_sampling(monkeypatch, tmp_path):
    files = {f"source_{i:03}.py": "def f():\n    return 1\n" for i in range(100)}
    files["source_000.py"] = "def broken(:\n"
    files["oversized.py"] = "#" * 240_001
    files["tests/test_excluded.py"] = "def test_f():\n    pass\n"
    _, _, complexity, _ = collect("snapshot", monkeypatch, tmp_path, files)
    coverage = complexity["profile_coverage"]
    assert coverage["file_limit"] == 90
    assert coverage["per_file_byte_limit"] == 240_000
    assert coverage["profiled_text_files"] <= 90
    assert coverage["analyzed_source_files"] == complexity["files_analyzed"]
    assert coverage["whole_repository_coverage_percent"] < 100
    assert coverage["unsampled_eligible_source_files"] > 0
    assert "oversized.py" in coverage["size_excluded_paths"]
    assert "tests/test_excluded.py" in coverage["complexity_excluded_paths"]
    assert any("source_000.py" in note for note in coverage["parser_notes"])


def test_coverage_refuses_foreign_or_overcounted_analysis():
    from nico.repository_profile_coverage_v1 import profile_coverage
    profile = {"tree_paths": ["app.py"], "files": {"foreign.py": "x = 1"},
               "tree_collection_succeeded": True, "tree_truncated": False,
               "unavailable": []}
    with pytest.raises(ValueError, match="profile_sample_outside_inventory"):
        profile_coverage(profile, {"files_analyzed": 1, "parse_notes": []})
    profile["files"] = {"app.py": "x = 1"}
    with pytest.raises(ValueError, match="profile_analyzed_exceeds_sample"):
        profile_coverage(profile, {"files_analyzed": 2, "parse_notes": []})


def test_snapshot_profile_enforces_actual_observed_byte_limit():
    client = SnapshotClient({"app.py": "x" * 240_001})
    original = client.get_json

    def false_size(url, params=None):
        payload, error = original(url, params)
        if isinstance(payload, dict) and payload.get("type") == "file":
            payload["size"] = 10
        return payload, error

    client.get_json = false_size
    text, error = snapshot_collector._text_file(client, "owner/repository", "app.py", SHA)
    assert text is None
    assert "limit" in error


def test_hosted_profile_does_not_follow_symlink_source(tmp_path):
    (tmp_path / "app.py").symlink_to(tmp_path / "absent.py")
    profile = hosted_collector._profile_checkout(tmp_path)
    assert profile["files"] == {}
    assert "app.py" in profile["unavailable_paths"]
    assert "app.py" in profile["tree_paths"]


def test_excluded_source_cannot_satisfy_whole_source_coverage(monkeypatch, tmp_path):
    _, _, complexity, _ = collect("snapshot", monkeypatch, tmp_path, {
        "app.py": "x = 1\n", "tests/test_app.py": "def test_app():\n    pass\n"})
    coverage = complexity["profile_coverage"]
    assert coverage["eligible_source_coverage_percent"] == 100
    assert coverage["whole_repository_coverage_percent"] == 50
    assert coverage["complexity_excluded_source_files"] == 1
