from __future__ import annotations

import base64
import io

from pypdf import PdfReader
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

from nico import express_pdf_section_index_binding_v1 as index_binding
from nico import express_score_assurance_export_v1 as score_export
from nico import scanner_tool_runners
from nico.accurate_green_release_v2 import install_accurate_green_release_v2


def _simple_pdf(lines: list[str]) -> bytes:
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=letter, invariant=1)
    y = 740
    for line in lines:
        page.drawString(42, y, line)
        y -= 20
    page.save()
    return buffer.getvalue()


def _result(*, include_pdf: bool = False) -> dict:
    reports: dict = {
        "markdown": "# Existing report\n\n### Code Audit — GREEN (86/100)\n",
        "html": "<html><body><h3>Code Audit — GREEN (86/100)</h3></body></html>",
    }
    if include_pdf:
        reports["pdf_base64"] = base64.b64encode(
            _simple_pdf(["Code Audit", "Secrets Exposure Review", "Review and Delivery"])
        ).decode("ascii")
    return {
        "status": "complete",
        "human_review_required": True,
        "client_delivery_allowed": False,
        "sections": [
            {
                "id": "code_audit",
                "label": "Code Audit",
                "score": 86,
                "presented_score": 86,
                "status": "green",
                "evidence": ["Current-run evidence completed."],
                "findings": [],
                "unavailable": [],
            },
            {
                "id": "secrets_review",
                "label": "Secrets Exposure Review",
                "score": 64,
                "presented_score": 64,
                "status": "yellow",
                "evidence": ["TruffleHog returned one candidate."],
                "findings": ["One candidate requires authorized human disposition."],
                "unavailable": ["Gitleaks timed out before full-history completion."],
            },
            {
                "id": "client_acceptance",
                "label": "Review and Delivery",
                "score": None,
                "presented_score": None,
                "status": "gray",
                "directly_scored": False,
                "evidence": [],
                "findings": [],
                "unavailable": [],
            },
        ],
        "reports": reports,
    }


def test_export_defensively_computes_verified_green_and_action_plan() -> None:
    install_accurate_green_release_v2()
    result = score_export.publish_score_assurance_exports(_result())

    records = result["score_assurance_export"]["records"]
    by_id = {item["section_id"]: item for item in records}
    assert by_id["code_audit"]["verified_green"] is True
    assert by_id["secrets_review"]["verified_green"] is False
    assert by_id["client_acceptance"]["verified_green"] is False

    plan = result["yellow_section_improvement_plan"]
    assert plan["status"] == "complete"
    assert plan["thresholds_lowered"] is False
    assert plan["missing_evidence_treated_as_clean"] is False
    assert [item["section_id"] for item in plan["controls"]] == ["secrets_review"]
    assert "Gitleaks" in plan["controls"][0]["recommended_action"]
    assert "Technical score >= 80" in plan["controls"][0]["exit_criteria"]


def test_pdf_index_appends_when_labels_exist_but_score_labels_do_not() -> None:
    install_accurate_green_release_v2()
    result = _result(include_pdf=True)

    index_binding.append_canonical_section_index(result)

    contract = result["express_pdf_section_index"]
    assert contract["index_appended"] is True
    assert contract["missing_labels_after"] == []
    assert contract["missing_score_labels_after"] == []
    pdf = base64.b64decode(result["reports"]["pdf_base64"], validate=True)
    text = "\n".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(pdf)).pages)
    assert "86/100" in text
    assert "64/100" in text
    assert "NOT SCORED" in text


def test_history_scanner_runtime_is_hardened_without_weakening_scope() -> None:
    install_accurate_green_release_v2()
    specs = {spec.name: spec for spec in scanner_tool_runners.TOOL_SPECS}

    assert specs["gitleaks"].timeout_seconds >= 600
    assert specs["trufflehog"].timeout_seconds >= 600
    assert specs["semgrep"].timeout_seconds >= 360
    assert specs["gitleaks"].scans_git_history is True
    assert specs["trufflehog"].scans_git_history is True


def test_live_binding_installs_accurate_green_release() -> None:
    source = __import__("pathlib").Path("nico/express_live_renderer_binding_v22.py").read_text(encoding="utf-8")
    assert "install_accurate_green_release_v2" in source
    assert "verified_green_remediation_page" in source
    assert "yellow_controls_have_exit_criteria" in source
