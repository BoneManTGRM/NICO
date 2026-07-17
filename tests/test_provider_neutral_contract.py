from nico.provider_neutral_contract import (
    Capability,
    CanonicalCIRun,
    PROVIDER_MINIMUM_CAPABILITIES,
    ProviderAccess,
    ProviderEvidenceEnvelope,
    ProviderIdentity,
    ProviderKind,
    SnapshotIdentity,
    normalize_provider,
    validate_provider_envelope,
)


def test_major_provider_aliases_normalize() -> None:
    assert normalize_provider("github-enterprise") is ProviderKind.GITHUB
    assert normalize_provider("gitlab self managed") is ProviderKind.GITLAB
    assert normalize_provider("bitbucket data center") is ProviderKind.BITBUCKET
    assert normalize_provider("azure repos") is ProviderKind.AZURE_DEVOPS
    assert normalize_provider("uploaded archive") is ProviderKind.ARCHIVE
    assert normalize_provider("ssh") is ProviderKind.GENERIC_GIT


def test_major_platforms_define_minimum_capabilities() -> None:
    for provider in (
        ProviderKind.GITHUB,
        ProviderKind.GITLAB,
        ProviderKind.BITBUCKET,
        ProviderKind.AZURE_DEVOPS,
        ProviderKind.GENERIC_GIT,
        ProviderKind.ARCHIVE,
    ):
        assert Capability.REPOSITORY in PROVIDER_MINIMUM_CAPABILITIES[provider]


def test_valid_provider_envelope_preserves_exact_snapshot_truth() -> None:
    identity = ProviderIdentity(
        provider=ProviderKind.GITLAB,
        instance_url="https://gitlab.example.com",
        namespace="security",
        repository="service",
        repository_id="project-17",
        default_branch="main",
    )
    access = ProviderAccess(
        read_only=True,
        scopes=("read_api", "read_repository"),
        capabilities=(Capability.REPOSITORY, Capability.COMMITS, Capability.CI_RUNS),
    )
    snapshot = SnapshotIdentity(
        provider=ProviderKind.GITLAB,
        repository_id="project-17",
        revision="abc123",
        collected_at="2026-07-17T12:00:00Z",
        source_fingerprint="sha256:example",
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=access,
        snapshot=snapshot,
        ci_runs=(
            CanonicalCIRun(
                provider=ProviderKind.GITLAB,
                native_id="pipeline-9",
                name="test",
                revision="abc123",
                branch="main",
                status="completed",
                conclusion="success",
                started_at="2026-07-17T12:01:00Z",
            ),
        ),
    )
    assert validate_provider_envelope(envelope) == []


def test_provider_contract_fails_closed_for_write_access_and_mismatch() -> None:
    identity = ProviderIdentity(
        provider=ProviderKind.BITBUCKET,
        instance_url="https://bitbucket.org",
        namespace="workspace",
        repository="repo",
        repository_id="repo-1",
        default_branch="main",
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=ProviderAccess(
            read_only=False,
            scopes=("repository:write",),
            capabilities=(Capability.REPOSITORY,),
            partial_access=True,
        ),
        snapshot=SnapshotIdentity(
            provider=ProviderKind.GITHUB,
            repository_id="other",
            revision="def456",
            collected_at="2026-07-17T12:00:00Z",
            source_fingerprint="sha256:other",
        ),
    )
    issues = validate_provider_envelope(envelope)
    assert "provider_access_must_be_read_only" in issues
    assert "provider_snapshot_identity_mismatch" in issues
    assert "provider_snapshot_repository_mismatch" in issues
    assert "provider_partial_access_limitation_required" in issues


def test_ci_revision_outside_snapshot_is_rejected() -> None:
    identity = ProviderIdentity(
        provider=ProviderKind.AZURE_DEVOPS,
        instance_url="https://dev.azure.com/example",
        namespace="project",
        repository="repo",
        repository_id="repo-2",
        default_branch="main",
    )
    envelope = ProviderEvidenceEnvelope(
        identity=identity,
        access=ProviderAccess(
            read_only=True,
            scopes=("vso.code", "vso.build"),
            capabilities=(Capability.REPOSITORY, Capability.CI_RUNS),
        ),
        snapshot=SnapshotIdentity(
            provider=ProviderKind.AZURE_DEVOPS,
            repository_id="repo-2",
            revision="expected",
            collected_at="2026-07-17T12:00:00Z",
            source_fingerprint="sha256:expected",
        ),
        ci_runs=(
            CanonicalCIRun(
                provider=ProviderKind.AZURE_DEVOPS,
                native_id="build-4",
                name="build",
                revision="different",
                branch="main",
                status="completed",
                conclusion="success",
                started_at="2026-07-17T12:01:00Z",
            ),
        ),
    )
    assert "ci_revision_outside_snapshot:build-4" in validate_provider_envelope(envelope)
