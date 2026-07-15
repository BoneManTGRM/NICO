from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PAGE = ROOT / "apps" / "web" / "app" / "assessment" / "page.tsx"
STYLES = ROOT / "apps" / "web" / "app" / "assessment" / "assessment.module.css"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
OPERATIONS_GUARD = ROOT / "apps" / "web" / "app" / "OperationsPreloadGuard.tsx"
FULL_RUN_REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def _page() -> str:
    return PAGE.read_text(encoding="utf-8")


def test_unified_intake_has_exactly_three_assessment_tiers() -> None:
    source = _page()

    assert 'type AssessmentTier = "express" | "mid" | "full"' in source
    assert 'aria-label="Assessment type"' in source
    assert '(["express", "mid", "full"] as AssessmentTier[])' in source
    assert source.count('key={value}') == 1
    for label in ("Express", "Mid", "Full"):
        assert f'? "{label}"' in source or f': "{label}"' in source


def test_normal_intake_asks_only_for_simple_repository_scope_and_authorization() -> None:
    source = _page()
    rendered = source.split("return <main", 1)[1]

    for label in (
        "Repository owner/name or GitHub URL",
        "Client name, optional",
        "Project name, optional",
        "I confirm I own this target or have explicit permission to assess it.",
    ):
        assert label in rendered

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

    assert 'scopeId("customer", clientName, "default_customer")' in source
    assert 'scopeId("project", projectName, "default_project")' in source


def test_one_run_action_uses_asynchronous_exact_run_endpoints() -> None:
    source = _page()

    assert '"/assessment/express-run"' in source
    assert '"/assessment/mid-run"' in source
    assert '"/assessment/full-run"' in source
    assert 'assessment_mode: "express"' in source
    assert 'mode: "full"' in source
    assert "run_scanners: true" in source
    assert "build_reports: true" in source
    assert "create_final_review_request: true" in source
    assert "tools: FULL_TOOLS" in source


def test_every_tier_continues_the_exact_same_run_automatically() -> None:
    source = _page()

    assert "const POLL_INTERVAL_MS = 3000" in source
    assert "const MAX_POLL_ATTEMPTS = 240" in source
    assert "for (let attempt = 1; attempt <= MAX_POLL_ATTEMPTS; attempt += 1)" in source
    assert "/assessment/express-run/${encodeURIComponent(runId)}/status" in source
    assert "/assessment/mid-run/${encodeURIComponent(runId)}/status" in source
    assert "/assessment/full-run/${encodeURIComponent(runId)}/status" in source
    assert "await sleep(POLL_INTERVAL_MS)" in source
    assert "auto_continue: true" in source
    assert 'scan_id: current.scanner?.scan_id || current.scanner_evidence?.scan_id || ""' in source
    assert "The exact run ID is preserved" in source


def test_normal_assessment_flow_has_no_manual_status_or_continue_buttons() -> None:
    source = _page()
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
    source = _page()

    assert 'return "review_required"' in source
    assert "stopped at the required human-review gate" in source
    assert "did not approve findings" in source
    assert "/approval/request" not in source
    assert "/approved" not in source
    assert "/delivery/access" not in source
    assert "/delivery/redeem" not in source
    assert "X-NICO-Admin-Token" not in source


def test_progress_uses_backend_stages_elapsed_time_and_indeterminate_fallback() -> None:
    source = _page()
    css = STYLES.read_text(encoding="utf-8")

    assert "progress_percent?: number" in source
    assert "current_stage?: string" in source
    assert "Current stage" in source
    assert "Elapsed" in source
    assert "Status checks" in source
    assert "activeProgressItem" in source
    assert "DEFAULT_STAGE_PERCENT" in source
    assert "aria-valuenow" in source
    assert ".indeterminate" in css
    assert "@keyframes assessmentProgress" in css


def test_full_result_distinguishes_pending_unavailable_and_review_required() -> None:
    source = _page()

    for state in ("pending", "unavailable", "complete", "review_required", "timed_out"):
        assert state in source
    assert "Not scored" in source
    assert "Unavailable or limited evidence" in source
    assert "Missing or failed evidence remains disclosed" in source


def test_primary_navigation_has_one_run_job_entry_for_all_tiers() -> None:
    navigation = NAVIGATION.read_text(encoding="utf-8")
    primary = navigation.split("export const PRIMARY_SERVICES = [", 1)[1].split("] as const;", 1)[0]

    assert 'label: "Run a Job"' in primary
    assert 'href: "/assessment?tier=express#assessment"' in primary
    assert 'data-primary-service-count="3"' in navigation
    assert 'key: "express"' not in primary
    assert 'key: "mid"' not in primary
    assert 'key: "full"' not in primary
    assert 'label: "Express Assessment"' not in primary
    assert 'label: "Mid Assessment"' not in primary
    assert 'label: "Full Assessment"' not in primary
    assert 'if (pathname.startsWith("/assessment")) return "run-job"' in navigation


def test_legacy_full_run_route_defaults_to_unified_full_intake() -> None:
    redirect = FULL_RUN_REDIRECT.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'pathname !== "/full-run"' in redirect
    assert 'params.get("legacy") === "1"' in redirect
    assert 'params.get("review") === "1"' in redirect
    assert 'window.location.replace("/assessment?tier=full#assessment")' in redirect
    assert "<LegacyFullRunRedirect />" in layout


def test_operations_preload_guard_hides_failure_colored_placeholders_until_loaded() -> None:
    guard = OPERATIONS_GUARD.read_text(encoding="utf-8")
    layout = LAYOUT.read_text(encoding="utf-8")

    assert 'pathname !== "/operations"' in guard
    assert 'section.textContent?.includes("Operator authentication")' in guard
    assert 'authentication.textContent?.includes("Last loaded:")' in guard
    assert 'element.style.setProperty("display", "none", "important")' in guard
    assert 'PRELOAD_SECTION_ATTRIBUTE = "data-nico-preload-section-hidden"' in guard
    assert "section.hidden" not in guard
    assert "Operations evidence is not loaded" in guard
    assert "No readiness, release, storage, workload, incident, or alert state is inferred" in guard
    assert "<OperationsPreloadGuard />" in layout


def test_unified_assessment_layout_is_mobile_readable() -> None:
    css = STYLES.read_text(encoding="utf-8")

    assert "grid-template-columns: repeat(3, minmax(0, 1fr));" in css
    assert ".progressBar" in css
    assert ".timeline" in css
    assert "@media (max-width: 760px)" in css
    assert "grid-template-columns: 1fr;" in css
