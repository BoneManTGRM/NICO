from __future__ import annotations

from pathlib import Path


def test_direct_intake_display_metadata_reaches_controller(monkeypatch) -> None:
    import nico.comprehensive_api_routes as routes
    import nico.comprehensive_intake_display_metadata_v2 as patch

    original_intake = routes._intake
    original_installed = patch._INSTALLED
    seen: dict[str, object] = {}

    class FakeController:
        def start(self, payload):
            seen.update(payload)
            return {
                "status": "ready",
                "run_id": payload["run_id"],
                "customer_id": payload["customer_id"],
                "project_id": payload["project_id"],
                "human_review_required": True,
                "client_delivery_allowed": False,
            }

    try:
        patch._INSTALLED = False
        monkeypatch.setattr(
            routes,
            "capture_repository_snapshot",
            lambda payload: {
                "status": "attached",
                "commit_sha": "a" * 40,
                "repository": payload["repository"],
            },
        )
        monkeypatch.setattr(routes, "expected_commit_sha", lambda payload: "")
        monkeypatch.setattr(routes, "normalize_repository", lambda value: str(value))
        monkeypatch.setattr(routes, "_controller", lambda request: FakeController())
        monkeypatch.setattr(
            routes,
            "_with_runtime_truth",
            lambda request, response: response,
        )

        state = patch.install_comprehensive_intake_display_metadata_v2()
        assert state["bound"] is True
        assert state["direct_controller_payload"] is True
        assert state["contextvar_required_for_display_metadata"] is False

        response = routes._intake(
            object(),
            {
                "repository": "BoneManTGRM/NICO",
                "client_name": "  Intake Proof Client  ",
                "project_name": " Intake Proof Project ",
                "customer_id": "default_customer",
                "project_id": "default_project",
                "assessment_depth": "strategic",
                "report_language": "en",
                "human_evidence": {
                    "stakeholder_context": {
                        "evidence": {
                            "access_method": ["GitHub HTTPS/API - read-only"],
                            "primary_technical_contact": ["Proof Contact"],
                            "authorized_scope": ["full repository - read-only"],
                        }
                    }
                },
                "authorized": True,
                "authorization_confirmed": True,
            },
        )

        assert seen["client_name"] == "Intake Proof Client"
        assert seen["project_name"] == "Intake Proof Project"
        assert seen["customer_id"] == "default_customer"
        assert seen["project_id"] == "default_project"
        assert seen["human_evidence"]
        assert response["client_name"] == "Intake Proof Client"
        assert response["project_name"] == "Intake Proof Project"
    finally:
        routes._intake = original_intake
        patch._INSTALLED = original_installed


def test_final_worker_installs_sparse_reflow_before_freezing_pdf() -> None:
    source = Path("nico/api/final_report_worker_bootstrap.py").read_text(encoding="utf-8")
    assert "install_comprehensive_final_worker_pdf_reflow_v1" in source
    assert "FINAL_WORKER_PDF_REFLOW = install_comprehensive_final_worker_pdf_reflow_v1()" in source
    assert '"reflow_before_final_navigation"' in source
    assert '"toc_page_labels_and_bookmarks_rebuilt_after_reflow"' in source
    assert source.index("FINAL_WORKER_PDF_REFLOW =") < source.index("CANONICAL_TRUTH_HASH_COMPAT =")


def test_markdown_bridge_waits_for_terminal_report_before_prefetch() -> None:
    source = Path("apps/web/app/AssessmentMarkdownCopyBridge.tsx").read_text(encoding="utf-8")
    assert 'actions.getAttribute("data-assessment-report-ready") !== "true"' in source
    assert "enabledCopyButton(actions)" in source
    assert "Markdown ready. Click Copy Markdown." in source
    assert "const markdown = entry.markdown || await loadMarkdown(entry)" not in source


def test_pdf_bridge_uses_one_user_gesture_dispatch_and_visible_status() -> None:
    source = Path("apps/web/app/AssessmentReviewPdfDownload.tsx").read_text(encoding="utf-8")
    assert "window.open(" not in source
    assert source.count("link.click();") == 1
    assert "PDF requested. Check the new tab or your downloads." in source
    assert "data-nico-review-pdf-action-status" in source
