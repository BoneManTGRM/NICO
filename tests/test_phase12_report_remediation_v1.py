from copy import deepcopy

from nico.phase12_report_remediation_v1 import (
    canonical_fingerprint,
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
    assert set(result[0]["finding_aliases"]) == {"RISK-P1-NEW", "RISK-OLD"}
    assert len(result[0]["supporting_evidence"]) == 2


def test_duplicate_merge_preserves_distinct_evidence_and_mappings():
    left = _finding("RISK-A")
    left.update({"tool": "radon", "rule_id": "CC", "evidence": "complexity=52", "roadmap_ids": ["WP-1"]})
    right = _finding("RISK-P1-B", enriched=True)
    right.update({"tool": "typescript", "rule_id": "CC", "evidence": "complexity=52", "roadmap_ids": ["WP-2"]})
    result = canonical_findings([left, right])[0]
    assert set(result["roadmap_ids"]) == {"WP-1", "WP-2"}
    assert {item.get("tool") for item in result["supporting_evidence"]} == {"radon", "typescript"}
    assert set(result["finding_aliases"]) == {"RISK-A", "RISK-P1-B"}


def test_fingerprint_ignores_legacy_id_and_p_prefixed_id():
    left = _finding("RISK-54DC2C8248A9", location="apps/web/app/operations/page.tsx:177")
    right = _finding("RISK-P1-0A2FA160AB", location="apps/web/app/operations/page.tsx:177")
    assert canonical_fingerprint(left) == canonical_fingerprint(right)


def test_distinct_locations_remain_distinct_findings():
    first = _finding("A", location="src/a.py:10")
    second = _finding("B", location="src/b.py:10")
    result = canonical_findings([first, second])
    assert len(result) == 2
    assert [item["title"] for item in result] == ["Reduce complexity in a.py", "Reduce complexity in b.py"]


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
    assert result["phase13_canonical_findings"]["supporting_evidence_merged"] is True


def test_terminal_filename_state_is_idempotent():
    original = "nico-report-FINAL-PENDING-APPROVAL-FINAL-PENDING-APPROVAL.pdf"
    once = remediate_filename(original, "FINAL-PENDING-APPROVAL")
    twice = remediate_filename(once, "FINAL-PENDING-APPROVAL")
    assert once == twice
    assert once.count("FINAL-PENDING-APPROVAL") == 1
