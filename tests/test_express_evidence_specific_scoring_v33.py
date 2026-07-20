from __future__ import annotations

from nico.express_evidence_specific_scoring_v33 import (
    VERSION,
    evidence_score_record,
    reconcile_express_scores,
    rewrite_cross_format_scores,
)


def _section(section_id: str, score: int, *, findings=None, unavailable=None, evidence=None, status="green") -> dict:
    return {
        "id": section_id,
        "label": section_id.replace("_", " ").title(),
        "score": score,
        "status": status,
        "summary": "Exact-snapshot control summary.",
        "findings": findings or [],
        "unavailable": unavailable or [],
        "evidence": evidence or ["Exact-snapshot artifact retained."],
    }


def test_clean_control_preserves_score_and_green_status() -> None:
    record = evidence_score_record(_section("dependency_health", 90))

    assert record.source_score == 90
    assert record.presented_score == 90
    assert record.status == "green"
    assert record.confidence == "high"
    assert record.deduction_details == ()


def test_partial_open_finding_uses_specific_deduction_without_blanket_cap() -> None:
    record = evidence_score_record(
        _section(
            "ci_cd",
            95,
            findings=["Historical workflow reliability includes seven non-success runs."],
        )
    )

    assert record.presented_score == 92
    assert record.status == "yellow"
    assert record.presented_score != 74
    assert record.deduction_details[0].rule_id == "OPEN_FINDING"
    assert record.deduction_details[0].points == 3
    assert "seven non-success runs" in record.deduction_details[0].evidence


def test_failed_timed_out_and_unavailable_evidence_has_rule_bound_deductions() -> None:
    record = evidence_score_record(
        _section(
            "static_analysis",
            90,
            findings=["Bandit ended with status failed and requires human triage."],
            unavailable=["Semgrep exact-snapshot analyzer unavailable for this run."],
            evidence=["gitleaks ended with status timeout."],
        )
    )

    details = {item.rule_id: item for item in record.deduction_details}
    assert set(details) == {
        "ANALYZER_TIMEOUT",
        "ANALYZER_FAILURE",
        "EVIDENCE_UNAVAILABLE",
        "HUMAN_TRIAGE_REQUIRED",
    }
    assert details["ANALYZER_TIMEOUT"].evidence == "gitleaks ended with status timeout."
    assert details["ANALYZER_FAILURE"].evidence.startswith("Bandit ended with status failed")
    assert details["EVIDENCE_UNAVAILABLE"].evidence.startswith("Semgrep exact-snapshot analyzer unavailable")
    assert record.presented_score == 61
    assert record.status == "yellow"


def test_mixed_controls_keep_distinct_presented_scores() -> None:
    result = {
        "maturity_signal": {"level": "Senior", "score": 90},
        "sections": [
            _section("dependency_health", 90, findings=["OSV finding requires human triage."]),
            _section("ci_cd", 95, findings=["Historical reliability includes seven non-success runs."]),
            _section("architecture_debt", 94, findings=["One complexity hotspot remains unresolved."]),
            _section("code_audit", 86),
        ],
    }

    records, overall = reconcile_express_scores(result)
    scores = {item.section_id: item.presented_score for item in records}

    assert scores == {
        "dependency_health": 85,
        "ci_cd": 92,
        "architecture_debt": 91,
        "code_audit": 86,
    }
    assert len(set(scores.values())) == 4
    assert 74 not in scores.values()
    assert overall == 89
    assert result["maturity_signal"]["source_score"] == 90
    assert result["maturity_signal"]["presented_score"] == 89
    assert result["express_score_transparency"]["blanket_score_cap_applied"] is False


def test_not_scored_controls_never_contribute_numeric_points() -> None:
    result = {
        "maturity_signal": {"score": 90},
        "sections": [
            _section("code_audit", 90),
            {
                "id": "scanner_worker_evidence",
                "label": "Scanner Worker Evidence",
                "score": 9,
                "status": "supplemental",
                "directly_scored": False,
            },
            {
                "id": "client_acceptance",
                "label": "Client / Human Acceptance",
                "score": 0,
                "status": "gray",
                "directly_scored": False,
            },
        ],
    }

    records, overall = reconcile_express_scores(result)
    by_id = {section["id"]: section for section in result["sections"]}

    assert [item.section_id for item in records] == ["code_audit"]
    assert overall == 90
    for section_id in ("scanner_worker_evidence", "client_acceptance"):
        assert by_id[section_id]["score"] is None
        assert by_id[section_id]["presented_score"] is None
        assert by_id[section_id]["directly_scored"] is False
        assert by_id[section_id]["score_label"] == "NOT SCORED"


def test_reconciliation_is_idempotent_and_preserves_source_score() -> None:
    result = {
        "maturity_signal": {"score": 95},
        "sections": [
            _section("ci_cd", 95, findings=["Historical reliability includes seven non-success runs."])
        ],
    }

    first, first_overall = reconcile_express_scores(result)
    second, second_overall = reconcile_express_scores(result)

    assert first[0].source_score == second[0].source_score == 95
    assert first[0].presented_score == second[0].presented_score == 92
    assert first_overall == second_overall == 92
    assert result["sections"][0]["score"] == 92
    assert result["sections"][0]["source_score"] == 95


def test_markdown_and_html_are_rewritten_from_the_same_canonical_record() -> None:
    result = {
        "maturity_signal": {"score": 95},
        "sections": [
            _section("ci_cd", 95, findings=["Historical reliability includes seven non-success runs."])
        ],
        "reports": {
            "markdown": "### Ci Cd — GREEN (95/100)\nEvidence.",
            "html": "<h3>Ci Cd — GREEN (95/100)</h3>",
        },
    }

    reconcile_express_scores(result)
    rewrite_cross_format_scores(result)

    assert "### Ci Cd — YELLOW (92/100)" in result["reports"]["markdown"]
    assert "Ci Cd — YELLOW (92/100)" in result["reports"]["html"]
    transparency = result["express_score_transparency"]
    assert transparency["version"] == VERSION
    assert transparency["records"][0]["presented_score"] == 92
    deduction = transparency["records"][0]["deductions"][0]
    assert deduction["rule_id"] == "OPEN_FINDING"
    assert deduction["evidence"] == "Historical reliability includes seven non-success runs."
