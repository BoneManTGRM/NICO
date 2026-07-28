from __future__ import annotations

import base64
import io

from reportlab.pdfgen import canvas

from nico.comprehensive_decision_grade_csv_v6 import _findings_csv
from nico.phase6_canonical_truth_v2 import (
    _canonicalize_surface_assessment,
    canonicalize_findings_v2,
    compare_language_factual_parity,
    validate_cross_format_truth,
)


def _finding(*, line: int, rule: str = "python.sql-concat", message: str = "Avoid SQL string concatenation") -> dict[str, object]:
    return {
        "id": "RISK-SQL",
        "finding_id": "RISK-SQL",
        "tool": "semgrep",
        "rule_id": rule,
        "priority": "P0",
        "category": "static",
        "title": message,
        "message": message,
        "file_path": "/home/runner/work/NICO/NICO/nico/comprehensive_run_store.py",
        "line": line,
        "acceptance_criteria": ["Verify placeholders", "Verify placeholders"],
        "roadmap_mappings": ["WP-01", "WP-01"],
        "backlog_mappings": ["NICO-1", "NICO-1"],
    }


def test_absolute_paths_are_repository_relative_and_occurrences_group() -> None:
    actionable, dispositions = canonicalize_findings_v2([_finding(line=33), _finding(line=58)])

    assert actionable == []
    assert len(dispositions) == 1
    finding = dispositions[0]
    assert finding["canonical_path"] == "nico/comprehensive_run_store.py"
    assert finding["canonical_location"] == "nico/comprehensive_run_store.py:33"
    assert finding["related_locations"] == [
        "nico/comprehensive_run_store.py:33",
        "nico/comprehensive_run_store.py:58",
    ]
    assert len(finding["occurrence_fingerprints"]) == 2
    assert finding["roadmap_mappings"] == ["WP-01"]
    assert finding["backlog_mappings"] == ["NICO-1"]


def test_same_incoming_id_different_rule_is_not_merged() -> None:
    first = _finding(line=33, rule="rule-a", message="First rule")
    second = _finding(line=33, rule="rule-b", message="Second rule")
    first["file_path"] = "nico/unreviewed.py"
    second["file_path"] = "nico/unreviewed.py"

    actionable, dispositions = canonicalize_findings_v2([first, second])

    assert dispositions == []
    assert len(actionable) == 2
    assert len({item["finding_id"] for item in actionable}) == 2
    assert len({item["finding_key"] for item in actionable}) == 2


def _assessment() -> dict[str, object]:
    finding = {
        "id": "RISK-ABC",
        "finding_id": "RISK-ABC",
        "priority": "P1",
        "status": "open",
        "category": "static",
        "executive_title": "Unsafe SQL query construction",
        "technical_summary": "A source-specific query path requires review.",
        "analyzer_message": "Analyzer detail",
        "tool": "semgrep",
        "rule_id": "sql-rule",
        "canonical_path": "nico/example.py",
        "canonical_line": 5,
        "canonical_location": "nico/example.py:5",
        "location": "nico/example.py:5",
        "acceptance_criteria": ["Exact-SHA analyzer rerun passes"],
        "roadmap_mappings": ["WP-01"],
        "backlog_mappings": ["NICO-1"],
    }
    return {
        "repository": "BoneManTGRM/NICO",
        "commit_sha": "a" * 40,
        "run_id": "run-1",
        "maturity_signal": {"presented_score": 80},
        "evidence_adjusted_score": 78,
        "evidence_health_summary": {"completed_scanners": ["bandit"], "incomplete_scanners": []},
        "decision_grade_findings_register": [finding],
        "findings_register": [finding],
        "executive_risk_register": [finding],
        "limitation_metrics": {"individual_limitation_records": 1},
        "ci_health": {"assessed_commit": {"status": "green", "green": True, "commit_sha": "a" * 40}},
        "delivery_status": "Human Review Required",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "sections": [],
    }


def _pdf(text: str) -> str:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer)
    y = 800
    for line in text.splitlines():
        page.drawString(30, y, line)
        y -= 16
    page.save()
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_cross_format_truth_contract_accepts_identical_facts() -> None:
    assessment = _canonicalize_surface_assessment(_assessment())
    finding = assessment["decision_grade_findings_register"][0]
    surface = "\n".join([
        "80/100",
        "78/100",
        "bandit",
        finding["finding_id"],
        finding["canonical_path"],
        str(finding["canonical_line"]),
        finding["canonical_location"],
    ])
    identity = {"repository": "BoneManTGRM/NICO", "commit_sha": "a" * 40, "run_id": "run-1"}
    result = {
        "status": "complete",
        "assessment": assessment,
        "report_quality_contract": {},
        "report_package": {
            "json": {"identity": identity, "assessment": assessment},
            "findings_csv": _findings_csv(assessment["decision_grade_findings_register"]),
            "markdown": surface,
            "html": surface,
            "pdf_base64": _pdf(surface),
        },
    }

    validated = validate_cross_format_truth(result)

    assert validated["status"] == "complete"
    assert validated["report_quality_contract"]["cross_format_truth_consistent"] is True
    assert validated["report_package"]["canonical_truth_manifest"]["status"] == "valid"


def test_language_parity_compares_facts_not_prose() -> None:
    english = _canonicalize_surface_assessment(_assessment())
    spanish = _canonicalize_surface_assessment(_assessment())
    english["executive_summary"] = "Human review required."
    spanish["executive_summary"] = "Se requiere revisión humana."

    parity = compare_language_factual_parity(english, spanish)

    assert parity["equivalent"] is True
    assert parity["english_fingerprint"] == parity["spanish_fingerprint"]
