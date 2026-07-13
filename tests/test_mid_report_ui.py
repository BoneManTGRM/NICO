from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "mid-report" / "page.tsx"
CONTEXT = ROOT / "apps" / "web" / "app" / "MidWorkspaceContext.tsx"
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_mid_report_page_uses_shared_exact_scope_and_admin_token():
    source = _page()
    context = CONTEXT.read_text(encoding="utf-8")

    for label in ("Mid run ID", "Customer ID", "Project ID", "NICO admin token"):
        assert label in context
    assert 'type="password"' in context
    assert "useMidWorkspace" in source
    assert "MidIdentityPanel" in source
    assert 'MidStageNavigation current="report"' in source
    assert '"X-NICO-Admin-Token": adminToken' in source
    assert "customer_id: customerId.trim()" in source
    assert "project_id: projectId.trim()" in source


def test_draft_generation_uses_dedicated_mid_endpoint_and_identity_checks():
    source = _page()

    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/report/draft" in source
    assert 'method: "POST"' in source
    assert 'data.report_path !== "mid_run"' in source
    assert 'data.report_type !== "mid_assessment"' in source
    assert "data.approved || data.client_delivery_allowed || !data.human_review_required" in source
    assert "Generate Mid draft report" in source


def test_pdf_download_verifies_all_identity_headers_before_saving():
    source = _page()

    assert "/report/draft/pdf?${params.toString()}" in source
    assert 'response.headers.get("X-NICO-Report-ID")' in source
    assert 'response.headers.get("X-NICO-PDF-SHA256")' in source
    assert 'response.headers.get("X-NICO-Review-Packet-SHA256")' in source
    assert 'response.headers.get("X-NICO-Source-Identity-SHA256")' in source
    assert 'response.headers.get("X-NICO-Report-Path")' in source
    assert 'reportPath !== "mid_run"' in source
    assert 'blob.type !== "application/pdf"' in source
    assert "Download verified draft PDF" in source


def test_page_explicitly_preserves_draft_and_delivery_boundary():
    source = _page()

    assert "Draft generation does not approve the assessment" in source
    assert "create a client link" in source
    assert "enable client delivery" in source
    assert "Human review required" in source
    assert "Client delivery" in source
    assert "client_delivery_allowed" in source
    assert "approved" in source
    assert "/approve" not in source
    assert "/reject" not in source


def test_draft_identity_display_includes_snapshot_review_and_hash_bindings():
    source = _page()

    assert "snapshot_id: report.snapshot_id" in source
    assert "snapshot_commit_sha: report.snapshot_commit_sha" in source
    assert "review_packet_id: report.review_packet_id" in source
    assert "review_packet_sha256: report.review_packet_sha256" in source
    assert "source_identity_sha256: report.source_identity_sha256" in source
    assert "pdf_sha256: report.pdf_sha256" in source
    assert "unsupported_claims_permitted" in source


def test_production_api_registers_both_mid_report_routes():
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_report_routes" in source
    assert '("POST", "/assessment/mid-run/{run_id}/report/draft")' in source
    assert '("GET", "/assessment/mid-run/{run_id}/report/draft/pdf")' in source
    assert "MID_REPORT_ROUTES" in source
