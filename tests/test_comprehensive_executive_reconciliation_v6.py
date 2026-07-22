from nico.comprehensive_executive_reconciliation_v6 import reconcile_comprehensive_assessment


def _base_assessment():
    return {
        "maturity_signal": {"score": 69, "presented_score": 69},
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 82,
                "presented_score": 82,
                "score_value": 82,
                "score_band_label": "STRONG",
                "assurance_label": "REVIEW LIMITED",
                "summary": "Code review complete.",
            },
            {
                "id": "static_analysis",
                "label": "Static Analysis",
                "score": 21,
                "presented_score": 21,
                "score_value": 21,
                "score_band_label": "CRITICAL",
                "assurance_label": "BLOCKED",
                "evidence": ["Static candidates: raw=108; material=39; review_required=69."],
                "findings": ["Failed static analyzers: bandit. bandit output was truncated."],
                "unavailable": ["bandit unavailable for accepted scoring evidence."],
                "summary": "Candidate findings retained.",
            },
            {
                "id": "architecture_debt",
                "label": "Architecture & Technical Debt",
                "score": 78,
                "presented_score": 78,
                "score_value": 78,
                "score_band_label": "MODERATE",
                "assurance_label": "REVIEW LIMITED",
                "summary": "Measured complexity retained.",
            },
        ],
        "findings_register": [
            {
                "id": "architecture-hotspot-1",
                "priority": "P1",
                "category": "architecture",
                "title": "Complexity hotspot: <module-logic>",
                "location": "apps/web/app/assessment/MidSectionReview.tsx:1",
                "evidence": "cyclomatic_complexity=148; loc=340",
                "impact": "Complexity risk.",
                "confidence": "moderate",
                "recommendation": "Decompose.",
            },
            {
                "id": "scanner-semgrep-1",
                "priority": "P1",
                "category": "static",
                "title": "github-actions-mutable-action-tag",
                "location": ".github/workflows/nico-ci.yml",
                "evidence": "tool=semgrep; severity=medium; verified=False",
                "impact": "Candidate.",
                "confidence": "moderate",
                "recommendation": "Review.",
            },
            {
                "id": "scanner-operational-1",
                "priority": "P1",
                "category": "evidence",
                "title": "bandit evidence unavailable",
                "location": "Scanner execution boundary",
                "evidence": "Analyzer status=failed; output truncated",
                "impact": "Evidence incomplete.",
                "confidence": "high",
                "recommendation": "Repair scanner.",
            },
        ],
    }


def test_incomplete_static_analysis_is_unscored_not_critical():
    result = reconcile_comprehensive_assessment(_base_assessment())
    static = next(item for item in result["sections"] if item["id"] == "static_analysis")
    assert static["score_value"] is None
    assert static["score_band_label"] == "NOT SCORED"
    assert static["assurance_label"] == "BLOCKED"
    assert static["exclude_from_maturity"] is True


def test_unverified_medium_candidate_is_not_p1():
    result = reconcile_comprehensive_assessment(_base_assessment())
    finding = next(item for item in result["findings_register"] if item["id"] == "scanner-semgrep-1")
    assert finding["priority"] == "P2"
    assert finding["confidence"] == "candidate"


def test_internal_module_logic_label_is_replaced():
    result = reconcile_comprehensive_assessment(_base_assessment())
    finding = next(item for item in result["findings_register"] if item["id"] == "architecture-hotspot-1")
    assert "<module-logic>" not in finding["title"]
    assert "MidSectionReview" in finding["title"]


def test_executive_register_is_consolidated_and_bounded():
    result = reconcile_comprehensive_assessment(_base_assessment())
    risks = result["executive_risk_register"]
    assert 1 <= len(risks) <= 8
    assert len({item["id"] for item in risks}) == len(risks)


def test_weighted_maturity_excludes_unscored_static_control():
    result = reconcile_comprehensive_assessment(_base_assessment())
    static_row = next(item for item in result["scoring_weight_table"] if item["control_id"] == "static_analysis")
    assert static_row["included"] is False
    assert static_row["weighted_contribution"] is None
    assert result["maturity_signal"]["presented_score"] != 69
