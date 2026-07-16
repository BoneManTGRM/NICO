from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
README = ROOT / "README.md"
DOCS_MAP = ROOT / "docs" / "README.md"
SELF_HOSTING = ROOT / "docs" / "SELF_HOSTING.md"
SCANNERS = ROOT / "docs" / "SCANNERS.md"
SAMPLES = ROOT / "docs" / "SAMPLES.md"
COMPOSE = ROOT / "docker-compose.yml"
INSTALLER = ROOT / "scripts" / "install_hosted_scanner_binaries.py"


def test_compose_uses_fail_closed_production_bootstrap_and_verified_named_volume() -> None:
    source = COMPOSE.read_text(encoding="utf-8")

    assert "nico.api.production_bootstrap:app" in source
    assert "nico.api.production:app" not in source
    assert "NICO_SQLITE_PATH: /data/nico-runtime.sqlite3" in source
    assert 'NICO_SQLITE_DURABLE_MOUNT_VERIFIED: "true"' in source
    assert 'NICO_REQUIRE_DURABLE_ASSESSMENT_STORAGE: "true"' in source
    assert 'NICO_REQUIRE_DURABLE_DELIVERY_STORAGE: "true"' in source
    assert 'NICO_WEB_WORKERS: "1"' in source
    assert "nico-data:/data" in source
    assert "NICO_DB_PATH" not in source


def test_hosted_binary_scanners_use_explicit_release_tags_not_latest_resolution() -> None:
    source = INSTALLER.read_text(encoding="utf-8")

    assert '"default_tag": "v2.4.0"' in source
    assert '"default_tag": "v8.30.1"' in source
    assert '"default_tag": "v3.95.9"' in source
    assert '"NICO_OSV_SCANNER_VERSION"' in source
    assert '"NICO_GITLEAKS_VERSION"' in source
    assert '"NICO_TRUFFLEHOG_VERSION"' in source
    assert "/releases/tags/{tag}" in source
    assert "/releases/latest" not in source
    assert "Scanner release tag mismatch" in source


def test_readme_states_current_provider_and_package_scope_truthfully() -> None:
    source = README.read_text(encoding="utf-8")

    assert "## Repository-provider scope" in source
    assert "current hosted remote-repository integration is **GitHub-native**" in source
    assert "does not currently claim native GitLab" in source
    assert "Provider expansion remains deferred" in source
    assert "## Package installation and quick start" in source
    assert 'python -m pip install -e ".[dev,scanners]"' in source
    assert "publication to a public package index is a separate release" in source
    assert "docs/SELF_HOSTING.md" in source
    assert "docs/SCANNERS.md" in source
    assert "docs/SAMPLES.md" in source


def test_canonical_documentation_map_links_new_operating_guides() -> None:
    docs = DOCS_MAP.read_text(encoding="utf-8")

    assert SELF_HOSTING.is_file()
    assert SCANNERS.is_file()
    assert SAMPLES.is_file()
    assert "[`SELF_HOSTING.md`](SELF_HOSTING.md)" in docs
    assert "[`SCANNERS.md`](SCANNERS.md)" in docs
    assert "[`SAMPLES.md`](SAMPLES.md)" in docs


def test_samples_remain_explicitly_non_live_and_review_bound() -> None:
    source = SAMPLES.read_text(encoding="utf-8")

    assert "Synthetic fixtures" in source
    assert "not a permanent public client sample" in source
    assert "human_review_required: true" in source
    assert "client_ready: false" in source
    assert "do not prove" in source.lower()
