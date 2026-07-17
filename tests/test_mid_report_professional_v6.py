from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from pypdf import PdfReader

from nico.mid_report_professional_v6 import MID_REPORT_V6_VERSION, _display, _enhance, _markdown, _pdf


V4_TEST = Path(__file__).with_name("test_mid_report_professional_v4.py")
SPEC = importlib.util.spec_from_file_location("mid_v4_fixture_for_v6", V4_TEST)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture() -> dict:
    payload = MODULE._payload()
    payload["evidence_coverage"] = {"percent": 100, "numerator": 12, "denominator": 12}
    payload["decision_summary"]["primary_score_constraints"] = [
        {"section_id": "static_analysis", "label": "Static Analysis", "score": 49, "primary_reason": "Bandit and Semgrep exact-snapshot evidence is incomplete."},
        {"section_id": "code_audit", "label": "Code Audit", "score": 60, "primary_reason": "Four sampled risk patterns require disposition."},
        {"section_id": "dependency_health", "label": "Dependency / Library Ecosystem", "score": 72, "primary_reason": "Scanner execution and accepted structured evidence do not yet align."},
    ]
    for section in payload["sections"]:
        if section.get("id") == "dependency_health":
            section["evidence"] = [
                "Dependency scanners run: npm-audit, osv-scanner, pip-audit.",
                "Structured scanners completed=0/3.",
            ]
            section["score_evidence_breakdown"] = {
                "verified_dependency_tool_count": 0,
                "material_dependency_finding_count": 0,
                "score_forced_upward": False,
                "optional_value": None,
            }
        if section.get("id") == "static_analysis":
            section["evidence"] = [
                "Structured exact-snapshot analyzers completed=0/2.",
                "TypeScript compiler static-analysis state=completed.",
            ]
            section["unavailable"].append("Bandit did not provide parseable exact-snapshot evidence.")
        if section.get("id") == "ci_cd":
            section["evidence"] = [
                "Workflow history returned success=79 and non-success=17.",
                "Detected CI commands: pytest, npm run lint, npm run build.",
            ]
    payload["deduplicated_review_exceptions"] = [
        {
            "severity": "medium",
            "category": "score_affecting_claim",
            "title": "Score-affecting claim in Static Analysis",
            "reason": "A limited section contributes to the reported score.",
        },
        {
            "severity": "medium",
            "category": "missing_evidence_affecting_delivery",
            "title": "Unavailable Functional QA evidence",
            "reason": "Direct functional evidence was not attached.",
        },
    ]
    payload["review_exception_original_count"] = 4
    payload["review_exception_final_count"] = 2
    return payload


def test_mid_v6_adds_decision_status_evidence_matrix_and_actionable_controls() -> None:
    result = _enhance(fixture())

    assert result["presentation_version"] == MID_REPORT_V6_VERSION
    assert result["decision_summary"]["review_decision"] == "Proceed to human review with remediation conditions"
    assert len(result["evidence_assurance_matrix"]) == 7
    static = next(item for item in result["evidence_assurance_matrix"] if item["section_id"] == "static_analysis")
    assert static["parsed"] == "Incomplete"
    actions = {item["section_id"]: item for item in result["decision_summary"]["action_plan"]}
    assert "Bandit, Semgrep, ESLint, and TypeScript" in actions["static_analysis"]["action"]
    assert "product regression" in actions["ci_cd"]["action"]
    assert result["report_depth_contract"]["target_pdf_pages"] == 8
    assert result["report_depth_contract"]["blank_values_normalized"] is True


def test_mid_v6_markdown_replaces_generic_boilerplate_and_normalizes_blank_values() -> None:
    markdown = _markdown(_enhance(fixture()))

    assert "## Evidence assurance matrix" in markdown
    assert "Accepted for scoring" in markdown
    assert "Owner / effort" in markdown
    assert "No material defect was confirmed in this control." in markdown
    assert "No specific repair finding was retained; reviewer validation remains required." not in markdown
    assert "Optional Value: Not provided" in markdown
    assert "classify every non-success run" in markdown.lower()
    assert _display(False) == "No"
    assert _display(None) == "Not provided"


def test_mid_v6_pdf_is_dense_unique_and_decision_ready() -> None:
    result = _enhance(fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))
    extracted = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    joined = "\n".join(extracted)

    assert 7 <= len(reader.pages) <= 10
    assert all(len(text) >= 120 for text in extracted)
    assert "Executive technical decision" in joined
    assert "Evidence Assurance and Score Sensitivity" in joined
    assert "Evidence assurance matrix" in joined
    assert "Prioritized Remediation Roadmap" in joined
    assert "CI/CD non-success classification required" in joined
    assert "Review Exceptions, Integrity, and Approval Boundary" in joined
    assert "Weighted technical scorecard — Weighted Technical Scorecard" not in joined
    assert "Repair Plan and Human-Context Requests — Prioritized" not in joined
    assert "Not provided" in joined
