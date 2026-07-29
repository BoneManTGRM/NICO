from __future__ import annotations

import base64
from pathlib import Path

from nico.v2_production_authority import wrap_final_report_publication


SHA = "8" * 40
ROOT = Path(__file__).resolve().parents[1]


def _finding(identifier: str, *, enriched: bool) -> dict:
    item = {
        "finding_id": identifier,
        "category": "architecture",
        "title": "High-complexity code hotspot",
        "location": "apps/web/app/operations/page.tsx:177",
        "fact": "cyclomatic_complexity=52; loc=173; method=typescript_compiler_ast",
        "priority": "P1",
        "status": "open",
        "recommendation": "Decompose the hotspot into bounded modules.",
        "acceptance_criteria": ["Target complexity is at most 30."],
    }
    if enriched:
        item.update(
            {
                "business_impact": "Concentrated branch logic increases regression risk.",
                "owner_role": "Product Engineering Architect",
                "effort": "M-L",
                "acceptance_criteria": [
                    f"Target complexity is at most 30. [method: metric_comparison; target commit: {SHA}]",
                    f"Target complexity is at most 30. [method: metric_comparison; target commit: {SHA}]",
                ],
            }
        )
    return item


def _source() -> dict:
    legacy = _finding("RISK-LEGACY-123", enriched=False)
    prioritized = _finding("RISK-P1-CANONICAL", enriched=True)
    duplicated = "FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL"
    return {
        "status": "complete",
        "report_package": {
            "service_id": "comprehensive",
            "json": {
                "service_id": "comprehensive",
                "identity": {
                    "repository": "BoneManTGRM/NICO",
                    "commit_sha": SHA,
                    "run_id": "comprun_v2_live",
                    "evidence_ledger_id": "ledger-v2",
                    "customer_id": "customer-v2",
                    "project_id": "project-v2",
                },
                "assessment": {
                    "technical_score": 81,
                    "canonical_evidence_adjusted_score": 80,
                    "maturity_signal": {"score": 81},
                    "sections": [],
                },
                "canonical_findings": [legacy, prioritized],
                "findings_register": [legacy, prioritized],
            },
            "pdf_filename": f"nico-live-{duplicated}.pdf",
            "spanish_pdf_filename": f"nico-live-es-{duplicated}.pdf",
            "pdf_base64": base64.b64encode(b"%PDF stale legacy artifact").decode("ascii"),
        },
    }


def test_real_final_provider_is_republished_through_one_v2_truth(monkeypatch):
    from nico import comprehensive_native_providers as providers

    monkeypatch.setattr(
        providers,
        "_scan",
        lambda context: {
            "scan_id": "scan-v2",
            "snapshot_commit_sha": SHA,
            "actual_commit_sha": SHA,
            "snapshot_match": True,
            "tools_requested": ["bandit", "eslint"],
            "tools_run": ["bandit", "eslint"],
            "scanner_results": [
                {
                    "tool": "bandit",
                    "status": "completed",
                    "returncode": 1,
                    "findings": [{"test_id": "B101"}],
                    "artifact_hash": "b" * 64,
                    "raw_artifact_retention_complete": True,
                    "verified_for_this_report": True,
                },
                {
                    "tool": "eslint",
                    "status": "completed",
                    "returncode": 1,
                    "findings": [{"ruleId": "complexity"}],
                    "artifact_hash": "e" * 64,
                    "raw_artifact_retention_complete": True,
                    "verified_for_this_report": True,
                },
            ],
        },
    )
    provider = wrap_final_report_publication(lambda context: _source())
    output = provider({"commit_sha": SHA, "prior_stage_results": {}})
    package = output["report_package"]
    canonical = package["json"]

    assert output["status"] == "complete"
    assert output["assessment_state"] == "review_required"
    assert output["v2_production_authority"]["single_final_publication_boundary"] is True
    assert len(canonical["canonical_findings"]) == 1
    finding = canonical["canonical_findings"][0]
    assert finding["finding_id"] == "RISK-P1-CANONICAL"
    assert set(finding["finding_aliases"]) >= {"RISK-LEGACY-123", "RISK-P1-CANONICAL"}
    assert finding["acceptance_criteria"] == ["Target complexity is at most 30."]

    scanners = {item["scanner_name"]: item for item in canonical["scanner_execution_records"]}
    assert scanners["bandit"]["state"] == "completed_with_findings"
    assert scanners["bandit"]["exit_code"] == 1
    assert scanners["eslint"]["state"] == "completed_with_findings"
    assert all(item["verified"] is True for item in scanners.values())

    assert package["pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1
    assert package["spanish_pdf_filename"].count("FINAL-PENDING-APPROVAL") == 1
    assert "PENDING HUMAN APPROVAL" in package["markdown"]
    assert "CLIENT DELIVERY BLOCKED" in package["markdown"]
    assert "RISK-LEGACY-123" not in package["markdown"].split("## Canonical findings", 1)[1].split("Historical aliases:", 1)[0]
    assert base64.b64decode(package["pdf_base64"]).startswith(b"%PDF")
    hashes = {
        package["canonical_truth_sha256"],
        package["json_canonical_sha256"],
        package["markdown_canonical_sha256"],
        package["html_canonical_sha256"],
        package["pdf_canonical_sha256"],
        package["csv_canonical_sha256"],
        package["ui_canonical_sha256"],
    }
    assert len(hashes) == 1


def test_production_bootstraps_bind_real_report_and_scanner_authorities():
    comprehensive = (ROOT / "nico/api/comprehensive_production_bootstrap.py").read_text(encoding="utf-8")
    terminal = (ROOT / "nico/api/terminal_authority_bootstrap.py").read_text(encoding="utf-8")
    scanner = (ROOT / "nico/v2_snapshot_scanner_authority.py").read_text(encoding="utf-8")

    assert "install_v2_production_authority(target)" in comprehensive
    assert comprehensive.index("install_v2_production_authority(target)") < comprehensive.index("build_production_capability_executors(target)")
    assert "install_v2_snapshot_scanner_authority()" in terminal
    assert "scanner_tool_runners.run_scanner_tool = canonical_snapshot_tool_runner" in scanner
    assert "snapshot_scanner_worker.clone_repository_at_snapshot = full_history_snapshot_clone" in scanner
    assert "raw_artifact_retention_complete" in scanner
    assert "exit_code" in scanner and "returncode" in scanner
