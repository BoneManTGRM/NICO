from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHROMIUM = ROOT / "scripts/mobile_restart_live_acceptance_v3.py"
WEBKIT = ROOT / "scripts/mobile_restart_live_acceptance_v4.py"
MOBILE_WORKFLOW = ROOT / ".github/workflows/mobile-restart-production-proof.yml"
IOS_WORKFLOW = ROOT / ".github/workflows/ios-webkit-paint-proof.yml"


def test_mobile_proof_dispatches_one_native_click_without_playwright_retry() -> None:
    source = CHROMIUM.read_text(encoding="utf-8")

    assert 'VERSION = "nico.mobile_restart_live_acceptance.single_dispatch.v3"' in source
    assert "class _SingleDispatchLocator" in source
    assert "button.click();" in source
    assert "_ORIGINAL_RUN_PROOF(SingleDispatchBrowser(browser), args)" in source
    assert 'result["start_dispatch"] = "single_native_dom_click"' in source
    assert 'result["start_dispatch_retry_absent"] = True' in source
    assert "self._locator.click(" not in source


def test_webkit_proof_reuses_the_same_single_dispatch_boundary() -> None:
    source = WEBKIT.read_text(encoding="utf-8")

    assert 'VERSION = "nico.mobile_restart_live_acceptance.webkit_single_dispatch.v4"' in source
    assert "webkit.recovery.run_proof = single_dispatch.run_proof" in source
    assert "return webkit.main(argv)" in source


def test_production_workflows_execute_the_non_retrying_entry_points() -> None:
    mobile = MOBILE_WORKFLOW.read_text(encoding="utf-8")
    ios = IOS_WORKFLOW.read_text(encoding="utf-8")

    assert "python scripts/mobile_restart_live_acceptance_v3.py" in mobile
    assert "single_native_dom_click" in mobile
    assert "start_dispatch_retry_absent" in mobile
    assert "python scripts/mobile_restart_live_acceptance_v1.py" not in mobile

    assert "python scripts/mobile_restart_live_acceptance_v4.py" in ios
    assert "single_native_dom_click" in ios
    assert "start_dispatch_retry_absent" in ios
    assert "python scripts/mobile_restart_live_acceptance_v2.py" not in ios
