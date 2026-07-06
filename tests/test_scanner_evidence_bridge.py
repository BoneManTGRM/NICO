from nico.reports import build_report_package
from nico.scanner_evidence import enrich_payload_with_scanner_evidence, scanner_section


def test_scanner_results_create_report_section():
    payload = {
        "scanner_results": [
            {"scanner": "pip-audit", "status": "passed", "evidence_summary": "pip-audit completed without known vulnerable packages."},
            {"scanner": "semgrep", "status": "failed", "evidence_summary": "Semgrep returned findings requiring review."},
        ]
    }
    section = scanner_section(payload)
    assert section is not None
    assert section["id"] == "scanner_worker_evidence"
    assert "dependency_intelligence" in section["evidence_sources"]
    assert "static_analysis" in section["evidence_sources"]
    assert section["findings"]


def test_report_package_folds_scanner_results_into_json_and_markdown():
    package = build_report_package({
        "client_name": "Client",
        "project_name": "Project",
        "repository": "owner/repo",
        "sections": [],
        "scanner_results": [
            {"scanner": "bandit", "status": "passed", "evidence_summary": "bandit completed."},
            {"scanner": "osv-scanner", "status": "unavailable", "evidence_summary": "osv-scanner was not installed.", "unavailable_data_notes": ["tool missing"]},
        ],
    })
    sections = package["formats"]["json"]["sections"]
    scanner = next(item for item in sections if item["id"] == "scanner_worker_evidence")
    assert scanner["confidence"] in {"limited", "medium"}
    assert "Scanner Worker Evidence" in package["formats"]["markdown"]
    assert package["formats"]["json"]["evidence_readiness"]["scanner_worker_attached"] is True


def test_enrichment_is_noop_without_scanner_results():
    payload = {"sections": [{"id": "code_audit", "label": "Code Audit", "score": 60, "status": "yellow", "summary": "x", "evidence": ["Repository files inspected."], "findings": [], "unavailable": []}]}
    enriched = enrich_payload_with_scanner_evidence(payload)
    assert enriched == payload
