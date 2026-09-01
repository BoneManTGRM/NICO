from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace

import pytest

from nico.hosted_provider_comprehensive_runtime_v1 import (
    _access_mode,
    _clone_spec,
    _hosted_url,
    assert_no_raw_provider_credentials,
    build_hosted_provider_client,
    canonical_repository_label,
    capture_hosted_provider_snapshot,
    checkout_hosted_provider_snapshot,
    normalize_submitted_provider_repository,
)
from nico.provider_neutral_contract import ProviderAccessMode
from nico.provider_platform_contract_v1 import ProviderKind


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
        self.access_mode = "anonymous_public"
        self.credential_used = False
        self.pagination_complete = True
        self.rate_limit_state = {}
        self.collection_limitations = ()
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


def test_public_intake_provider_helpers_cover_anonymous_access_and_exact_hosts() -> None:
    assert _access_mode("") is ProviderAccessMode.AUTO
    assert _access_mode("anonymous_public") is ProviderAccessMode.ANONYMOUS_PUBLIC
    assert _access_mode("authenticated_read_only") is ProviderAccessMode.AUTHENTICATED_READ_ONLY

    assert normalize_submitted_provider_repository("Owner/Repo", "", organization="", project="") == (
        ProviderKind.GITHUB,
        "Owner/Repo",
        "",
        "",
    )
    assert normalize_submitted_provider_repository(
        "https://gitlab.com/group/sub/repo.git",
        "gitlab",
        organization="",
        project="",
    ) == (ProviderKind.GITLAB, "group/sub/repo", "", "")
    assert normalize_submitted_provider_repository(
        "https://bitbucket.org/workspace/repo",
        "bitbucket_cloud",
        organization="",
        project="",
    ) == (ProviderKind.BITBUCKET_CLOUD, "workspace/repo", "", "")
    assert normalize_submitted_provider_repository(
        "https://dev.azure.com/Org/Project/_git/repo",
        "azure_devops",
        organization="",
        project="",
    ) == (ProviderKind.AZURE_DEVOPS, "repo", "Org", "Project")


def test_public_intake_provider_helpers_fail_closed_for_secret_keys_and_host_mismatch() -> None:
    with pytest.raises(ValueError, match="raw_provider_credentials_prohibited"):
        assert_no_raw_provider_credentials({"token": "must-not-cross-public-boundary"})

    with pytest.raises(ValueError, match="provider_repository_selection_mismatch"):
        normalize_submitted_provider_repository(
            "https://gitlab.com/group/repo",
            "github",
            organization="",
            project="",
        )


@pytest.mark.parametrize(
    "provider,repository",
    (
        (ProviderKind.GITLAB, "group/../repo"),
        (ProviderKind.GITLAB, "group/./repo"),
        (ProviderKind.GITLAB, "https://evil.example/repo"),
        (ProviderKind.GITLAB, "group\\repo"),
        (ProviderKind.BITBUCKET_CLOUD, "workspace"),
        (ProviderKind.BITBUCKET_CLOUD, "workspace/repo/extra"),
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


def test_azure_provider_coordinates_reject_dot_segments() -> None:
    for organization, project in (("..", "Project"), ("Org", ".")):
        with pytest.raises(ValueError, match="azure_provider_coordinates_invalid"):
            canonical_repository_label(
                ProviderKind.AZURE_DEVOPS,
                "repo",
                organization=organization,
                project=project,
            )


def test_hosted_provider_instance_cannot_be_arbitrary_or_downgraded() -> None:
    assert _hosted_url("https://gitlab.com", host="gitlab.com", default="https://gitlab.com") == "https://gitlab.com"
    for unsafe in (
        "http://gitlab.com",
        "https://evil.example",
        "https://gitlab.com.evil.example",
        "https://user:pass@gitlab.com",
        "https://gitlab.com:443",
        "https://gitlab.com/api/v4",
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
        build_hosted_provider_client(
            ProviderKind.GITLAB,
            {"provider_access_mode": "authenticated_read_only"},
            environ=common,
        ),
        build_hosted_provider_client(
            ProviderKind.BITBUCKET_CLOUD,
            {"provider_access_mode": "authenticated_read_only"},
            environ=common,
        ),
        build_hosted_provider_client(
            ProviderKind.AZURE_DEVOPS,
            {"provider_access_mode": "authenticated_read_only"},
            environ=common,
        ),
    ]
    try:
        assert [client.provider.value for client in clients] == ["gitlab", "bitbucket", "azure_devops"]
        assert all(client.credential.secret.reveal() for client in clients)
        assert all("secret" not in repr(client.credential.reference).casefold() for client in clients)
    finally:
        for client in clients:
            client.close()


def test_public_live_client_builders_do_not_resolve_configured_credentials() -> None:
    environment = {
        "NICO_GITLAB_TOKEN": "must-not-be-resolved",
        "NICO_BITBUCKET_CLOUD_TOKEN": "must-not-be-resolved",
        "NICO_AZURE_DEVOPS_TOKEN": "must-not-be-resolved",
    }
    contexts = (
        (ProviderKind.GITLAB, {}),
        (ProviderKind.BITBUCKET_CLOUD, {}),
        (
            ProviderKind.AZURE_DEVOPS,
            {"provider_organization": "Org", "provider_project": "Project"},
        ),
    )
    clients = [
        build_hosted_provider_client(provider, context, environ=environment)
        for provider, context in contexts
    ]
    try:
        assert all(client.credential is None for client in clients)
        assert all(client.credential_used is False for client in clients)
        assert all(client.actual_access_mode.value == "anonymous_public" for client in clients)
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


def test_clone_specs_require_exact_host_token_and_canonical_shape() -> None:
    assert _clone_spec("evil.example/gitlab.com/group/repo") is None
    assert _clone_spec("gitlab.com.evil/group/repo") is None
    assert _clone_spec("bitbucket.org.evil/workspace/repo") is None
    assert _clone_spec("dev.azure.com.evil/Org/Project/_git/repo") is None

    for malformed in (
        "https://gitlab.com/group/repo",
        "gitlab.com/group/../repo",
        "gitlab.com/group/./repo",
        "bitbucket.org/workspace/repo/extra",
        "dev.azure.com/Org/Project/_git/repo/extra",
        "dev.azure.com/../Project/_git/repo",
    ):
        with pytest.raises(ValueError):
            _clone_spec(malformed)


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
        access_mode="authenticated_read_only",
        credential_used=True,
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


def test_exact_anonymous_checkout_uses_no_credential_or_auth_helper(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
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
        access_mode="anonymous_public",
        credential_used=False,
        environ={"NICO_GITLAB_TOKEN": "must-not-be-read-or-used"},
        runner=runner,
    )

    assert repo_path == tmp_path / "repo"
    assert actual == revision
    assert notes == []
    assert not (tmp_path / "nico-provider-git-askpass.sh").exists()
    assert all("must-not-be-read-or-used" not in " ".join(command) for command in commands)
    assert all("NICO_GIT_AUTH_PASSWORD" not in environment for environment in environments)
    assert all("GIT_ASKPASS" not in environment for environment in environments)
    assert all("http.followRedirects=false" in command for command in commands)
    assert all("http.extraHeader=" in command for command in commands)


@pytest.mark.parametrize(
    "access_mode,credential_used",
    (("auto", False), ("", False), ("anonymous_public", True), ("authenticated_read_only", False)),
)
def test_exact_hosted_checkout_rejects_unbound_or_inconsistent_access_truth(
    tmp_path: Path,
    access_mode: str,
    credential_used: bool,
) -> None:
    repo_path, actual, notes = checkout_hosted_provider_snapshot(
        "gitlab.com/group/repo",
        "e" * 40,
        tmp_path,
        {"PATH": "/usr/bin"},
        access_mode=access_mode,
        credential_used=credential_used,
        environ={"NICO_GITLAB_TOKEN": "unused"},
    )
    assert repo_path is None
    assert actual == ""
    assert notes == ["provider_snapshot_access_binding_invalid"]


@pytest.mark.parametrize(
    "language,expected",
    (
        ("en", ("Access mode: Anonymous public.", "Provider credential used: No.")),
        ("es-MX", ("Modo de acceso: Público anónimo.", "Credencial del proveedor utilizada: No.")),
    ),
)
def test_provider_access_truth_is_authored_for_report_without_internal_property_labels(
    language: str,
    expected: tuple[str, str],
) -> None:
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime
    from nico.comprehensive_report_package import _stage_summary

    lines = runtime._provider_access_report_evidence(
        {"report_language": language},
        {
            "provider": "gitlab",
            "repository": "gitlab.com/group/repo",
            "commit_sha": "e" * 40,
            "access_mode": "anonymous_public",
            "credential_used": False,
            "required_source_evidence_complete": True,
            "pagination_complete": True,
            "provider_rate_limit_state": {},
            "provider_collection_limitations": [],
            "provider_source_fingerprint": "sha256:" + "a" * 64,
            "snapshot_id": "snapshot-provider",
            "provider_capability_states": [
                {"capability": "tree", "state": "supported", "reason": ""},
                {
                    "capability": "ci_runs",
                    "state": "unavailable_authentication",
                    "reason": "provider authentication required",
                },
            ],
        },
        {"exact_source_locator_count": 1},
    )
    summary = _stage_summary(
        "repository_and_delivery_evidence",
        {"status": "complete", "provider_access_evidence": lines},
    )

    assert expected[0] in summary["evidence"]
    assert expected[1] in summary["evidence"]
    assert any("snapshot-provider" in line for line in summary["evidence"])
    assert all("provider_access_evidence" not in line for line in summary["evidence"])


@pytest.mark.parametrize("language", ("en", "es-MX"))
def test_bitbucket_cloud_internal_provider_value_has_client_facing_label(
    language: str,
) -> None:
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime

    lines = runtime._provider_access_report_evidence(
        {"report_language": language},
        {
            "provider": "bitbucket_cloud",
            "repository": "bitbucket.org/workspace/repository",
            "commit_sha": "e" * 40,
            "access_mode": "anonymous_public",
            "credential_used": False,
            "required_source_evidence_complete": True,
            "pagination_complete": True,
            "provider_rate_limit_state": {},
            "provider_collection_limitations": [],
            "provider_source_fingerprint": "sha256:" + "a" * 64,
            "snapshot_id": "snapshot-provider",
            "provider_capability_states": [
                {"capability": "tree", "state": "supported", "reason": ""}
            ],
        },
        {"exact_source_locator_count": 1},
    )

    assert lines[0] in {"Provider: Bitbucket Cloud.", "Proveedor: Bitbucket Cloud."}
    assert "bitbucket_cloud" not in "\n".join(lines)


@pytest.mark.parametrize(
    "language,expected_lines",
    (
        (
            "en",
            (
                "Provider: GitHub.",
                "Access mode: Anonymous public.",
                "Provider credential used: No.",
                "Required source evidence complete: Yes.",
                "Pagination complete: No.",
                "Human review: Required.",
                "Human approval: Pending explicit reviewer action.",
                "Client delivery: Not authorized.",
            ),
        ),
        (
            "es-MX",
            (
                "Proveedor: GitHub.",
                "Modo de acceso: Público anónimo.",
                "Credencial del proveedor utilizada: No.",
                "Evidencia fuente requerida completa: Sí.",
                "Paginación completa: No.",
                "Revisión humana: Obligatoria.",
                "Aprobación humana: Pendiente de una acción explícita del revisor.",
                "Entrega al cliente: No autorizada.",
            ),
        ),
    ),
)
def test_frozen_github_access_truth_projects_into_bilingual_report(
    language: str,
    expected_lines: tuple[str, ...],
) -> None:
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime
    from nico.comprehensive_report_package import _stage_summary

    commit_sha = "e" * 40
    snapshot = {
        "provider": "github",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": commit_sha,
        "snapshot_id": "snapshot-github",
    }
    repository_evidence = {
        "repository_provider": "github",
        "repository_provider_instance": "github.com",
        "provider_access_observed": True,
        "provider_access_binding_consistent": True,
        "provider_access_mode": "anonymous_public",
        "provider_credential_used": False,
        "required_source_evidence_complete": True,
        "provider_pagination_complete": False,
        "provider_rate_limit_state": {"limited": False, "reason": ""},
        "provider_collection_limitations": [
            "Complete pagination proof was not retained."
        ],
        "provider_source_fingerprint": "sha256:" + "a" * 64,
        "exact_source_locators": [
            (
                "https://github.com/BoneManTGRM/NICO/blob/"
                f"{commit_sha}/nico/main.py"
            )
        ],
        "exact_source_locator_count": 1,
        "assessment_snapshot_id": "snapshot-github",
        "snapshot_id": "snapshot-github",
        "repository": "BoneManTGRM/NICO",
        "snapshot_commit_sha": commit_sha,
        "provider_capability_states": [
            {"capability": "tree", "state": "supported", "reason": ""},
            {
                "capability": "ci_runs",
                "state": "supported_empty",
                "reason": "",
            },
            {
                "capability": "source_links",
                "state": "supported",
                "reason": "",
            },
        ],
    }

    projected = runtime._github_access_report_snapshot(
        snapshot,
        repository_evidence,
    )
    assert projected is not None
    lines = runtime._provider_access_report_evidence(
        {"report_language": language},
        projected,
        repository_evidence,
    )
    summary = _stage_summary(
        "repository_and_delivery_evidence",
        {"status": "complete", "provider_access_evidence": lines},
    )

    for expected in expected_lines:
        assert expected in summary["evidence"]
    assert any(
        "snapshot-github" in line
        for line in summary["evidence"]
    )
    assert any(
        ("Capability Source tree:" in line)
        or ("Capacidad Árbol de fuentes:" in line)
        for line in summary["evidence"]
    )


@pytest.mark.parametrize(
    "missing_field",
    (
        "provider_access_observed",
        "provider_access_binding_consistent",
        "provider_access_mode",
        "provider_credential_used",
        "required_source_evidence_complete",
        "provider_pagination_complete",
        "provider_source_fingerprint",
        "exact_source_locators",
        "exact_source_locator_count",
        "assessment_snapshot_id",
        "provider_capability_states",
    ),
)
def test_github_report_projection_rejects_missing_or_legacy_access_truth(
    missing_field: str,
) -> None:
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime

    commit_sha = "e" * 40
    snapshot = {
        "provider": "github",
        "repository": "BoneManTGRM/NICO",
        "commit_sha": commit_sha,
        "snapshot_id": "snapshot-github",
    }
    repository_evidence = {
        "repository_provider": "github",
        "repository_provider_instance": "github.com",
        "provider_access_observed": True,
        "provider_access_binding_consistent": True,
        "provider_access_mode": "anonymous_public",
        "provider_credential_used": False,
        "required_source_evidence_complete": True,
        "provider_pagination_complete": False,
        "provider_rate_limit_state": {"limited": False},
        "provider_collection_limitations": [],
        "provider_source_fingerprint": "sha256:" + "a" * 64,
        "exact_source_locators": [
            (
                "https://github.com/BoneManTGRM/NICO/blob/"
                f"{commit_sha}/nico/main.py"
            )
        ],
        "exact_source_locator_count": 1,
        "assessment_snapshot_id": "snapshot-github",
        "repository": "BoneManTGRM/NICO",
        "snapshot_commit_sha": commit_sha,
        "provider_capability_states": [
            {"capability": "tree", "state": "supported", "reason": ""}
        ],
    }
    repository_evidence.pop(missing_field)

    assert runtime._github_access_report_snapshot(
        snapshot,
        repository_evidence,
    ) is None


def test_provider_access_truth_localizes_from_one_frozen_english_snapshot() -> None:
    from nico import hosted_provider_comprehensive_runtime_v1 as runtime
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree

    english = runtime._provider_access_report_evidence(
        {"report_language": "en"},
        {
            "provider": "gitlab",
            "repository": "gitlab.com/group/repo",
            "commit_sha": "e" * 40,
            "access_mode": "anonymous_public",
            "credential_used": False,
            "required_source_evidence_complete": True,
            "pagination_complete": True,
            "provider_rate_limit_state": {},
            "provider_collection_limitations": [],
            "provider_source_fingerprint": "sha256:" + "a" * 64,
            "snapshot_id": "snapshot-provider",
            "provider_capability_states": [
                {"capability": "tree", "state": "supported", "reason": ""},
                {
                    "capability": "ci_runs",
                    "state": "unavailable_authentication",
                    "reason": "provider authentication required",
                },
            ],
        },
        {"exact_source_locator_count": 1},
    )

    localized = _localize_tree({"evidence": english})["evidence"]

    assert "Proveedor: GitLab." in localized
    assert "Modo de acceso: Público anónimo." in localized
    assert "Capacidad Árbol de fuentes: Recopilado." in localized
    assert "gitlab.com/group/repo" in "\n".join(localized)
    assert "e" * 40 in "\n".join(localized)


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
    assert 'normalized in {".", ".."}' in runtime
    assert 'part in {"", ".", ".."}' in safety
    assert "verify=False" not in runtime
    assert "shell=True" not in runtime
