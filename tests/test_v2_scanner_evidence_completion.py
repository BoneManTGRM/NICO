from __future__ import annotations

import gzip
import hashlib
import json
import os
import subprocess
from pathlib import Path

from nico import v2_scanner_evidence_completion as completion
from nico.v2_scanner_evidence_context_normalization import install_v2_scanner_evidence_context_normalization


ROOT = Path(__file__).resolve().parents[1]
install_v2_scanner_evidence_context_normalization()


def _git(cwd: Path, *arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )


def test_retained_osv_json_preserves_package_version_path_and_fix(monkeypatch, tmp_path):
    raw = {
        "results": [
            {
                "source": {"path": "apps/web/package-lock.json"},
                "packages": [
                    {
                        "package": {
                            "name": "example-package",
                            "version": "1.0.0",
                            "ecosystem": "npm",
                        },
                        "vulnerabilities": [
                            {
                                "id": "GHSA-EXAMPLE",
                                "affected": [
                                    {
                                        "ranges": [
                                            {
                                                "events": [
                                                    {"introduced": "0"},
                                                    {"fixed": "1.2.0"},
                                                ]
                                            }
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        ]
    }
    raw_bytes = json.dumps(raw, sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw_bytes, mtime=0)
    root = tmp_path / "scanner-artifacts"
    artifact = root / "repo" / "sha" / "run" / "osv.json.gz"
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(compressed)
    monkeypatch.setattr(completion, "DEFAULT_RAW_ROOT", root)

    payload = {
        "scanner_name": "osv-scanner",
        "raw_artifact": {
            "storage_key": str(artifact.relative_to(root)),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        },
        "findings": [{"id": "GHSA-EXAMPLE"}],
    }
    completion._enrich_retained_osv(payload)

    assert payload["dependency_context_enrichment"]["status"] == "complete"
    assert payload["dependency_context_enrichment"]["package_context_retained"] is True
    assert payload["dependency_context_enrichment"]["installed_version_retained"] is True
    finding = payload["findings"][0]
    assert finding["id"] == "GHSA-EXAMPLE"
    assert finding["package"] == "example-package"
    assert finding["installed_version"] == "1.0.0"
    assert finding["ecosystem"] == "npm"
    assert finding["dependency_path"] == "apps/web/package-lock.json"
    assert finding["fixed_version"] == "1.2.0"
    assert finding["fixed_versions"] == ["1.2.0"]


def test_full_history_materialization_removes_partial_clone_contract(tmp_path):
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    clone = tmp_path / "clone"
    origin.mkdir()
    _git(origin, "init", "--bare")
    work.mkdir()
    _git(work, "init")
    _git(work, "config", "user.email", "nico-tests@example.invalid")
    _git(work, "config", "user.name", "NICO Tests")
    (work / "evidence.txt").write_text("immutable evidence\n", encoding="utf-8")
    _git(work, "add", "evidence.txt")
    _git(work, "commit", "-m", "Add immutable evidence")
    _git(work, "branch", "-M", "main")
    _git(work, "remote", "add", "origin", str(origin))
    _git(work, "push", "-u", "origin", "main")
    _git(tmp_path, "clone", str(origin), str(clone))
    _git(clone, "checkout", "main")

    _git(clone, "config", "remote.origin.promisor", "true")
    _git(clone, "config", "remote.origin.partialclonefilter", "blob:none")
    _git(clone, "config", "extensions.partialClone", "origin")
    notes, complete = completion._materialize_git_objects(clone, os.environ.copy(), [])

    assert complete is True
    assert any("materialized and verified" in note for note in notes)
    for key in completion._PARTIAL_CLONE_KEYS:
        result = subprocess.run(
            ["git", "config", "--get", key],
            cwd=clone,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0
    missing = subprocess.run(
        ["git", "rev-list", "--objects", "--all", "--missing=print"],
        cwd=clone,
        capture_output=True,
        text=True,
        check=True,
    )
    assert not any(line.startswith("?") for line in missing.stdout.splitlines())
    _git(clone, "fsck", "--full", "--no-dangling")


def test_production_bootstrap_and_workflow_bind_completion_contracts():
    bootstrap = (ROOT / "nico/api/terminal_authority_bootstrap.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/remediation-evidence.yml").read_text(encoding="utf-8")
    source = (ROOT / "nico/v2_scanner_evidence_completion.py").read_text(encoding="utf-8")
    normalization = (ROOT / "nico/v2_scanner_evidence_context_normalization.py").read_text(encoding="utf-8")

    assert "install_v2_scanner_evidence_completion" in bootstrap
    assert "install_v2_scanner_evidence_context_normalization" in bootstrap
    assert "V2_SCANNER_EVIDENCE_COMPLETION" in bootstrap
    assert "V2_SCANNER_CONTEXT_NORMALIZATION" in bootstrap
    assert "trufflehog_internal_clone_supported" in bootstrap
    assert "GITHUB_TOKEN: ${{ github.token }}" in workflow
    assert '"--refetch"' in source
    assert '"remote.origin.promisor"' in source
    assert '"remote.origin.partialclonefilter"' in source
    assert '"rev-list", "--objects", "--all", "--missing=print"' in source
    assert '"fsck", "--full", "--no-dangling"' in source
    assert "_enrich_retained_osv(output)" in source
    assert "normalized_package_context" in normalization
    assert "nested_source_path_normalized" in normalization
