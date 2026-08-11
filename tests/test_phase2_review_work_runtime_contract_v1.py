from __future__ import annotations

from pathlib import Path


RUNTIME = Path("nico/comprehensive_review_work_runtime_v1.py").read_text(encoding="utf-8")
PROXY = Path("apps/web/app/api/nico/[...path]/route.ts").read_text(encoding="utf-8")
PANEL = Path("apps/web/app/operations/reviewer-queue/ReviewWorkPanel.tsx").read_text(encoding="utf-8")
PAGE = Path("apps/web/app/operations/reviewer-queue/page.tsx").read_text(encoding="utf-8")
SPANISH_INSTALLER = Path("nico/spanish_cross_format_score_parity_v1.py").read_text(encoding="utf-8")


def test_protected_review_work_routes_are_installed_without_new_product_or_report() -> None:
    assert 'GET_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"' in RUNTIME
    assert 'POST_ROUTE = "/assessment/comprehensive-run/{run_id}/review-work"' in RUNTIME
    assert "routes_module._authorize_review(x_nico_admin_token)" in RUNTIME
    assert "service.review_work(run_id, payload)" in RUNTIME
    assert "if _canonical_scanner_register_present(record):" in RUNTIME
    assert "assert_ready_for_approval(_review_action_record(record))" in RUNTIME
    assert "legacy_precanonical_approval_compatibility_preserved" in RUNTIME
    assert '"candidate_truth_source": "canonical_terminal_comprehensive_report_json"' in RUNTIME
    assert '"client_delivery_allowed": False' in RUNTIME


def test_web_proxy_forwards_admin_authority_only_to_protected_review_work() -> None:
    assert "const COMPREHENSIVE_REVIEW_WORK" in PROXY
    assert '(method === "GET" || method === "POST") && COMPREHENSIVE_REVIEW_WORK.test(path)' in PROXY
    assert "protectedReviewRoute(request.method, apiPath)" in PROXY
    assert 'request.headers.get("x-nico-admin-token")' in PROXY
    assert 'headers.set("X-NICO-Admin-Token", adminToken)' in PROXY


def test_reviewer_workspace_exposes_bilingual_human_controls_and_no_delivery_bypass() -> None:
    assert 'type Locale = "en" | "es-MX"' in PANEL
    assert 'data-phase2-review-work="true"' in PANEL
    assert 'data-client-delivery-allowed="false"' in PANEL
    for action in (
        "assign",
        "disposition_candidate",
        "disposition_group",
        "quality_control",
        "request_evidence",
        "resolve_evidence_request",
        "stakeholder_evidence",
        "start_session",
        "stop_session",
        "complete_empirical_study",
    ):
        assert f'"{action}"' in PANEL
    assert "ReviewWorkPanel" in PAGE
    assert "ReviewerQueue" in PAGE
    assert "localStorage" not in PANEL
    assert "sessionStorage" not in PANEL


def test_phase2_review_runtime_is_loaded_by_existing_nico_install_chain() -> None:
    assert "install_comprehensive_review_work_runtime_v1" in SPANISH_INSTALLER
    assert "phase2_review_work" in SPANISH_INSTALLER
