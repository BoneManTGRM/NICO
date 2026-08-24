from pathlib import Path


def test_default_live_production_proofs_are_serialized() -> None:
    mobile = Path(".github/workflows/mobile-restart-production-proof.yml").read_text(encoding="utf-8")
    ios = Path(".github/workflows/ios-webkit-paint-proof.yml").read_text(encoding="utf-8")

    assert "Wait for exact-SHA Spanish production proof" in mobile
    assert 'required_context = "NICO Spanish Comprehensive Production Proof"' in mobile
    assert "Wait for exact-SHA Mobile production proof" in ios
    assert 'required_context = "NICO Mobile Restart Production Proof"' in ios

    spanish_wait = mobile.index("Wait for exact-SHA Spanish production proof")
    mobile_launch = mobile.index("Prove recovery and exact-run review PDF download")
    assert spanish_wait < mobile_launch

    mobile_wait = ios.index("Wait for exact-SHA Mobile production proof")
    ios_launch = ios.index("Prove WebKit intake, bilingual failure layout, recovery, and review PDF download")
    assert mobile_wait < ios_launch


def test_serialization_does_not_cancel_immutable_release_proofs() -> None:
    spanish = Path(".github/workflows/spanish-comprehensive-production-proof.yml").read_text(encoding="utf-8")
    mobile = Path(".github/workflows/mobile-restart-production-proof.yml").read_text(encoding="utf-8")
    ios = Path(".github/workflows/ios-webkit-paint-proof.yml").read_text(encoding="utf-8")

    assert "cancel-in-progress: false" in spanish
    assert "cancel-in-progress: false" in mobile
    assert "cancel-in-progress: false" in ios
