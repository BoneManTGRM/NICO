from __future__ import annotations

import pytest
from scripts.production_proof_repository_scope_v1 import proof_repository_scope


@pytest.mark.parametrize("repository, identity, provider", [
    ("https://gitlab.com/gitlab-org/gitlab-test", "gitlab.com/gitlab-org/gitlab-test", "GitLab"),
    ("gitlab.com/group/subgroup/repo", "gitlab.com/group/subgroup/repo", "GitLab"),
    ("BoneManTGRM/NICO", "github.com/BoneManTGRM/NICO", "GitHub"),
    ("https://github.com/bitcoin/bitcoin.git", "github.com/bitcoin/bitcoin", "GitHub"),
])
def test_scope_matches_selected_repository(repository, identity, provider):
    result = proof_repository_scope(repository)
    assert result["repository_identity"] == identity
    assert result["authorized_scope"].startswith(identity + " —")
    assert result["access_method"] == f"Public {provider} repository via HTTPS/API — read-only access"
    assert "current main branch" not in result["authorized_scope"]


@pytest.mark.parametrize("repository", ["", "https://other.example/a/b", "https://user:pass@gitlab.com/a/b", "https://gitlab.com/a/b?token=secret"])
def test_scope_rejects_missing_or_ambiguous_identity(repository):
    with pytest.raises(ValueError):
        proof_repository_scope(repository)


def test_production_and_recovery_entrypoints_bind_scope_before_use():
    from pathlib import Path
    source = Path("scripts/spanish_comprehensive_live_acceptance_v3.py").read_text()
    recovery = Path("scripts/spanish_comprehensive_existing_run_recovery_v1.py").read_text()
    live = source.split("def _commercial_spanish_run_proof(", 1)[1]
    assert live.index("_configure_proof_repository(args.repository)") < live.index("browser.new_context(")
    resume = recovery.split("def run_recovery(", 1)[1]
    assert resume.index("spanish._configure_proof_repository(args.repository)") < resume.index("_load_failed_source(")


def _scope_fixture():
    from scripts.production_proof_repository_scope_v1 import validate_report_repository_scope
    scope = proof_repository_scope("https://gitlab.com/gitlab-org/gitlab-test")
    metadata = {k: scope[k] for k in ("access_method", "authorized_scope")}
    canonical = {"identity": {"repository": scope["repository_identity"], "commit_sha": "a" * 40, **metadata},
                 "engagement_metadata": dict(metadata)}
    acceptance = {"repository": "https://gitlab.com/gitlab-org/gitlab-test", "assessed_commit_sha": "a" * 40}
    audit = {"repository": scope["repository_identity"]}
    text = "\n".join(metadata.values())
    return validate_report_repository_scope, canonical, acceptance, audit, text


def test_completion_scope_accepts_matching_gitlab_evidence():
    validate, canonical, acceptance, audit, text = _scope_fixture()
    assert validate(canonical, acceptance, audit, text) == "gitlab.com/gitlab-org/gitlab-test"


@pytest.mark.parametrize("field,value", [
    ("authorized_scope", "BoneManTGRM/NICO — entire repository, current main branch"),
    ("access_method", "Public GitHub repository via HTTPS/API — read-only access"),
])
@pytest.mark.parametrize("section", ["identity", "engagement_metadata"])
def test_completion_scope_rejects_old_cross_repository_metadata(field, value, section):
    validate, canonical, acceptance, audit, text = _scope_fixture()
    canonical[section][field] = value
    with pytest.raises(ValueError, match="mismatch"):
        validate(canonical, acceptance, audit, text)


def test_completion_scope_rejects_pdf_with_stale_authorization():
    validate, canonical, acceptance, audit, _ = _scope_fixture()
    with pytest.raises(ValueError, match="PDF authorization metadata mismatch"):
        validate(canonical, acceptance, audit, "BoneManTGRM/NICO — entire repository")


def test_live_proof_metadata_tracks_target_changes(monkeypatch):
    import importlib
    import sys
    from pathlib import Path
    monkeypatch.syspath_prepend(str(Path("scripts").resolve()))
    proof = importlib.import_module("spanish_comprehensive_live_acceptance_v3")
    for name in ("PROOF_ACCESS_METHOD", "PROOF_AUTHORIZED_SCOPE", "PROOF_REPOSITORY_IDENTITY"):
        monkeypatch.setattr(proof, name, getattr(proof, name))
    monkeypatch.setenv(proof.ENGAGEMENT_PROOF_FIXTURE_ENV, "supplied")
    for repository in ("BoneManTGRM/NICO", "https://gitlab.com/gitlab-org/gitlab-test"):
        proof._configure_proof_repository(repository)
        expected = proof_repository_scope(repository)
        metadata = proof._expected_engagement_metadata()
        assert metadata["access_method"] == expected["access_method"]
        assert metadata["authorized_scope"] == expected["authorized_scope"]
    assert "BoneManTGRM/NICO" not in metadata["authorized_scope"]
    assert "GitHub" not in metadata["access_method"]
