from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from nico.hosted_provider_comprehensive_runtime_v1 import (
    _clone_spec,
    _hosted_url,
    build_hosted_provider_client,
    canonical_repository_label,
    capture_hosted_provider_snapshot,
    checkout_hosted_provider_snapshot,
)
from nico.hosted_provider_comprehensive_safety_patch_v1 import (
    install_hosted_provider_comprehensive_safety_patch,
)
from nico.provider_platform_contract_v1 import ProviderKind

install_hosted_provider_comprehensive_safety_patch()


class MemoryStore:
    def __init__(self) -> None:
        self.data: dict[tuple[str, str], dict] = {}
        self.audits: list[tuple[str, dict, str, str]] = []

    def get(self, collection: str, item_id: str):
        return self.data.get((collection, item_id))

    def put(self, collection: str, item_id: str, value: dict):
        self.data[(collection, item_id)] = value
        return value

    def audit(self, action: str, payload: dict, *, customer_id: str = "", project_id: str = "") -> None:
        self.audits.append((action, payload, customer_id, project_id))


class FakeCollection:
    def __init__(self, provider: ProviderKind, revision: str) -> None:
        self.provider = provider
        self.repository_id = "stable-provider-repository-id"
        self.revision = revision
        self.collected_at = "2026-08-23T11:00:00+00:00"
        self.payload = {
            "revision": revision,
            "repository": {"id": self.repository_id, "name": "repo"},
            "source_tree": [{"path": "src/app.py", "id": "f" * 40, "type": "blob"}],
        }

    def adapt(self):
        envelope = SimpleNamespace(
            access=SimpleNamespace(read_only=True),
            snapshot=SimpleNamespace(
                revision=self.revision,
                source_fingerprint="sha256:" + "a" * 64,
            ),
            identity=SimpleNamespace(
                repository_id=self.repository_id,
                instance_url="https://gitlab.com",
                default_branch="main",
            ),
        )
        return SimpleNamespace(envelope=envelope, warnings=())


class FakeCollector:
    def __init__(self, revision: str) -> None:
        self.revision = revision
        self.calls: list[tuple[str, str]] = []

    def collect(self, repository_id: str, *, revision: str = ""):
        self.calls.append((repository_id, revision))
        return FakeCollection(ProviderKind.GITLAB, revision or self.revision)


def test_major_provider_labels_are_provider_safe_and_unambiguous() -> None:
    assert canonical_repository_label(ProviderKind.GITHUB, "Owner/Repo") == "Owner/Repo"
    assert canonical_repository_label(ProviderKind.GITLAB, "group/subgroup/repo") == "gitlab.com/group/subgroup/repo"
    assert canonical_repository_label(ProviderKind.BITBUCKET_CLOUD, "workspace/repo") == "bitbucket.org/workspace/repo"
    assert canonical_repository_label(
        ProviderKind.AZURE_DEVOPS,
        "repo",
        organization="Org",
        project="Project",
    ) == "dev.azure.com/Org/Project/_git/repo"


@pytest.mark.parametrize(
    "provider,repository",
    (
        (ProviderKind.GITLAB, "group/../repo"),
        (ProviderKind.GITLAB, "group/./repo"),
        (ProviderKind.GITLAB, "https://evil.example/repo"),
        (ProviderKind.GITLAB, "group\\repo"),
        (ProviderKind.BITBUCKET_CLOUD, "workspace"),
        (ProviderKind.AZURE_DEVOPS, "repo/extra"),
    ),
)
def test_provider_repository_coordinates_fail_closed(provider: ProviderKind, repository: str) -> None:
    with pytest.raises(ValueError):
        canonical_repository_label(
            provider,
            repository,
            organization="Org",
            project="Project",
        )


def test_hosted_provider_instance_cannot_be_arbitrary_or_downgraded() -> None:
    assert _hosted_url("https://gitlab.com", host="gitlab.com", default="https://gitlab.com") == "https://gitlab.com"
    for unsafe in (
        "http://gitlab.com",
        "https://evil.example",
        "https://user:pass@gitlab.com",
        "https://gitlab.com?redirect=https://evil.example",
        "https://gitlab.com#fragment",
    ):
        with pytest.raises(ValueError, match="hosted_provider_instance_invalid"):
            _hosted_url(unsafe, host="gitlab.com", default="https://gitlab.com")


def test_server_side_live_client_builders_cover_all_non_github_major_providers() -> None:
    common = {
        "NICO_GITLAB_TOKEN": "gitlab-secret",
        "NICO_BITBUCKET_CLOUD_TOKEN": "bitbucket-secret",
        "NICO_AZURE_DEVOPS_TOKEN": "azure-secret",
        "NICO_AZURE_DEVOPS_ORGANIZATION": "Org",
        "NICO_AZURE_DEVOPS_PROJECT": "Project",
    }
    clients = [
        build_hosted_provider_client(ProviderKind.GITLAB, {}, environ=common),
        build_hosted_provider_client(ProviderKind.BITBUCKET_CLOUD, {}, environ=common),
        build_hosted_provider_client(ProviderKind.AZURE_DEVOPS, {}, environ=common),
    ]
    try:
        assert [client.provider.value for client in clients] == ["gitlab", "bitbucket", "azure_devops"]
        assert all(client.credential.secret.reveal() for client in clients)
        assert all("secret" not in repr(client.credential.reference).casefold() for client in clients)
    finally:
        for client in clients:
            client.close()


def test_provider_snapshot_is_exact_revision_bound_and_persists_no_raw_secret() -> None:
    revision = "b" * 40
    store = MemoryStore()
    collector = FakeCollector(revision)
    snapshot = capture_hosted_provider_snapshot(
        {
            "run_id": "comprun_provider_parity",
            "provider_repository": "group/repo",
            "customer_id": "customer-1",
            "project_id": "project-1",
            "expected_commit_sha": revision,
        },
        ProviderKind.GITLAB,
        collector=collector,
        store=store,
    )
    assert collector.calls == [("group/repo", revision)]
    assert snapshot["status"] == "attached"
    assert snapshot["provider"] == "gitlab"
    assert snapshot["repository"] == "gitlab.com/group/repo"
    assert snapshot["commit_sha"] == revision
    assert snapshot["exact_commit_verified"] is True
    assert snapshot["tree_identity_type"] == "provider_snapshot_manifest_sha256"
    assert snapshot["human_review_required"] is True
    assert snapshot["client_delivery_allowed"] is False


def test_provider_snapshot_rejects_revision_drift() -> None:
    expected = "c" * 40

    class DriftingCollector(FakeCollector):
        def collect(self, repository_id: str, *, revision: str = ""):
            self.calls.append((repository_id, revision))
            return FakeCollection(ProviderKind.GITLAB, "d" * 40)

    with pytest.raises(ValueError, match="provider_snapshot_revision_mismatch"):
        capture_hosted_provider_snapshot(
            {
                "run_id": "comprun_revision_drift",
                "provider_repository": "group/repo",
                "customer_id": "customer-1",
                "project_id": "project-1",
                "expected_commit_sha": expected,
            },
            ProviderKind.GITLAB,
            collector=DriftingCollector(expected),
            store=MemoryStore(),
        )


def test_clone_specs_use_https_without_embedding_credentials() -> None:
    expected = {
        "gitlab.com/group/repo": ("gitlab", "https://gitlab.com/group/repo.git"),
        "bitbucket.org/workspace/repo": ("bitbucket_cloud", "https://bitbucket.org/workspace/repo.git"),
        "dev.azure.com/Org/Project/_git/repo": ("azure_devops", "https://dev.azure.com/Org/Project/_git/repo"),
    }
    for repository, (provider, clone_url) in expected.items():
        spec = _clone_spec(repository)
        assert spec is not None
        assert spec[0].value == provider
        assert spec[1] == clone_url
        assert spec[1].startswith("https://")
        assert "@" not in spec[1]
        assert "token" not in spec[1].casefold()


def test_exact_checkout_uses_ephemeral_askpass_not_secret_bearing_commands(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    revision = "e" * 40
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    @dataclass
    class Result:
        returncode: int = 0
        stdout: str = ""
        stderr: str = ""

    def runner(command, **kwargs):
        commands.append(list(command))
        environments.append(dict(kwargs.get("env") or {}))
        if command[-2:] == ["rev-parse", "HEAD"]:
            return Result(stdout=revision + "\n")
        return Result()

    monkeypatch.setattr("nico.hosted_provider_comprehensive_runtime_v1.shutil.which", lambda _: "/usr/bin/git")
    monkeypatch.setattr("nico.scanner_worker.directory_size", lambda _: 0)
    repo_path, actual, notes = checkout_hosted_provider_snapshot(
        "gitlab.com/group/repo",
        revision,
        tmp_path,
        {"PATH": "/usr/bin"},
        environ={"NICO_GITLAB_TOKEN": "super-secret-provider-token"},
        runner=runner,
    )
    assert repo_path == tmp_path / "repo"
    assert actual == revision
    assert notes == []
    assert all("super-secret-provider-token" not in " ".join(command) for command in commands)
    assert any(env.get("NICO_GIT_AUTH_PASSWORD") == "super-secret-provider-token" for env in environments)
    askpass = (tmp_path / "nico-provider-git-askpass.sh").read_text(encoding="utf-8")
    assert "super-secret-provider-token" not in askpass
    assert "NICO_GIT_AUTH_PASSWORD" in askpass


def test_production_bootstrap_binds_provider_parity_without_saas_surface() -> None:
    source = Path("nico/api/spanish_final_report_bootstrap.py").read_text(encoding="utf-8")
    runtime = Path("nico/hosted_provider_comprehensive_runtime_v1.py").read_text(encoding="utf-8")
    safety = Path("nico/hosted_provider_comprehensive_safety_patch_v1.py").read_text(encoding="utf-8")
    assert 'VERSION = "nico.api.spanish_final_report_bootstrap.v7"' in source
    assert "install_hosted_provider_comprehensive_safety_patch()" in source
    assert "install_hosted_provider_comprehensive_runtime(app)" in source
    assert '"gitlab_comprehensive_runtime_bound"' in source
    assert '"bitbucket_cloud_comprehensive_runtime_bound"' in source
    assert '"azure_devops_comprehensive_runtime_bound"' in source
    assert '"same_scanner_pipeline"' in source
    assert '"same_candidate_triage_report_pipeline"' in source
    assert 'OPERATOR_INTAKE_ROUTE = "/providers/operator/comprehensive-intake"' in runtime
    assert '"customer_self_service": False' in runtime
    assert '"human_review_required": True' in runtime
    assert '"client_delivery_allowed": False' in runtime
    assert 'part in {"", ".", ".."}' in safety
    assert "verify=False" not in runtime
    assert "shell=True" not in runtime
