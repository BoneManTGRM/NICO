from __future__ import annotations

from pathlib import Path


GUARD = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "AssessmentRequestGuard.tsx"
API = Path(__file__).resolve().parents[1] / "nico" / "mid_assessment_api.py"


def test_mid_run_response_is_captured_without_consuming_page_response():
    source = GUARD.read_text(encoding="utf-8")

    assert "isMidRunResponseRequest" in source
    assert 'parsed.pathname === "/assessment/mid-run"' in source
    assert '/^\\/assessment\\/mid-run\\/[^/]+\\/status$/' in source
    assert "response.clone()" in source
    assert "void captureMidReport" in source
    assert "return response" in source


def test_mid_report_banner_exposes_download_and_copy_controls():
    source = GUARD.read_text(encoding="utf-8")

    assert 'data-testid="mid-report-ready"' in source
    assert "Mid draft report ready" in source
    assert "Download Mid draft PDF" in source
    assert "Copy Markdown" in source
    assert "Copy HTML" in source
    assert "human review remains required" in source.lower()
    assert "client delivery is still blocked" in source.lower()


def test_mid_pdf_download_uses_returned_base64_and_filename():
    source = GUARD.read_text(encoding="utf-8")

    assert "reports.pdf_base64" in source
    assert "reports.pdf_filename" in source
    assert "reports.pdf_sha256" in source
    assert "Uint8Array.from(atob(encoded)" in source
    assert 'new Blob([bytes], {type: "application/pdf"})' in source
    assert "saveBlob(blob, midReport.pdfFilename)" in source


def test_mid_api_replaces_generic_skips_with_dedicated_artifact_states():
    source = API.read_text(encoding="utf-8")

    assert 'result["report_generation_status"] = "complete"' in source
    assert '"reports",\n        "complete"' in source
    assert '"approval_request",\n            "complete"' in source
    assert "Dedicated Mid draft report generated automatically" in source
    assert "Exact-state Mid human-review request created automatically" in source
    assert 'result["express_report_generated"] = False' in source
    assert 'result["full_report_generated"] = False' in source


def test_mid_api_returns_report_formats_directly_to_one_click_intake():
    source = API.read_text(encoding="utf-8")

    assert 'result["reports"] = {' in source
    assert '"markdown": str(formats.get("markdown") or "")' in source
    assert '"html": str(formats.get("html") or "")' in source
    assert '"pdf_base64": str(formats.get("pdf") or "")' in source
    assert '"pdf_filename": str(report.get("pdf_filename")' in source
    assert '"pdf_sha256": str(report.get("pdf_sha256")' in source
