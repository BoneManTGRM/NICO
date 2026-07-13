from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import nico.cli as legacy
from nico.local_reporting_service import analyze_memory, generate_reports, report_text
from nico.local_store import LocalStore


ROOT = Path(__file__).resolve().parents[1]
CLI_ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"
LOCAL_SCAN_SERVICE = ROOT / "nico" / "local_scan_service.py"
EXPECTED_FORMATS = [
    "json",
    "markdown",
    "html",
    "owner",
    "developer",
    "reparodynamic",
    "compliance",
]


def _fixture_data() -> dict[str, object]:
    findings = [
        {
            "id": "finding_1",
            "severity": "high",
            "category": "unsafe_eval",
            "title": "Unsafe eval usage",
            "affected_file": "app.py",
            "affected_line": 12,
            "masked_evidence": "eval(***hidden***)",
            "recommended_fix": "Replace eval with a safe parser.",
            "verification_method": "pytest tests/test_app.py",
            "standards_mapping": ["CWE-95"],
        },
        {
            "id": "finding_2",
            "severity": "medium",
            "category": "unsafe_eval",
            "title": "Second unsafe parser path",
            "affected_file": "worker.py",
            "affected_line": 7,
            "masked_evidence": "eval(***masked***)",
            "recommended_fix": "Use an explicit allowlist.",
            "verification_method": "pytest tests/test_worker.py",
            "standards_mapping": ["CWE-95", "OWASP-A03"],
        },
    ]
    return {
        "scan": {
            "id": "scan_exact_1",
            "target": "authorized/repository",
            "created_at": "2026-07-13T00:00:00+00:00",
            "files_scanned": ["app.py", "worker.py"],
            "findings": findings,
            "scanner_availability": [],
        },
        "drift": [
            {
                "id": "drift_exact_1",
                "type": "risk_score_drift",
                "description": "Current scan risk exceeds the stored secure baseline.",
            }
        ],
        "repairs": [
            {
                "id": "repair_exact_1",
                "repair_id": "repair_exact_1",
                "finding_id": "finding_1",
                "repair_type": "minimal",
                "rye_score": 81.5,
                "exact_issue": "Unsafe eval usage",
                "status": "suggested",
            },
            {
                "id": "repair_exact_2",
                "repair_id": "repair_exact_2",
                "finding_id": "finding_2",
                "repair_type": "moderate",
                "rye_score": 62.0,
                "exact_issue": "Second unsafe parser path",
                "status": "suggested",
            },
        ],
        "memory": [
            {
                "id": "memory_exact_1",
                "type": "verification",
                "created_at": "2026-07-13T00:01:00+00:00",
                "category": "unsafe_eval",
                "result": {"status": "verification_observed"},
            }
        ],
        "verification": {
            "id": "verify_exact_1",
            "created_at": "2026-07-13T00:02:00+00:00",
            "repair_id": "repair_exact_1",
            "passed": False,
            "status": "verification_pending",
        },
        "policy": {
            "autonomy_level": 1,
            "kill_switch": False,
            "allowed_actions": ["scan", "report", "score", "repair_plan", "verify", "memory_update"],
            "approval_required": ["production_deploy"],
            "blocked_actions": ["exploit", "unauthorized_scan", "destructive_action"],
        },
    }


def _seed(store: LocalStore) -> None:
    fixture = deepcopy(_fixture_data())
    scan = fixture["scan"]
    assert isinstance(scan, dict)
    store.save_scan(scan, "local")
    drift = fixture["drift"]
    repairs = fixture["repairs"]
    memory = fixture["memory"]
    verification = fixture["verification"]
    policy = fixture["policy"]
    assert isinstance(drift, list)
    assert isinstance(repairs, list)
    assert isinstance(memory, list)
    assert isinstance(verification, dict)
    assert isinstance(policy, dict)
    store.save_drift(str(scan["id"]), drift)
    store.save_repairs(repairs)
    for item in memory:
        assert isinstance(item, dict)
        store.save_memory(item)
    store.save_verification(verification)
    store.save_policy(policy)


def _paths_by_format(paths: list[dict[str, str]]) -> dict[str, Path]:
    return {item["format"]: Path(item["path"]) for item in paths}


def _normalized_report_rows(store: LocalStore) -> list[tuple[str, str, str]]:
    return sorted(
        (str(row["id"]), str(row["format"]), Path(str(row["path"])).name)
        for row in store.rows("reports")
    )


def test_extracted_reports_are_byte_for_byte_legacy_compatible(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_store = LocalStore(tmp_path / "legacy" / "nico.sqlite3")
    extracted_store = LocalStore(tmp_path / "extracted" / "nico.sqlite3")
    _seed(legacy_store)
    _seed(extracted_store)
    legacy_dir = tmp_path / "legacy-reports"
    extracted_dir = tmp_path / "extracted-reports"
    assert not extracted_dir.exists()

    monkeypatch.setattr(legacy, "Store", lambda: legacy_store)
    monkeypatch.setattr(legacy, "REPORT_DIR", legacy_dir)
    legacy_paths = legacy.generate_reports()
    extracted_paths = generate_reports(store=extracted_store, report_dir=extracted_dir)

    assert [item["format"] for item in legacy_paths] == EXPECTED_FORMATS
    assert [item["format"] for item in extracted_paths] == EXPECTED_FORMATS
    legacy_outputs = _paths_by_format(legacy_paths)
    extracted_outputs = _paths_by_format(extracted_paths)
    assert set(legacy_outputs) == set(extracted_outputs)
    for fmt in EXPECTED_FORMATS:
        assert legacy_outputs[fmt].name == extracted_outputs[fmt].name
        assert legacy_outputs[fmt].read_bytes() == extracted_outputs[fmt].read_bytes()

    assert extracted_dir.exists()
    assert _normalized_report_rows(legacy_store) == _normalized_report_rows(extracted_store)
    assert _normalized_report_rows(extracted_store) == sorted(
        (f"latest-{fmt}", fmt, _paths_by_format(extracted_paths)[fmt].name)
        for fmt in EXPECTED_FORMATS
    )


def test_reporting_audit_is_bounded_to_generated_report_metadata(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    _seed(store)
    paths = generate_reports(store=store, report_dir=tmp_path / "reports")

    row = store.rows("audit_log")[0]
    assert row["action"] == "reports.generate"
    detail = json.loads(row["detail"])
    assert [item["format"] for item in detail["reports"]] == EXPECTED_FORMATS
    assert all(Path(item["path"]).parent == tmp_path / "reports" for item in detail["reports"])
    assert [item["format"] for item in paths] == EXPECTED_FORMATS


def test_specialized_report_text_preserves_truthful_compliance_wording(tmp_path: Path) -> None:
    store = LocalStore(tmp_path / "nico.sqlite3")
    _seed(store)

    text = report_text("compliance", store=store, report_dir=tmp_path / "reports")

    assert text.startswith("# NICO Compliance Report")
    assert "Local mapping only. This is not a certification report." in text
    assert "CWE-95: Unsafe eval usage" in text


def test_memory_analysis_matches_legacy_contract() -> None:
    fixture = _fixture_data()
    memory = fixture["memory"]
    scan = fixture["scan"]
    assert isinstance(memory, list)
    assert isinstance(scan, dict)
    findings = scan["findings"]
    assert isinstance(findings, list)

    assert analyze_memory(memory, findings) == legacy.analyze_memory(memory, findings)
    result = analyze_memory(memory, findings)
    assert result["recurring_categories"] == ["unsafe_eval"]
    assert result["fragile_modules"] == ["app.py", "worker.py"]


def test_canonical_reporting_no_longer_sources_functions_from_cli_monolith() -> None:
    entrypoint_source = CLI_ENTRYPOINT.read_text(encoding="utf-8")
    scan_source = LOCAL_SCAN_SERVICE.read_text(encoding="utf-8")

    assert "from nico.local_reporting_service import generate_reports, report_text" in entrypoint_source
    assert "from nico.local_reporting_service import generate_reports" in scan_source
    entrypoint_cli_block = entrypoint_source.split("from nico.cli import (", 1)[1].split(")", 1)[0]
    scan_cli_import = next(line for line in scan_source.splitlines() if line.startswith("from nico.cli import"))
    assert "generate_reports" not in entrypoint_cli_block
    assert "report_text" not in entrypoint_cli_block
    assert "generate_reports" not in scan_cli_import
