from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = ROOT / "scripts/mobile_restart_live_acceptance_v3.py"
WEBKIT = ROOT / "scripts/mobile_restart_live_acceptance_v4.py"
CHROMIUM_PDF = ROOT / "scripts/mobile_restart_live_acceptance_v5.py"
WEBKIT_PDF = ROOT / "scripts/mobile_restart_live_acceptance_v6.py"
PDF_PROOF = ROOT / "scripts/mobile_pdf_download_action_proof_v1.py"
MOBILE_WORKFLOW = ROOT / ".github/workflows/mobile-restart-production-proof.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-webkit-paint-proof.yml"


def test_mobile_proof_is_a_fail_closed_existing_run_consumer() -> None:
    source = CHROMIUM.read_text(encoding="utf-8")
    recovery = (ROOT / "scripts/mobile_restart_live_acceptance_v1.py").read_text(encoding="utf-8")

    assert 'VERSION = "nico.mobile_restart_live_acceptance.single_dispatch.v3"' in source
    assert "_ORIGINAL_RUN_PROOF(SingleDispatchBrowser(browser), args)" in source
    assert 'result["start_dispatch"] = "not_dispatched_existing_run"' in source
    assert 'result["start_dispatch_retry_absent"] = True' in source
    assert "_require_existing_source_args(args)" in source
    assert 'parser.add_argument("--source-proof", type=Path, required=True)' in recovery
    assert 'parser.add_argument("--source-workflow-run-id", required=True)' in recovery
    assert 'parser.add_argument("--source-workflow-run-attempt", required=True)' in recovery
    assert 'parser.add_argument("--observation-seconds", type=float, default=90.0)' in recovery
    assert 'page.route("**/*", mutation_guard)' in recovery
    assert 'parsed.path == "/api/nico/assessment/comprehensive-intake"' in recovery
    assert 'parsed.path.endswith("/continue")' in recovery
    assert "_prove_visibility_hidden_visible(" in recovery
    assert "def _mobile_terminal_layout" in recovery
    assert "def _mobile_locale_round_trip" in recovery
    assert '"mobile_locale_switch_control_verified": True' in recovery
    assert '"terminal_touch_targets_verified": True' in recovery
    assert '"clean_context_reopen_verified": True' in recovery
    assert '"browser_context_count": 2' in recovery
    assert 'localized-report/{report_language}' in recovery
    assert '"legacy_markdown_get_count": len(legacy_markdown_gets)' in recovery
    assert '"markdown_action_success_count": len(markdown_proofs)' in recovery
    assert '"markdown_network_bounded": True' in recovery
    assert 'legacy_markdown_path = status_path + "/report/markdown"' in recovery


def test_webkit_proof_reuses_the_same_single_dispatch_boundary() -> None:
    source = WEBKIT.read_text(encoding="utf-8")

    assert 'VERSION = "nico.mobile_restart_live_acceptance.webkit_single_dispatch.v4"' in source
    assert "webkit.recovery.run_proof = single_dispatch.run_proof" in source
    assert "return webkit.main(argv)" in source


def test_pdf_download_wrappers_preserve_single_dispatch_and_add_real_ui_download() -> None:
    chromium = CHROMIUM_PDF.read_text(encoding="utf-8")
    webkit = WEBKIT_PDF.read_text(encoding="utf-8")
    proof = PDF_PROOF.read_text(encoding="utf-8")

    assert "import mobile_restart_live_acceptance_v3 as single_dispatch" in chromium
    assert "install_ui_pdf_download_proof(recovery)" in chromium
    assert "return single_dispatch.main(argv)" in chromium
    assert "import mobile_restart_live_acceptance_v4 as webkit_single_dispatch" in webkit
    assert "install_ui_pdf_download_proof(recovery)" in webkit
    assert "return webkit_single_dispatch.main(argv)" in webkit
    assert 'page.expect_download(timeout=240_000)' in proof
    assert 'ui_review_pdf_original_user_gesture_preserved' in proof
    assert 'ui_review_pdf_artifact_status_cleared' in proof
    assert 'ui_review_pdf_action_kind' in proof
    assert 'ui_review_pdf_network_path' in proof
    assert 'localized-draft-pending-approval' in proof
    assert 'accepted-edition' in proof


def test_production_workflows_execute_non_retrying_download_entry_points() -> None:
    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")
    ios = IOS_WORKFLOW.read_text(encoding="utf-8")

    assert "python scripts/mobile_restart_live_acceptance_v5.py" in mobile
    assert "not_dispatched_existing_run" in mobile
    assert 'payload["start_request_count"] == 0' in mobile
    assert 'payload["continuation_post_count"] == 0' in mobile
    assert "--source-workflow-run-attempt" in mobile
    assert "--observation-seconds 90" in mobile
    assert "--ui-locale en" in mobile
    assert "start_dispatch_retry_absent" in mobile
    assert "ui_review_pdf_download_verified" in mobile
    assert 'payload["terminal_observation"]["legacy_markdown_get_count"] == 0' in mobile
    assert 'payload["terminal_observation"]["markdown_action_success_count"] == 2' in mobile
    assert 'payload["ui_review_pdf_lifecycle_contract_verified"] is True' in mobile
    assert 'payload["ui_review_pdf_user_gesture_anchor_click_count"] == 1' in mobile
    assert 'payload["ui_review_pdf_anchor_click_observation_verified"] is True' in mobile
    assert "python scripts/mobile_restart_live_acceptance_v1.py" not in mobile

    assert "python scripts/mobile_restart_live_acceptance_v6.py" in ios
    assert "not_dispatched_existing_run" in ios
    assert 'payload["start_request_count"] == 0' in ios
    assert 'payload["continuation_post_count"] == 0' in ios
    assert "--source-workflow-run-attempt" in ios
    assert "--observation-seconds 90" in ios
    assert "--ui-locale es-MX" in ios
    assert 'payload["assessment_path"] == "/es/assessment"' in ios
    assert 'payload["terminal_visibility_transitions"] == ["hidden", "visible"]' in ios
    assert 'payload["professional_review_locale_preserved"] is True' in ios
    assert "Playwright WebKit iPhone-sized mobile emulation" in ios
    assert "real_device_tested" in ios
    assert "start_dispatch_retry_absent" in ios
    assert "ui_review_pdf_download_verified" in ios
    assert 'payload["terminal_observation"]["legacy_markdown_get_count"] == 0' in ios
    assert 'payload["terminal_observation"]["markdown_action_success_count"] == 2' in ios
    assert 'payload["ui_review_pdf_lifecycle_contract_verified"] is True' in ios
    assert 'payload["ui_review_pdf_user_gesture_anchor_click_count"] == 1' in ios
    assert 'payload["ui_review_pdf_anchor_click_observation_verified"] is True' in ios
    assert "python scripts/mobile_restart_live_acceptance_v2.py" not in ios
