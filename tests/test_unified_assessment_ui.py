from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ASSESSMENT = ROOT / "apps" / "web" / "app" / "assessment"
WORKSPACE = ASSESSMENT / "AssessmentWorkspace.tsx"
HOOK = ASSESSMENT / "useAssessmentRun.ts"
MODEL = ASSESSMENT / "assessmentModel.ts"
COPY = ASSESSMENT / "assessmentCopy.ts"
TYPES = ASSESSMENT / "assessmentTypes.ts"
STYLES = ASSESSMENT / "assessment.module.css"
NAVIGATION = ROOT / "apps" / "web" / "app" / "PrimaryNavigation.tsx"
OPERATIONS_GUARD = ROOT / "apps" / "web" / "app" / "OperationsPreloadGuard.tsx"
FULL_RUN_REDIRECT = ROOT / "apps" / "web" / "app" / "LegacyFullRunRedirect.tsx"
LAYOUT = ROOT / "apps" / "web" / "app" / "layout.tsx"


def workspace_source() -> str:
    return WORKSPACE.read_text(encoding="utf-8")


def assessment_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in (WORKSPACE, HOOK, MODEL, COPY, TYPES))


def test_public_intake_has_one_canonical_assessment() -> None:
    source = workspace_source()
    rendered = source.split("return <main", 1)[1]

    assert 'data-assessment-service-count="1"' in rendered
    assert 'data-canonical-assessment="strategic"' in rendered
    assert 'data-customer-facing-assessment="comprehensive"' in rendered
    assert 'aria-label="Assessment type"' not in rendered
    assert '"/assessment/mid-run"' not in rendered
    assert '"/assessment/full-run"' not in rendered


def test_normal_intake_asks_only_for_simple_repository_scope_and_authorization() -> None:
    source = assessment_source()
    rendered = workspace_source().split("return <main", 1)[1]

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


def test_one_run_action_uses_only_comprehensive_start_endpoint() -> None:
    source = HOOK.read_text(encoding="utf-8")
    run_body = source.split("async function run()", 1)[1]

    assert "requestWithRetry(" in run_body
    assert '"/assessment/comprehensive-intake"' in run_body
    assert 'assessment_depth: "strategic"' in run_body
    assert '"/assessment/express-run"' not in run_body
    assert '"/assessment/mid-run"' not in run_body
    assert '"/assessment/full-run"' not in run_body


def test_comprehensive_continues_the_exact_same_run_automatically() -> None:
    source = HOOK.read_text(encoding="utf-8")
    continuation = source.split("async function continueRun(", 1)[1].split("async function run()", 1)[0]

    assert "for (let count = 1; count <= MAX_POLL_ATTEMPTS; count += 1)" in continuation
    assert 'const runId = String(current.run_id || "")' in continuation
    assert "/assessment/comprehensive-run/${encodeURIComponent(runId)}/continue" in continuation
    assert 'JSON.stringify({max_stages: 1})' in continuation
    assert '"/assessment/comprehensive-intake"' not in continuation
    assert "await wait(POLL_INTERVAL_MS)" in continuation


def test_normal_assessment_flow_has_no_manual_status_approval_or_delivery_buttons() -> None:
    rendered = workspace_source().split("return <main", 1)[1]
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
    source = assessment_source()

    assert 'value === "review_required"' in source or 'value === "review_required"' in MODEL.read_text(encoding="utf-8")
    assert "stopped at the required human-review gate" in source
    assert "The final report is complete" in source
    assert "before client delivery" in source
    assert "no separate report rewrite is required" in source
    assert "/approval/request" not in source
    assert "/approved" not in source
    assert "/delivery/access" not in source
    assert "/delivery/redeem" not in source
    assert "X-NICO-Admin-Token" not in source


def test_progress_uses_backend_stage_progress_elapsed_time_and_exact_run_identity() -> None:
    source = assessment_source()
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
