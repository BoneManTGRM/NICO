from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "apps" / "web" / "app" / "assessment" / "AssessmentWorkspace.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "assessment.module.css"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
OPERATIONS_GUARD = ROOT / "apps" / "web" / "app" / "OperationsPreloadGuard.tsx"
FULL_RUN_REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def _workspace() -> str:
    return WORKSPACE.read_text(encoding="utf-8")


def test_public_intake_has_exactly_two_native_assessment_services() -> None:
    source = _workspace()
    rendered = source.split("return <main", 1)[1]

    assert 'type Service = "express" | "comprehensive"' in source
    assert 'data-assessment-service-count="2"' in rendered
    assert '(["express", "comprehensive"] as Service[])' in rendered
    assert 'aria-label="Assessment type"' in rendered
    assert '"/assessment/mid-run"' not in rendered
    assert '"/assessment/full-run"' not in rendered


def test_normal_intake_asks_only_for_simple_repository_scope_and_authorization() -> None:
    source = _workspace()
    rendered = source.split("return <main", 1)[1]

    for label in (
        "Repository owner/name or GitHub URL",
        "Client name, optional",
        "Project name, optional",
        "I confirm I own this target or have explicit permission to assess it.",
    ):
        assert label in source

    for forbidden in (
        "NICO admin token",
        "Customer ID",
        "Project ID",
        "Mid run ID",
        "Run scanner worker",
        "Build report package",
        "Request final review",
    ):
        assert forbidden not in rendered

    assert 'scopeId("customer", client, "default_customer")' in source
    assert 'scopeId("project", project, "default_project")' in source
    assert 'const [repository, setRepository] = useState("")' in source


def test_one_run_action_uses_only_native_express_and_comprehensive_start_endpoints() -> None:
    source = _workspace()
    run_body = source.split("async function run()", 1)[1].split("async function copyMarkdown()", 1)[0]

    assert '"/assessment/express-run"' in run_body
    assert '"/assessment/comprehensive-intake"' in run_body
    assert 'assessment_mode: "express"' in run_body
    assert '"/assessment/mid-run"' not in run_body
    assert '"/assessment/full-run"' not in run_body


def test_each_service_continues_the_exact_same_run_automatically() -> None:
    source = _workspace()
    continuation = source.split("async function continueRun(", 1)[1].split("async function run()", 1)[0]

    assert "for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1)" in continuation
    assert 'const runId = String(current.run_id || "")' in continuation
    assert "/assessment/express-run/${encodeURIComponent(runId)}/status" in continuation
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in continuation
    assert 'JSON.stringify({max_stages: 1})' in continuation
    assert '"/assessment/express-run"' not in continuation
    assert '"/assessment/comprehensive-intake"' not in continuation
    assert "await wait(POLL_INTERVAL_MS)" in continuation


def test_normal_assessment_flow_has_no_manual_status_approval_or_delivery_buttons() -> None:
    source = _workspace()
    rendered = source.split("return <main", 1)[1]

    for forbidden in (
        "Check Mid status",
        "Refresh full-run status",
        "Continue to report and human review",
        "Load exact review packet",
        "Request Mid approval",
        "Create private delivery link",
    ):
        assert forbidden not in rendered


def test_autonomous_flow_stops_at_human_review_without_approval_or_delivery_mutation() -> None:
    source = _workspace()

    assert 'value === "review_required"' in source
    assert "stopped at the required human-review gate" in source
    assert "did not approve findings or authorize client delivery" in source
    assert "/approval/request" not in source
    assert "/approved" not in source
    assert "/delivery/access" not in source
    assert "/delivery/redeem" not in source
    assert "X-NICO-Admin-Token" not in source


def test_progress_uses_backend_stage_progress_elapsed_time_and_exact_run_identity() -> None:
    source = _workspace()
    css = STYLES.read_text(encoding="utf-8")

    assert "progress_percent?: number" in source
    assert "current_stage?: string" in source
    assert "Current stage" in source
    assert "Elapsed" in source
    assert "Status checks" in source
    assert "aria-valuenow" in source
    assert "result?.run_id" in source
    assert ".progressBar" in css
    assert ".timeline" in css


def test_result_distinguishes_pending_unavailable_and_review_required() -> None:
    source = _workspace()

    for state in ("pending", "unavailable", "complete", "review_required", "timed_out"):
        assert state in source
    assert "Not scored" in source
    assert "Unavailable or limited evidence" in source
    assert "Discloses missing or failed evidence" in source


def test_primary_navigation_uses_one_assessment_entry_and_normalizes_legacy_tiers() -> None:
    navigation = NAVIGATION.read_text(encoding="utf-8")
    primary = navigation.split("export const PRIMARY_SERVICES = [", 1)[1].split("] as const;", 1)[0]

    assert 'type AssessmentMode = "express" | "comprehensive"' in navigation
    assert 'label: "Run a Job"' in primary
    assert 'href: "/assessment?tier=express#assessment"' in primary
    assert 'data-primary-service-count="3"' in navigation
    assert '["comprehensive", "mid", "full", "deep"]' in navigation
    assert '"/es/assessment?tier=express#assessment"' in navigation
    assert 'if (pathname.startsWith("/assessment") || pathname.startsWith("/es/assessment")) return "run-job"' in navigation


def test_legacy_full_run_route_defaults_to_comprehensive_intake() -> None:
    redirect = FULL_RUN_REDIRECT.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'pathname !== "/full-run"' in redirect
    assert 'params.get("legacy") === "1"' in redirect
    assert 'params.get("review") === "1"' in redirect
    assert 'window.location.replace("/assessment?tier=comprehensive#assessment")' in redirect
    assert "<LegacyFullRunRedirect />" in layout


def test_operations_preload_guard_hides_failure_colored_placeholders_until_loaded() -> None:
    guard = OPERATIONS_GUARD.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'pathname !== "/operations"' in guard
    assert 'section.textContent?.includes("Operator authentication")' in guard
    assert 'element.style.setProperty("display", "none", "important")' in guard
    assert 'PRELOAD_SECTION_ATTRIBUTE = "data-nico-preload-section-hidden"' in guard
    assert "<OperationsPreloadGuard />" in layout


def test_unified_assessment_layout_is_mobile_readable() -> None:
    css = STYLES.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(2, minmax(0, 1fr));" in css
    assert ".progressBar" in css
    assert ".timeline" in css
    assert "@media (max-width: 760px)" in css
    assert "grid-template-columns: 1fr;" in css
