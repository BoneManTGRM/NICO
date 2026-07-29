from copy import deepcopy

from nico.phase12_report_remediation_v1 import (
    canonical_findings,
    canonical_scanner_records,
    remediate_assessment,
    remediate_filename,
)

SHA = "a" * 40


def _finding(fid: str, *, title: str = "High-complexity code hotspot", location: str = "src/page.tsx:10", enriched: bool = False):
    item = {
        "finding_id": fid,
        "priority": "P1",
        "category": "architecture",
        "title": title,
        "decision_title": title,
        "location": location,
        "interpretation": title,
        "business_impact": "Concentrated branch logic increases regression risk.",
        "recommendation": "Decompose the hotspot.",
        "acceptance_criteria": ["Add tests", "  add   tests  "],
    }
    if enriched:
        item.update({"cost_of_inaction": "Material", "residual_risk": "Moderate", "roadmap": ["WP-1"]})
    return item


def test_semantic_duplicate_pair_collapses_to_enriched_record():
    plain = _finding("RISK-OLD")
    enriched = _finding("RISK-P1-NEW", enriched=True)
    result = canonical_findings([plain, enriched])
    assert len(result) == 1
    assert result[0]["finding_id"] == "RISK-P1-NEW"
    assert result[0]["title"] == "Reduce complexity in page.tsx"
    assert result[0]["acceptance_criteria"] == ["Add tests"]


def test_internal_rule_literal_is_not_reported_as_tls_defect():
    tls = _finding("TLS-1", title="TLS certificate verification disabled", location="nico/phase5_report_truth_v1.py:112")
    tls["evidence"] = "risk_pattern_hits=7; exact immutable commit=" + SHA
    assert canonical_findings([tls]) == []


def test_real_tls_call_remains_visible():
    tls = _finding("TLS-2", title="TLS certificate verification disabled", location="src/client.py:12")
    tls["evidence"] = "requests.get(url, verify=False)"
    result = canonical_findings([tls])
    assert len(result) == 1
    assert "src/client.py:12" in result[0]["title"]


def test_location_not_retained_cannot_remain_p1():
    finding = _finding("CI-1", title="Delivery workflow reliability issue", location="location-not-retained")
    result = canonical_findings([finding])[0]
    assert result["priority"] == "P2"
    assert result["status"] == "review_limited"


def test_scanner_reconciliation_prefers_exact_completed_record():
    records = [
        {"scanner": "bandit", "status": "failed", "commit_sha": SHA},
        {"scanner": "bandit", "status": "completed", "commit_sha": SHA, "output_sha256": "b" * 64},
        {"scanner": "bandit", "status": "completed", "commit_sha": "c" * 40},
    ]
    result = canonical_scanner_records(records, commit_sha=SHA)
    assert len(result) == 1
    assert result[0]["status"] == "completed"
    assert result[0]["commit_sha"] == SHA


def test_assessment_surfaces_share_one_population():
    assessment = {
        "findings_register": [_finding("A"), _finding("B", enriched=True)],
        "executive_risk_register": [_finding("A")],
        "evidence_health_summary": {
            "scanner_records": [
                {"scanner": "bandit", "status": "failed", "commit_sha": SHA},
                {"scanner": "bandit", "status": "completed", "commit_sha": SHA, "output_sha256": "d" * 64},
            ]
        },
    }
    result = remediate_assessment(deepcopy(assessment), commit_sha=SHA)
    assert len(result["findings_register"]) == 1
    assert result["canonical_findings"] == result["findings_register"]
    assert result["executive_risk_register"] == result["findings_register"]
    assert result["evidence_health_summary"]["completed_scanners"] == ["bandit"]
    assert result["evidence_health_summary"]["incomplete_scanner_records"] == []


def test_terminal_filename_state_is_idempotent():
    original = "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    once = remediate_filename(original, "FINAL-PENDING-APPROVAL")
    twice = remediate_filename(once, "FINAL-PENDING-APPROVAL")
    assert once == twice
    assert once.count("FINAL-PENDING-APPROVAL") == 1
