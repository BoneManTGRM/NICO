from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "mid-approval" / "page.tsx"
CONTEXT = ROOT / "apps" / "web" / "app" / "MidWorkspaceContext.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_legacy_mid_approval_route_is_preserved_but_not_global() -> None:
    context = CONTEXT.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'path: "/mid-review"' in context
    assert 'path: "/mid-report"' in context
    assert 'path: "/mid-approval"' in context
    assert context.index('path: "/mid-review"') < context.index('path: "/mid-report"') < context.index('path: "/mid-approval"')
    assert 'href="/assessment?tier=express#assessment"' in layout
    assert "Start Express or Comprehensive" in layout
    assert "NICO never approves findings or creates client delivery automatically" in layout
    assert "MidSectionReviewPortal" not in layout


def test_page_uses_shared_exact_scope_admin_reviewer_and_notes() -> None:
    source = _page()
    context = CONTEXT.read_text(encoding="utf-8")

    for label in ("Mid run ID", "Customer ID", "Project ID", "NICO admin token", "Reviewer or operator"):
        assert label in context
    assert 'type="password"' in context
    assert "useMidWorkspace" in source
    assert "MidIdentityPanel" in source
    assert 'MidStageNavigation current="approval"' in source
    assert "reviewer: actor" in source
    assert "Item-level reviewer note" in source
    assert "Final decision note" in source
    assert '"X-NICO-Admin-Token": adminToken' in source


def test_page_uses_dedicated_request_status_disposition_and_decision_endpoints() -> None:
    source = _page()

    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval/request" in source
    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/approval?${params.toString()}" in source
    assert "/assessment/mid-run/approval/${encodeURIComponent(approvalId)}/review-items" in source
    assert "/assessment/mid-run/approval/${encodeURIComponent(approval.approval_id)}/review-items/${encodeURIComponent(item.item_id)}" in source
    assert "/assessment/mid-run/approval/${encodeURIComponent(approval.approval_id)}/${state}" in source
    assert "Request Mid approval" in source
    assert "Refresh approval" in source
    assert "Request evidence" in source
    assert "Reject item" in source


def test_approval_ui_requires_a_structured_decision_for_every_current_exception() -> None:
    source = _page()

    assert "Decide each current item" in source
    assert "Accept as represented" in source
    assert "Accept as inference only" in source
    assert "accepted_item_ids" in source
    assert "approval_ready" in source
    assert "!structuredReviewReady" in source
    assert "reviewed_item_ids: acceptedIds" in source
    assert "Approve and generate separate PDF" in source
    assert "Acknowledge all current exception items" not in source


def test_inference_only_button_cannot_accept_score_changing_inference() -> None:
    source = _page()

    assert "!item.inference_based || item.score_change_material" in source
    assert "Score-changing:" in source
    assert "Inference-based:" in source


def test_page_displays_exact_identity_and_delivery_boundary() -> None:
    source = _page()

    assert "snapshot_commit_sha: approval.snapshot_commit_sha" in source
    assert "draft_pdf_sha256: approval.draft_pdf_sha256" in source
    assert "truth_sha256: approval.truth_sha256" in source
    assert "review_packet_sha256: approval.review_packet_sha256" in source
    assert "disposition_set_sha256: reviewSummary?.disposition_set_sha256" in source
    assert "Client delivery" in source
    assert "Approval does not create a client link" in source
    assert "secure delivery remains disabled" in source


def test_approved_pdf_download_verifies_approval_and_report_headers() -> None:
    source = _page()

    assert "/report/approved/pdf?${params.toString()}" in source
    assert 'response.headers.get("X-NICO-Report-ID")' in source
    assert 'response.headers.get("X-NICO-PDF-SHA256")' in source
    assert 'response.headers.get("X-NICO-Approval-ID")' in source
    assert 'response.headers.get("X-NICO-Approval-Identity-SHA256")' in source
    assert "The approved PDF response did not match the approval identity" in source
    assert 'blob.type !== "application/pdf"' in source


def test_admin_token_is_not_rendered_in_identity_json() -> None:
    source = _page()
    identity = source.split('<summary>Exact identity</summary>', 1)[1].split("</details>", 1)[0]

    assert "adminToken" not in identity
    assert "admin_token" not in identity
    assert "review_packet_sha256" in identity
    assert "truth_sha256" in identity
    assert "disposition_set_sha256" in identity


def test_production_registers_complete_mid_approval_route_group() -> None:
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_approval_routes" in source
    assert "MID_APPROVAL_ROUTES" in source
    routes = [
        '("POST", "/assessment/mid-run/{run_id}/approval/request")',
        '("GET", "/assessment/mid-run/{run_id}/approval")',
        '("GET", "/assessment/mid-run/approval/{approval_id}/review-items")',
        '("POST", "/assessment/mid-run/approval/{approval_id}/review-items/{item_id}")',
        '("POST", "/assessment/mid-run/approval/{approval_id}/{state}")',
        '("GET", "/assessment/mid-run/{run_id}/report/approved")',
        '("GET", "/assessment/mid-run/{run_id}/report/approved/pdf")',
    ]
    for route in routes:
        assert route in source
