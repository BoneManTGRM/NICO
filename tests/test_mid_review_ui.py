from __future__ import annotations

from pathlib import Path


PAGE = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "mid-review" / "page.tsx"
LAYOUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "layout.tsx"
PRODUCTION = Path(__file__).resolve().parents[1] / "nico" / "api" / "production.py"


def test_navigation_exposes_dedicated_mid_review_screen():
    layout = LAYOUT.read_text(encoding="utf-8")

    assert '<a href="/mid-review">Mid Review</a>' in layout
    assert "admin-authenticated review-by-exception packet" in layout


def test_review_screen_requires_exact_run_scope_and_admin_token():
    source = PAGE.read_text(encoding="utf-8")

    assert "Mid run ID" in source
    assert "Customer ID" in source
    assert "Project ID" in source
    assert "NICO admin token" in source
    assert 'type="password"' in source
    assert 'headers: {"X-NICO-Admin-Token": adminToken}' in source
    assert "customer_id: customerId.trim()" in source
    assert "project_id: projectId.trim()" in source


def test_review_screen_calls_only_review_exception_endpoint():
    source = PAGE.read_text(encoding="utf-8")

    assert "/assessment/mid-run/${encodeURIComponent(runId.trim())}/review-exceptions" in source
    assert "Load review exceptions" in source
    assert "/approve" not in source
    assert "/reject" not in source
    assert "approval_controls_note" in source


def test_review_screen_surfaces_required_summary_counts():
    source = PAGE.read_text(encoding="utf-8")

    assert "Verified sections" in source
    assert "Items requiring review" in source
    assert "Unavailable sources" in source
    assert "Unsupported claims permitted" in source
    assert "Critical items" in source
    assert "High items" in source
    assert "Score-changing items" in source
    assert "Inference items" in source


def test_exceptions_are_expanded_and_verified_sections_are_collapsed():
    source = PAGE.read_text(encoding="utf-8")

    assert '<details className="result-card" open' in source
    assert "Human review queue" in source
    assert "Verified automatically — evidence available" in source
    assert "packet.verified_sections?.length" in source
    assert "packet.exceptions?.map" in source


def test_review_packet_identity_is_visible_without_admin_token_echo():
    source = PAGE.read_text(encoding="utf-8")
    rendered = source.split("return <main", 1)[1]

    assert "review_packet_sha256" in source
    assert "snapshot_commit_sha" in source
    assert "packet_version" in source
    assert "{adminToken}" not in rendered
    assert "JSON.stringify({" in source


def test_production_api_registers_review_route():
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_review_routes" in source
    assert '("GET", "/assessment/mid-run/{run_id}/review-exceptions")' in source
    assert "MID_REVIEW_ROUTES" in source
