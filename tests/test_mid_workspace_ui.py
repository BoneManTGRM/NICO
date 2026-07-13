from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTEXT = ROOT / "apps" / "web" / "app" / "MidWorkspaceContext.tsx"
WORKSPACE = ROOT / "apps" / "web" / "app" / "mid-assessment" / "page.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
STAGE_PAGES = {
    "review": ROOT / "apps" / "web" / "app" / "mid-review" / "page.tsx",
    "report": ROOT / "apps" / "web" / "app" / "mid-report" / "page.tsx",
    "approval": ROOT / "apps" / "web" / "app" / "mid-approval" / "page.tsx",
    "delivery": ROOT / "apps" / "web" / "app" / "mid-delivery-admin" / "page.tsx",
}


def test_mid_primary_navigation_opens_one_workspace() -> None:
    navigation = NAVIGATION.read_text(encoding="utf-8")

    assert 'label: "Mid Assessment"' in navigation
    assert 'href: "/mid-assessment"' in navigation
    for legacy in (
        '{label: "Mid Review", href: "/mid-review"}',
        '{label: "Mid Report", href: "/mid-report"}',
        '{label: "Mid Approval", href: "/mid-approval"}',
        '{label: "Mid Delivery", href: "/mid-delivery-admin"}',
    ):
        assert legacy not in navigation


def test_workspace_stage_sequence_and_existing_routes_are_preserved() -> None:
    context = CONTEXT.read_text(encoding="utf-8")
    workspace = WORKSPACE.read_text(encoding="utf-8")

    ordered = [
        ('key: "start"', '/?assessment=mid#assessment'),
        ('key: "review"', '/mid-review'),
        ('key: "report"', '/mid-report'),
        ('key: "approval"', '/mid-approval'),
        ('key: "delivery"', '/mid-delivery-admin'),
    ]
    positions = []
    for key, route in ordered:
        positions.append(context.index(key))
        assert route in context
    assert positions == sorted(positions)
    assert "Start → Review → Report → Approval → Delivery" in context
    assert "Start → Review → Report → Approval → Delivery" in workspace
    assert 'href="/?assessment=mid#assessment"' in workspace


def test_workspace_admin_token_and_reviewer_are_memory_only() -> None:
    context = CONTEXT.read_text(encoding="utf-8")

    assert 'const [adminToken, setAdminToken] = useState("")' in context
    assert 'const [reviewer, setReviewer] = useState("")' in context
    assert "localStorage" not in context
    assert "sessionStorage.setItem(ACTIVE_RUN_KEY" in context
    assert "sessionStorage.setItem(\"admin" not in context
    assert "sessionStorage.setItem(\"reviewer" not in context
    assert "params.set(\"run_id\"" in context
    assert "params.set(\"customer_id\"" in context
    assert "params.set(\"project_id\"" in context
    assert "params.set(\"admin" not in context
    assert "params.set(\"reviewer" not in context
    assert "never written to the URL or browser storage" in context


def test_passive_workspace_refresh_uses_only_read_endpoints() -> None:
    source = WORKSPACE.read_text(encoding="utf-8")
    refresh_block = source.split("async function refreshStatus()", 1)[1].split("return <main", 1)[0]

    assert "/review-exceptions?" in refresh_block
    assert "/approval?" in refresh_block
    assert "/delivery/access?" in refresh_block
    assert "/delivery/receipts?" in refresh_block
    assert 'method: "POST"' not in refresh_block
    assert "/report/draft" not in refresh_block
    assert "/approval/request" not in refresh_block
    assert "No report, approval, grant, or delivery mutation was performed" in refresh_block


def test_direct_mid_stage_pages_consume_shared_workspace_identity() -> None:
    for stage, path in STAGE_PAGES.items():
        source = path.read_text(encoding="utf-8")
        assert "useMidWorkspace" in source, stage
        assert "MidIdentityPanel" in source, stage
        assert f'<MidStageNavigation current="{stage}" />' in source, stage
        assert "const [runId, setRunId]" not in source, stage
        assert "const [adminToken, setAdminToken]" not in source, stage


def test_root_layout_keeps_provider_alive_across_mid_routes() -> None:
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'import {MidWorkspaceProvider} from "./MidWorkspaceContext";' in layout
    assert layout.index("<MidWorkspaceProvider>") < layout.index("{children}")
    assert layout.index("{children}") < layout.index("</MidWorkspaceProvider>")
    assert 'href="/mid-assessment"' in layout
    assert "does not create a client delivery link" in layout
    assert "Client downloads require acknowledgement" in layout
