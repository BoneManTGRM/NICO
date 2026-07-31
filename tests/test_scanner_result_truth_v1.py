from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from nico.scanner_result_truth_v1 import reconcile_scanner_payload
from nico.worker_execution import WorkerWorkspace


def _blob(payload: object) -> dict:
    raw = json.dumps(payload, sort_keys=True).encode("utf-8")
    compressed = gzip.compress(raw, mtime=0)
    return {
        "gzip_hex": compressed.hex(),
        "gzip_sha256": hashlib.sha256(compressed).hexdigest(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "filename": "scanner.json.gz",
        "raw_format": "json",
        "retained_bytes": len(raw),
        "gzip_bytes": len(compressed),
    }


def _workspace(tmp_path: Path) -> WorkerWorkspace:
    repo = tmp_path / "repo"
    repo.mkdir()
    return WorkerWorkspace(root=tmp_path)


def test_osv_projection_keeps_only_authoritative_manifest_context(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace.repo_dir / "requirements.txt").write_text("requests==2.34.2\n", encoding="utf-8")
    fixture_dir = workspace.repo_dir / "audit-results"
    fixture_dir.mkdir()
    (fixture_dir / "requirements.txt").write_text("Pillow==1.0\n", encoding="utf-8")
    payload = {
        "results": [
            {
                "source": {"path": str(workspace.repo_dir / "requirements.txt"), "type": "lockfile"},
                "packages": [
                    {
                        "package": {"name": "requests", "version": "2.34.2", "ecosystem": "PyPI"},
                        "vulnerabilities": [
                            {
                                "id": "GHSA-TEST-0001",
                                "affected": [
                                    {
                                        "ranges": [
                                            {"events": [{"introduced": "0"}, {"fixed": "2.34.3"}]}
                                        ]
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            {
                "source": {"path": "audit-results/requirements.txt", "type": "lockfile"},
                "packages": [
                    {
                        "package": {"name": "Pillow", "version": "1.0", "ecosystem": "PyPI"},
                        "vulnerabilities": [{"id": "GHSA-STALE-FIXTURE"}],
                    }
                ],
            },
        ]
    }
    result = reconcile_scanner_payload(
        "osv-scanner",
        {"tool": "osv-scanner", "status": "completed", "findings": [{"id": "stale"}]},
        _blob(payload),
        workspace,
    )

    assert result["findings_count"] == 1
    finding = result["findings"][0]
    assert finding["advisory_id"] == "GHSA-TEST-0001"
    assert finding["package"] == "requests"
    assert finding["installed_version"] == "2.34.2"
    assert finding["dependency_path"] == "requirements.txt"
    assert finding["fixed_versions"] == ["2.34.3"]
    assert finding["scanner_context_complete"] is True
    assert result["ignored_non_authoritative_candidate_count"] == 1
    assert result["authoritative_manifest_paths"] == ["requirements.txt"]


def test_unverified_example_secret_placeholder_is_retained_as_nonblocking(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace.repo_dir / ".env.example").write_text(
        "DATABASE_URL=postgresql://user:password@host:5432/nico\n",
        encoding="utf-8",
    )
    candidate = {"File": ".env.example", "StartLine": 1, "DetectorName": "Postgres", "Verified": False}
    result = reconcile_scanner_payload(
        "trufflehog",
        {"tool": "trufflehog", "status": "completed", "findings": [candidate]},
        None,
        workspace,
    )

    assert result["findings"] == []
    assert result["findings_count"] == 0
    assert result["verified_example_placeholder_count"] == 1
    retained = result["nonblocking_findings"][0]
    assert retained["path"] == ".env.example"
    assert retained["disposition"] == "verified_example_placeholder"
    assert retained["technical_score_impact"] == "none"
    assert result["secret_candidate_disposition"]["raw_artifact_preserved"] is True


def test_verified_or_non_example_secret_is_never_suppressed(tmp_path: Path) -> None:
    workspace = _workspace(tmp_path)
    (workspace.repo_dir / ".env.example").write_text(
        "DATABASE_URL=postgresql://user:password@host:5432/nico\n",
        encoding="utf-8",
    )
    (workspace.repo_dir / "settings.py").write_text("TOKEN='real-looking-value'\n", encoding="utf-8")
    candidates = [
        {"File": ".env.example", "StartLine": 1, "DetectorName": "Postgres", "Verified": True},
        {"File": "settings.py", "StartLine": 1, "DetectorName": "Generic", "Verified": False},
    ]
    result = reconcile_scanner_payload(
        "trufflehog",
        {"tool": "trufflehog", "status": "completed", "findings": candidates},
        None,
        workspace,
    )

    assert result["findings_count"] == 2
    assert result["verified_example_placeholder_count"] == 0
