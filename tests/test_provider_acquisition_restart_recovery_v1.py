from __future__ import annotations

from types import SimpleNamespace

from nico.hosted_provider_comprehensive_runtime_v1 import capture_hosted_provider_snapshot
from nico.provider_platform_contract_v1 import ProviderKind


class SharedEvidenceStore:
    def __init__(self, data: dict | None = None) -> None:
        self.data = data if data is not None else {}
        self.audit_events: list[tuple] = []

    def get(self, collection: str, item_id: str):
        return self.data.get((collection, item_id))

    def put(self, collection: str, item_id: str, value: dict):
        self.data[(collection, item_id)] = value
        return value

    def audit(self, action: str, payload: dict, *, customer_id: str = "", project_id: str = "") -> None:
        self.audit_events.append((action, payload, customer_id, project_id))


class Collection:
    def __init__(self, revision: str) -> None:
        self.revision = revision
        self.collected_at = "2026-08-23T23:00:00Z"
        self.access_mode = "anonymous_public"
        self.credential_used = False
        self.pagination_complete = True
        self.rate_limit_state = {}
        self.collection_limitations = ()
        self.payload = {
            "revision": revision,
            "repository": {"id": "gitlab-repo-1", "name": "repo"},
            "source_tree": [{"path": "src/app.py", "id": "f" * 40, "type": "blob"}],
        }

    def adapt(self):
        return SimpleNamespace(
            warnings=(),
            envelope=SimpleNamespace(
                access=SimpleNamespace(read_only=True),
                snapshot=SimpleNamespace(
                    revision=self.revision,
                    source_fingerprint="sha256:" + "b" * 64,
                ),
                identity=SimpleNamespace(
                    repository_id="gitlab-repo-1",
                    instance_url="https://gitlab.com",
                    default_branch="main",
                ),
            ),
        )


class Collector:
    def __init__(self, revision: str) -> None:
        self.revision = revision
        self.calls = 0

    def collect(self, repository_id: str, *, revision: str = ""):
        self.calls += 1
        assert repository_id == "group/repo"
        assert revision == self.revision
        return Collection(self.revision)


class MustNotRunCollector:
    def collect(self, *args, **kwargs):
        raise AssertionError("durable snapshot recovery must not reacquire provider evidence")


def test_provider_snapshot_recovers_idempotently_after_process_restart() -> None:
    revision = "a" * 40
    shared_data: dict = {}
    first_process_store = SharedEvidenceStore(shared_data)
    collector = Collector(revision)
    context = {
        "run_id": "comprun_provider_restart",
        "customer_id": "customer-1",
        "project_id": "project-1",
        "provider_repository": "group/repo",
        "commit_sha": revision,
    }

    first = capture_hosted_provider_snapshot(
        context,
        ProviderKind.GITLAB,
        collector=collector,
        store=first_process_store,
    )
    assert collector.calls == 1
    assert first["status"] == "attached"
    assert first["exact_commit_verified"] is True
    assert first["idempotent_reuse"] is False
    assert first["human_review_required"] is True
    assert first["client_delivery_allowed"] is False

    restarted_process_store = SharedEvidenceStore(shared_data)
    recovered = capture_hosted_provider_snapshot(
        context,
        ProviderKind.GITLAB,
        collector=MustNotRunCollector(),
        store=restarted_process_store,
    )

    assert recovered["snapshot_id"] == first["snapshot_id"]
    assert recovered["commit_sha"] == first["commit_sha"]
    assert recovered["provider"] == first["provider"]
    assert recovered["provider_repository_id"] == first["provider_repository_id"]
    assert recovered["idempotent_reuse"] is True
    assert recovered["human_review_required"] is True
    assert recovered["client_delivery_allowed"] is False


def test_changed_run_identity_does_not_reuse_another_runs_provider_snapshot() -> None:
    revision = "c" * 40
    store = SharedEvidenceStore()
    first_context = {
        "run_id": "comprun_provider_restart_a",
        "customer_id": "customer-1",
        "project_id": "project-1",
        "provider_repository": "group/repo",
        "commit_sha": revision,
    }
    first = capture_hosted_provider_snapshot(
        first_context,
        ProviderKind.GITLAB,
        collector=Collector(revision),
        store=store,
    )

    second_context = dict(first_context, run_id="comprun_provider_restart_b")
    second_collector = Collector(revision)
    second = capture_hosted_provider_snapshot(
        second_context,
        ProviderKind.GITLAB,
        collector=second_collector,
        store=store,
    )

    assert second_collector.calls == 1
    assert second["snapshot_id"] != first["snapshot_id"]
    assert second["idempotent_reuse"] is False
