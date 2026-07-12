from __future__ import annotations

import json
import time

import nico.dependency_scanner_triage as triage


def _osv_payload(version: str = "3.9.1") -> dict:
    return {
        "results": [
            {
                "source": {"path": "/workspace/requirements.txt", "type": "lockfile"},
                "packages": [
                    {
                        "package": {"name": "filelock", "version": version, "ecosystem": "PyPI"},
                        "groups": [
                            {
                                "ids": ["GHSA-example", "PYSEC-example"],
                                "aliases": ["CVE-example", "GHSA-example", "PYSEC-example"],
                                "max_severity": "8.1",
                            }
                        ],
                        "vulnerabilities": [
                            {
                                "id": "GHSA-example",
                                "aliases": ["CVE-example", "PYSEC-example"],
                                "affected": [
                                    {
                                        "ranges": [
                                            {"events": [{"introduced": "0"}, {"fixed": "3.20.3"}]}
                                        ]
                                    }
                                ],
                            },
                            {"id": "PYSEC-example", "aliases": ["CVE-example", "GHSA-example"]},
                        ],
                    }
                ],
            }
        ]
    }


def test_osv_groups_aliases_into_one_review_record() -> None:
    records = triage.parse_osv(_osv_payload())

    assert len(records) == 1
    assert records[0]["package"] == "filelock"
    assert records[0]["installed_version"] == "3.9.1"
    assert records[0]["fixed_versions"] == ["3.20.3"]
    assert records[0]["material"] is False
    assert records[0]["review_required"] is True
    assert set(records[0]["advisory_ids"]) == {"CVE-example", "GHSA-example", "PYSEC-example"}


def test_pip_audit_parser_retains_resolved_versions_and_vulnerabilities() -> None:
    parsed = triage.parse_pip_audit(
        {
            "dependencies": [
                {"name": "filelock", "version": "3.29.7", "vulns": []},
                {
                    "name": "demo",
                    "version": "1.0",
                    "vulns": [{"id": "GHSA-demo", "aliases": ["CVE-demo"], "fix_versions": ["1.1"]}],
                },
            ]
        }
    )

    assert parsed["resolved_versions"] == {"demo": "1.0", "filelock": "3.29.7"}
    assert len(parsed["vulnerabilities"]) == 1
    assert parsed["vulnerabilities"][0]["material"] is True


def test_old_osv_source_resolution_is_not_material_when_pip_audit_resolves_clean_newer_version() -> None:
    osv_record = triage.parse_osv(_osv_payload())[0]
    scanner = {
        "scanner_results": [
            {
                "scanner": "osv-scanner",
                "execution_completed": True,
                "dependency_records": [osv_record],
            },
            {
                "scanner": "pip-audit",
                "execution_completed": True,
                "resolved_versions": {"filelock": "3.29.7"},
                "dependency_records": [],
            },
            {"scanner": "npm-audit", "execution_completed": True, "dependency_records": []},
        ]
    }

    result = triage.corroborate_dependency_records(scanner)

    assert result["material_records"] == []
    assert len(result["review_records"]) == 1
    assert "3.29.7" in result["review_records"][0]["disposition_reason"]


def test_matching_ecosystem_advisory_is_material() -> None:
    osv_record = triage.parse_osv(_osv_payload("3.9.1"))[0]
    pip_record = {
        **osv_record,
        "fingerprint": "pip-confirmed",
        "installed_version": "3.9.1",
        "material": True,
        "review_required": False,
    }
    scanner = {
        "scanner_results": [
            {"scanner": "osv-scanner", "execution_completed": True, "dependency_records": [osv_record]},
            {
                "scanner": "pip-audit",
                "execution_completed": True,
                "resolved_versions": {"filelock": "3.9.1"},
                "dependency_records": [pip_record],
            },
            {"scanner": "npm-audit", "execution_completed": True, "dependency_records": []},
        ]
    }

    result = triage.corroborate_dependency_records(scanner)

    assert len(result["material_records"]) >= 1
    assert any(item["package"] == "filelock" for item in result["material_records"])


def test_clean_correlated_scanners_can_recover_dependency_score(monkeypatch) -> None:
    monkeypatch.setattr(
        triage,
        "_DEPENDENCY_SECTION_DELEGATE",
        lambda _repo, _scanner: {
            "id": "dependency_health",
            "label": "Dependency / Library Ecosystem",
            "score": 55,
            "status": "yellow",
            "evidence": ["OSV records require review."],
            "verified_claims": ["OSV records require review."],
            "findings": ["Review and remediate 1 OSV vulnerability record(s) before report approval."],
            "unavailable": [],
            "unverified_claims": [],
        },
    )
    osv_record = triage.parse_osv(_osv_payload())[0]
    scanner = {
        "scanner_results": [
            {"scanner": "osv-scanner", "execution_completed": True, "dependency_records": [osv_record]},
            {
                "scanner": "pip-audit",
                "execution_completed": True,
                "resolved_versions": {"filelock": "3.29.7"},
                "dependency_records": [],
            },
            {"scanner": "npm-audit", "execution_completed": True, "dependency_records": []},
        ]
    }

    section = triage.dependency_section_with_corroboration({}, scanner)

    assert section["score"] >= 82
    assert section["status"] == "green"
    assert section["dependency_scanner_triage"]["material_finding_count"] == 0
    assert section["dependency_scanner_triage"]["review_finding_count"] == 1
    assert not any("remediate 1 osv vulnerability" in item.lower() for item in section["findings"])
    assert any("not scored as confirmed installed vulnerabilities" in item for item in section["findings"])


def test_osv_runner_executes_once_and_retains_grouped_records(monkeypatch, tmp_path) -> None:
    calls = []
    payload = _osv_payload()
    monkeypatch.setattr(triage.scanner_worker, "ENABLE_SCANNER_EXECUTION", True)
    monkeypatch.setattr(triage.shutil, "which", lambda _name: "/usr/local/bin/osv-scanner")
    monkeypatch.setattr(triage.runtime_compat, "_osv_commands", lambda _path: [("v2-source", ["osv-scanner", "scan", "source"])])

    def communicate(command, cwd, env, timeout):
        calls.append((command, cwd, timeout))
        return 1, json.dumps(payload), "", 0.2, False

    monkeypatch.setattr(triage.runtime_compat, "_communicate", communicate)
    result = triage._run_osv(
        {"intent": "OSV dependency review"},
        tmp_path,
        {},
        time.monotonic() + 30,
    )

    assert len(calls) == 1
    assert result["execution_completed"] is True
    assert result["material_finding_count"] == 0
    assert result["review_finding_count"] == 1
    assert len(result["dependency_records"]) == 1
