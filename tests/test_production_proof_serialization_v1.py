from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOBILE = (
    ROOT / ".github" / "workflows" / "mobile-restart-production-proof.yml"
).read_text(encoding="utf-8")
IOS = (
    ROOT / ".github" / "workflows" / "ios-webkit-paint-proof.yml"
).read_text(encoding="utf-8")


def test_mobile_and_ios_proofs_do_not_share_a_cancelling_workflow_group() -> None:
    assert "group: nico-production-assessment-proof-${{ github.ref }}" in MOBILE
    assert "group: nico-production-ios-webkit-proof-${{ github.ref }}" in IOS
    assert "group: nico-production-assessment-proof-${{ github.ref }}" not in IOS


def test_ios_proof_waits_for_exact_sha_mobile_success_before_starting_webkit() -> None:
    wait_step = "- name: Wait for exact-SHA Mobile production proof"
    identity_step = "- name: Verify exact frontend release identity"
    browser_step = "- name: Prove WebKit intake, bilingual failure layout, recovery, and review PDF download"

    assert wait_step in IOS
    assert 'required_context = "NICO Mobile Restart Production Proof"' in IOS
    assert 'if last_state == "success":' in IOS
    assert 'if last_state in {"error", "failure"}:' in IOS
    assert "nico-ios-wait-for-mobile-proof" in IOS
    assert IOS.index(wait_step) < IOS.index(identity_step) < IOS.index(browser_step)


def test_proof_ordering_remains_exact_sha_and_fail_closed() -> None:
    assert 'sha = os.environ["RELEASE_SHA"]' in IOS
    assert "commits/{sha}/status" in IOS
    assert "Timed out waiting for exact-SHA Mobile production proof" in IOS
    assert "Publish failed iOS proof status" in IOS
    assert '"state": "failure"' in IOS
