from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "mid-review" / "page.tsx"
CONTEXT = ROOT / "apps" / "web" / "app" / "MidWorkspaceContext.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
PRODUCTION = ROOT / "nico" / "api" / "production.py"


def test_workspace_exposes_dedicated_mid_review_stage():
    context = CONTEXT.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'path: "/mid-review"' in context
    assert 'path: "/assessment?tier=mid#assessment"' in context
    assert 'href="/assessment?tier=express#assessment"' in layout
    assert "Mid and Full continue through repository evidence" in layout
    assert "stop at required human review" in layout


def test_review_screen_uses_shared_exact_run_scope_and_admin_token():
    source = PAGE.read_text(encoding="utf-8")
    context = CONTEXT.read_text(encoding="utf-8")

    for label in ("Mid run ID", "Customer ID", "Project ID", "NICO admin token"):
        assert label in context
    assert 'type="password"' in context
    assert "useMidWorkspace" in source
    assert "MidIdentityPanel" in source
    assert 'MidStageNavigation current="review"' in source
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
    identity_block = source.split("JSON.stringify({", 1)[1].split("}, null, 2)", 1)[0]

    assert "review_packet_sha256" in identity_block
    assert "snapshot_commit_sha" in identity_block
    assert "packet_version" in identity_block
    assert "adminToken" not in identity_block
    assert "admin_token" not in identity_block


def test_production_api_registers_review_route():
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_review_routes" in source
    assert '("GET", "/assessment/mid-run/{run_id}/review-exceptions")' in source
    assert "MID_REVIEW_ROUTES" in source
