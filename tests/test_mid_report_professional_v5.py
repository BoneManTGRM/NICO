from __future__ import annotations

import importlib.util
import io
from pathlib import Path

from pypdf import PdfReader

from nico.mid_report_professional_v5 import MID_REPORT_V5_VERSION, _enhance, _markdown, _pdf


V4_TEST = Path(__file__).with_name("test_mid_report_professional_v4.py")
SPEC = importlib.util.spec_from_file_location("mid_v4_fixture", V4_TEST)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def fixture() -> dict:
    payload = MODULE._payload()
    payload["decision_summary"]["technical_score"] = 70
    payload["score_integrity"].update({
        "calculated_score": 70,
        "reported_score": 70,
        "final_report_score": 70,
        "score_match": False,
    })
    for section in payload["sections"]:
        if section.get("id") == "static_analysis":
            section["unavailable"].append("bandit")
        if section.get("id") == "secrets_review":
            section["unavailable"].append("gitleaks")
    return payload


def test_mid_v5_reconciles_one_canonical_score_and_constraint_order() -> None:
    result = _enhance(fixture())

    assert result["presentation_version"] == MID_REPORT_V5_VERSION
    assert result["decision_summary"]["technical_score"] == 71
    assert result["score_integrity"]["calculated_score"] == 71
    assert result["score_integrity"]["reported_score"] == 71
    assert result["score_integrity"]["final_report_score"] == 71
    assert result["score_integrity"]["score_match"] is True
    assert [item["label"] for item in result["decision_summary"]["primary_score_constraints"]] == [
        "Static Analysis",
        "Code Audit",
        "Dependency / Library Ecosystem",
    ]


def test_mid_v5_uses_clear_coverage_and_readable_tool_gaps() -> None:
    markdown = _markdown(_enhance(fixture()))

    assert "Evidence-unit coverage" in markdown
    assert "Analyzer execution is separate" in markdown
    assert "Bandit did not provide accepted parseable exact-snapshot evidence" in markdown
    assert "Gitleaks did not provide accepted same-run history evidence" in markdown
    assert "\n- Limitation: bandit\n" not in markdown.lower()
    assert "\n- Limitation: gitleaks\n" not in markdown.lower()
    assert markdown.count("## Human-context evidence requests") == 1
    assert markdown.count("## Review exceptions and integrity") == 1


def test_mid_v5_pdf_is_compact_and_has_no_orphan_page() -> None:
    result = _enhance(fixture())
    reader = PdfReader(io.BytesIO(_pdf(result)))
    extracted = [" ".join((page.extract_text() or "").split()) for page in reader.pages]
    joined = "\n".join(extracted)

    assert 10 <= len(reader.pages) <= 12
    assert all(len(text) >= 120 for text in extracted)
    assert "Evidence-unit coverage" in joined
    assert "Technical Review 1 of 7" in joined
    assert "Technical Review 7 of 7" in joined
    assert "Repair Plan and Human-Context Requests" in joined
    assert "Review Exceptions and Integrity" in joined
    assert joined.count("Unavailable Functional QA evidence") == 1
