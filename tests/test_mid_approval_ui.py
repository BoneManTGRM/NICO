from __future__ import annotations

from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "mid-approval" / "page.tsx"
LAYOUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "layout.tsx"
PRODUCTION = Path(__file__).resolve().parents[1] / "nico" / "api" / "production.py"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_navigation_exposes_mid_approval_after_review_and_report():
    layout = LAYOUT.read_text(encoding="utf-8")

    assert '<a href="/mid-review">Mid Review</a>' in layout
    assert '<a href="/mid-report">Mid Report</a>' in layout
    assert '<a href="/mid-approval">Mid Approval</a>' in layout
    assert layout.index('href="/mid-review"') < layout.index('href="/mid-report"') < layout.index('href="/mid-approval"')
    assert "Approval creates a separate approved artifact but does not create a client delivery link" in layout


def test_page_requires_exact_scope_admin_reviewer_and_note():
    source = _page()

    assert "Mid run ID" in source
    assert "Customer ID" in source
    assert "Project ID" in source
    assert "NICO admin token" in source
    assert 'type="password"' in source
    assert "Reviewer name or role" in source
    assert "Decision note" in source
    assert '"X-NICO-Admin-Token": adminToken' in source


def test_page_uses_dedicated_request_status_and_decision_endpoints():
    source = _page()

    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval/request" in source
    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval?${params.toString()}" in source
    assert "/assessment/mid-run/approval/${encodeURIComponent(approval.approval_id)}/${state}" in source
    assert "Request Mid approval" in source
    assert "Refresh approval" in source
    assert "Request more evidence" in source
    assert "Reject" in source


def test_approval_requires_all_current_exception_items():
    source = _page()

    assert "Acknowledge all current exception items" in source
    assert "item.truth_status" not in source
    assert "allItems.every" in source
    assert "reviewed_item_ids: reviewed" in source
    assert "!allReviewed" in source
    assert "Approve and generate separate PDF" in source


def test_page_displays_exact_identity_and_delivery_boundary():
    source = _page()

    assert "snapshot_commit_sha: approval.snapshot_commit_sha" in source
    assert "draft_pdf_sha256: approval.draft_pdf_sha256" in source
    assert "truth_sha256: approval.truth_sha256" in source
    assert "review_packet_sha256: approval.review_packet_sha256" in source
    assert "Client delivery" in source
    assert "Approval does not create a client link" in source
    assert "secure delivery remains disabled" in source


def test_approved_pdf_download_verifies_approval_and_report_headers():
    source = _page()

    assert "/report/approved/pdf?${params.toString()}" in source
    assert 'response.headers.get("X-NICO-Report-ID")' in source
    assert 'response.headers.get("X-NICO-PDF-SHA256")' in source
    assert 'response.headers.get("X-NICO-Approval-ID")' in source
    assert 'response.headers.get("X-NICO-Approval-Identity-SHA256")' in source
    assert "The approved PDF response did not match the approval identity" in source
    assert 'blob.type !== "application/pdf"' in source


def test_admin_token_is_not_rendered_in_identity_json():
    source = _page()
    identity = source.split("JSON.stringify({", 1)[1].split("}, null, 2)", 1)[0]

    assert "adminToken" not in identity
    assert "admin_token" not in identity
    assert "review_packet_sha256" in identity
    assert "truth_sha256" in identity


def test_production_registers_complete_mid_approval_route_group():
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_approval_routes" in source
    assert "MID_APPROVAL_ROUTES" in source
    routes = [
        '("POST", "/assessment/mid-run/{run_id}/approval/request")',
        '("GET", "/assessment/mid-run/{run_id}/approval")',
        '("POST", "/assessment/mid-run/approval/{approval_id}/{state}")',
        '("GET", "/assessment/mid-run/{run_id}/report/approved")',
        '("GET", "/assessment/mid-run/{run_id}/report/approved/pdf")',
    ]
    for route in routes:
        assert route in source
