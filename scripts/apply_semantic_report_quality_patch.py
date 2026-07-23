#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

TRANSFORMED_PATHS = (
    "scripts/two_service_live_acceptance.py",
    ".github/workflows/two-service-production-acceptance.yml",
    "nico/mid_assessment_report.py",
    "nico/mid_report_professional_v4.py",
    "nico/mid_report_professional_v6.py",
    "nico/mid_report_professional_v7.py",
    "nico/comprehensive_canonical_truth.py",
)


def replace(path: str, old: str, new: str, count: int = 1) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"{path}: expected {count} occurrence(s), found {actual}: {old!r}")
    target.write_text(text.replace(old, new), encoding="utf-8")


def apply() -> None:
    replace(
        "scripts/two_service_live_acceptance.py",
        '        assert pdf["page_count"] >= 30, f"Comprehensive PDF is only {pdf[\'page_count\']} pages"\n',
        '        semantic_markers = (\n'
        '            "NICO Comprehensive Technical Assessment",\n'
        '            "Functional QA",\n'
        '            "Platform Parity",\n'
        '            "Six-Month Roadmap",\n'
        '            "Staffing, Sequencing, and Cost",\n'
        '            "Evidence Appendix",\n'
        '            "Human Review and Acceptance Gate",\n'
        '        )\n'
        '        for marker in semantic_markers:\n'
        '            assert marker in markdown, f"Comprehensive Markdown omitted {marker}"\n'
        '            assert marker in pdf["text"], f"Comprehensive PDF omitted {marker}"\n'
        '        upper_markdown = markdown.upper()\n'
        '        upper_pdf = pdf["text"].upper()\n'
        '        for stale in ("DRAFT ONLY", "DRAFT - HUMAN REVIEW REQUIRED", "DRAFT · HUMAN REVIEW REQUIRED", "COMPLETE ONLY AS A DRAFT"):\n'
        '            assert stale not in upper_markdown, f"Comprehensive Markdown retained stale status: {stale}"\n'
        '            assert stale not in upper_pdf, f"Comprehensive PDF retained stale status: {stale}"\n'
        '        assert "FINAL REPORT" in upper_markdown\n'
        '        assert "FINAL REPORT" in upper_pdf\n'
        '        assert "PENDING HUMAN APPROVAL" in upper_markdown\n'
        '        assert "PENDING HUMAN APPROVAL" in upper_pdf\n'
        '        assert "\\x7f" not in pdf["text"], "Comprehensive PDF contains a control-character glyph"\n',
    )
    replace(
        "scripts/two_service_live_acceptance.py",
        '        "pdf": {key: value for key, value in pdf.items() if key != "text"},\n',
        '        "pdf": {key: value for key, value in pdf.items() if key != "text"},\n'
        '        "semantic_contract": {\n'
        '            "status": "passed",\n'
        '            "page_count_informational_only": True,\n'
        '            "required_sections_verified": True,\n'
        '            "final_report_language_verified": True,\n'
        '            "stale_draft_language_absent": True,\n'
        '            "control_characters_absent": True,\n'
        '        },\n',
    )
    replace(
        ".github/workflows/two-service-production-acceptance.yml",
        '          assert all(item["report"]["pdf"]["page_count"] >= 30 for item in comprehensive)\n',
        '          assert all(item["report"]["semantic_contract"]["status"] == "passed" for item in comprehensive)\n'
        '          assert all(item["report"]["semantic_contract"]["required_sections_verified"] is True for item in comprehensive)\n'
        '          assert all(item["report"]["semantic_contract"]["stale_draft_language_absent"] is True for item in comprehensive)\n',
    )

    replace("nico/mid_assessment_report.py", 'MID_REPORT_VERSION = "mid-assessment-draft-v1"', 'MID_REPORT_VERSION = "mid-assessment-final-pending-approval-v2"')
    replace("nico/mid_assessment_report.py", 'DRAFT_LABEL = "DRAFT — HUMAN REVIEW REQUIRED"', 'DRAFT_LABEL = "FINAL REPORT - PENDING HUMAN APPROVAL"')
    replace("nico/mid_assessment_report.py", '        "status": "draft",', '        "status": "final_pending_human_approval",')
    replace(
        "nico/mid_assessment_report.py",
        '            "This is a draft Mid Assessment and requires human technical review before approval or client delivery.",',
        '            "This is a complete final assessment report pending required human approval; client delivery remains blocked until approval.",',
    )
    replace("nico/mid_assessment_report.py", '        canvas.drawString(LEFT + 2, y, "•")', '        canvas.drawString(LEFT + 2, y, "-")')
    replace("nico/mid_assessment_report.py", '    """Generate one professional Mid draft report bound to the current review packet."""', '    """Generate one professional final report pending approval, bound to the current review packet."""')
    replace("nico/mid_assessment_report.py", '"Admin authentication is required to generate a Mid draft report."', '"Admin authentication is required to generate a final report pending approval."')
    replace("nico/mid_assessment_report.py", '"The Mid run must complete before its draft report can be generated."', '"The assessment run must complete before its final report can be generated."')
    replace("nico/mid_assessment_report.py", '"Mid draft PDF rendering failed:', '"Final report PDF rendering failed:')
    replace("nico/mid_assessment_report.py", '"Mid draft PDF rendering did not produce a valid PDF."', '"Final report PDF rendering did not produce a valid PDF."')
    replace("nico/mid_assessment_report.py", '-DRAFT.pdf"', '-FINAL-PENDING-APPROVAL.pdf"')

    replace("nico/mid_report_professional_v4.py", 'MID_REPORT_V4_VERSION = "mid-assessment-draft-v4-full-depth"', 'MID_REPORT_V4_VERSION = "mid-assessment-final-v4-full-depth"')
    replace("nico/mid_report_professional_v4.py", '_DRAFT_LABEL = "DRAFT — HUMAN REVIEW REQUIRED"', '_DRAFT_LABEL = "FINAL REPORT - PENDING HUMAN APPROVAL"')
    replace("nico/mid_report_professional_v6.py", 'MID_REPORT_V6_VERSION = "mid-assessment-draft-v6-executive-actionable"', 'MID_REPORT_V6_VERSION = "mid-assessment-final-v6-executive-actionable"')
    replace("nico/mid_report_professional_v7.py", 'VERSION = "mid-assessment-draft-v8-premium"', 'VERSION = "mid-assessment-final-v8-premium"')
    replace(
        "nico/mid_report_professional_v7.py",
        '["Page contract", "35–50 substantive pages", "Delivery", "Blocked pending approval"],',
        '["Report contract", "Semantic sections verified", "Delivery", "Blocked pending approval"],',
    )
    replace(
        "nico/comprehensive_canonical_truth.py",
        '        "delivery_status": "Draft only",',
        '        "report_finality": "final",\n'
        '        "approval_status": "pending_human_approval",\n'
        '        "delivery_status": "blocked_pending_human_approval",',
    )


def verify() -> None:
    acceptance = Path("scripts/two_service_live_acceptance.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/two-service-production-acceptance.yml").read_text(encoding="utf-8")
    report = Path("nico/mid_assessment_report.py").read_text(encoding="utf-8")
    canonical = Path("nico/comprehensive_canonical_truth.py").read_text(encoding="utf-8")
    assert 'pdf["page_count"] >= 30' not in acceptance
    assert '"semantic_contract"' in acceptance
    assert 'semantic_contract"]["status"] == "passed"' in workflow
    assert "DRAFT — HUMAN REVIEW REQUIRED" not in report
    assert 'canvas.drawString(LEFT + 2, y, "-")' in report
    assert '"report_finality": "final"' in canonical


if __name__ == "__main__":
    apply()
    verify()
    print("semantic report quality source transformation verified")
