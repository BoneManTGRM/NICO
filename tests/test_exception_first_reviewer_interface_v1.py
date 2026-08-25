import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMPONENT = ROOT / "apps/web/app/operations/reviewer-queue/ReviewerQueue.tsx"
PAGE = ROOT / "apps/web/app/operations/reviewer-queue/page.tsx"
FINAL_REVIEW_PAGE = ROOT / "apps/web/app/operations/final-review/page.tsx"
FINAL_REVIEW_COMPONENT = ROOT / "apps/web/app/operations/final-review/ComprehensiveFinalReviewWorkspace.tsx"
PROXY = ROOT / "apps/web/app/api/nico/[...path]/route.ts"
API_ROUTES = ROOT / "nico/comprehensive_api_routes.py"
STATUS = ROOT / "docs/NICO_COMPLETION_PROGRAM_STATUS.md"
STATE = ROOT / "docs/client-ready-report-accuracy-observation.json"


def source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_authoritative_state_closes_wp1_and_declares_exact_next_phase2_package() -> None:
    status = source(STATUS)
    state = json.loads(source(STATE))

    assert state["program_phase"] == 2
    assert state["work_package"] == "exception_first_reviewer_interface"
    assert state["dependency_state"] == "completed"
    assert state["state"] == "post_merge_verified"
    assert state["verified_release_sha"] == state["implementation"]["merge_sha"]
    assert state["current_main_sha"] == state["verified_release_sha"]
    assert state["phase2_work_package_1_definition_of_done"]["work_package"] == "complete"
    assert state["phase2_work_package_1_definition_of_done"]["required_exact_head_and_production_checks_passed"] is True
    assert state["next_work_package"] == "expandable_deterministic_clusters"
    assert state["next_work_package_state"] == "declared_not_started"
    assert state["next_work_package_scope"]["read_only"] is True
    assert state["next_work_package_scope"]["candidate_or_group_disposition_controls"] is False
    assert "PHASE 2 WORK PACKAGE 1: COMPLETE" in status
    assert "`expandable_deterministic_clusters`" in status
    assert "`declared_not_started`" in status


def test_queue_consumes_protected_canonical_phase1_projection() -> None:
    component = source(COMPONENT)
    proxy = source(PROXY)
    api_routes = source(API_ROUTES)
    assert "candidate_register" in component
    assert "technical_triage" in component
    assert "human_review_work_units" in component
    assert "/api/nico/assessment/comprehensive-run/" in component
    assert "/review-queue" in component
    assert '"X-NICO-Admin-Token"' in component
    assert 'type="password"' in component
    assert "COMPREHENSIVE_REVIEW_QUEUE" in proxy
    assert "protectedReviewRoute" in proxy
    assert 'headers.set("X-NICO-Admin-Token", adminToken)' in proxy
    assert '@app.get("/assessment/comprehensive-run/{run_id}/review-queue")' in api_routes
    assert "_authorize_review(x_nico_admin_token)" in api_routes
    assert "canonical_scanner_finding_register" in api_routes
    assert "localStorage" not in component
    assert "sessionStorage" not in component


def test_queue_is_exception_first_and_preserves_every_candidate_identity() -> None:
    component = source(COMPONENT)
    assert "const units = [...individualUnits, ...groupedUnits]" in component
    assert "individualUnits.map" in component
    assert "groupedUnits.map" in component
    assert "unit.candidates.map" in component
    assert "queuedIds.length !== findings.length" in component
    assert "new Set(queuedIds).size !== findings.length" in component
    assert "expectedWorkUnits !== units.length" in component
    assert "payload.human_review_work_units" in component
    assert "payload.candidate_count" in component
    assert "Queue integrity check failed closed" in component


def test_package_remains_read_only_and_does_not_absorb_later_work() -> None:
    component = source(COMPONENT)
    assert 'data-review-queue-contract="exception-first-v1"' in component
    assert 'data-human-disposition-controls="absent"' in component
    assert 'data-client-delivery-authorization="absent"' in component
    assert "No candidate disposition, reviewer identity, risk acceptance, approval, score change" in component
    assert 'method: "POST"' not in component
    assert "/review-queue" in component
    assert "reviewer_workload_timer" not in component
    assert "quality_control_sampling" not in component
    assert "setAdminToken(\"\")" in component


def test_internal_final_review_exposes_queue_without_changing_client_report() -> None:
    page = source(PAGE)
    final_review_page = source(FINAL_REVIEW_PAGE)
    final_review_component = source(FINAL_REVIEW_COMPONENT)
    component = source(COMPONENT)
    assert "ReviewerQueue" in page
    assert "ComprehensiveFinalReviewWorkspace" in final_review_page
    assert "/operations/reviewer-queue?run_id=${encodeURIComponent(runId.trim())}" in final_review_component
    assert "&lang=${encodeURIComponent(locale)}" in final_review_component
    assert "report_package" not in component
    assert "pdf_base64" not in component
