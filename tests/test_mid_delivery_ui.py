from __future__ import annotations

from pathlib import Path


CLIENT = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "mid-delivery" / "page.tsx"
ADMIN = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "mid-delivery-admin" / "page.tsx"
LAYOUT = Path(__file__).resolve().parents[1] / "apps" / "web" / "app" / "layout.tsx"
PRODUCTION = Path(__file__).resolve().parents[1] / "nico" / "api" / "production.py"


def test_navigation_places_delivery_after_approval():
    layout = LAYOUT.read_text(encoding="utf-8")

    assert '<a href="/mid-approval">Mid Approval</a>' in layout
    assert '<a href="/mid-delivery-admin">Mid Delivery</a>' in layout
    assert layout.index('href="/mid-approval"') < layout.index('href="/mid-delivery-admin"')
    assert "expiring and download-limited link" in layout
    assert "Client downloads require acknowledgement" in layout


def test_admin_page_requires_exact_scope_and_admin_identity():
    source = ADMIN.read_text(encoding="utf-8")

    assert "Mid run ID" in source
    assert "Customer ID" in source
    assert "Project ID" in source
    assert "NICO admin token" in source
    assert 'type="password"' in source
    assert "Recipient label" in source
    assert "Created by" in source
    assert '"X-NICO-Admin-Token": adminToken' in source


def test_admin_page_creates_lists_revokes_and_displays_receipts():
    source = ADMIN.read_text(encoding="utf-8")

    assert "/delivery/access" in source
    assert "/delivery/receipts" in source
    assert "/revoke" in source
    assert "Create private delivery link" in source
    assert "Refresh grants and receipts" in source
    assert "Revoke access" in source
    assert "Delivery receipts" in source
    assert "Acknowledgement SHA-256" in source


def test_raw_token_is_shown_only_in_one_time_admin_output_not_access_cards():
    source = ADMIN.read_text(encoding="utf-8")
    one_time = source.split("One-time token output", 1)[1].split("Access grants", 1)[0]
    grants = source.split("Access grants", 1)[1]

    assert "rawToken" in one_time
    assert "privateLink" in one_time
    assert "Shown once" in one_time
    assert "rawToken" not in grants
    assert "token_fingerprint" in grants


def test_client_page_reads_fragment_token_and_never_places_it_in_url_query():
    source = CLIENT.read_text(encoding="utf-8")

    assert "window.location.hash" in source
    assert 'params.get("token")' in source
    assert "/delivery/inspect" in source
    assert "/delivery/redeem" in source
    assert "?token=" not in source
    assert "Authorization" not in source


def test_client_page_requires_acknowledgement_and_named_recipient():
    source = CLIENT.read_text(encoding="utf-8")

    assert "Recipient name" in source
    assert "I acknowledge receipt of this NICO Mid Assessment" in source
    assert "acknowledged: true" in source
    assert "recipientName.trim().length < 2" in source
    assert "Download approved Mid PDF" in source
    assert "Download receipt recorded" in source


def test_client_verifies_all_approved_artifact_headers_before_saving():
    source = CLIENT.read_text(encoding="utf-8")

    assert 'response.headers.get("X-NICO-Report-ID")' in source
    assert 'response.headers.get("X-NICO-PDF-SHA256")' in source
    assert 'response.headers.get("X-NICO-Approval-ID")' in source
    assert 'response.headers.get("X-NICO-Approval-Identity-SHA256")' in source
    assert 'response.headers.get("X-NICO-Review-Packet-SHA256")' in source
    assert 'response.headers.get("X-NICO-Delivery-Receipt-ID")' in source
    assert 'response.headers.get("X-NICO-Delivery-Receipt-SHA256")' in source
    assert "The downloaded PDF did not match the approved delivery identity" in source
    assert 'blob.type !== "application/pdf"' in source


def test_client_identity_display_does_not_render_raw_token():
    source = CLIENT.read_text(encoding="utf-8")
    identity = source.split("Integrity identity", 1)[1].split("</details>", 1)[0]

    assert "token" not in identity.lower()
    assert "pdf_sha256" in identity
    assert "approval_identity_sha256" in identity
    assert "review_packet_sha256" in identity
    assert "snapshot_commit_sha" in identity


def test_production_registers_complete_mid_delivery_route_group():
    source = PRODUCTION.read_text(encoding="utf-8")

    assert "register_mid_delivery_routes" in source
    assert "MID_DELIVERY_ROUTES" in source
    routes = [
        '("POST", "/assessment/mid-run/{run_id}/delivery/access")',
        '("GET", "/assessment/mid-run/{run_id}/delivery/access")',
        '("GET", "/assessment/mid-run/{run_id}/delivery/receipts")',
        '("POST", "/assessment/mid-run/delivery/access/{access_id}/revoke")',
        '("POST", "/assessment/mid-run/delivery/inspect")',
        '("POST", "/assessment/mid-run/delivery/redeem")',
    ]
    for route in routes:
        assert route in source
