from pathlib import Path


def test_default_live_production_proofs_are_serialized() -> None:
    mobile = Path(".github/workflows/mobile-restart-production-proof.yml").read_text(encoding="utf-8")
    ios = Path(".github/workflows/ios-webkit-paint-proof.yml").read_text(encoding="utf-8")

    for workflow in (mobile, ios):
        header = workflow.split("\njobs:", 1)[0]
        assert "workflow_run:" in header
        assert "Spanish Comprehensive Production Proof" in header
        assert "push:" not in header
        assert "workflow_dispatch:" not in header
        assert "actions/download-artifact@3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c" in workflow
        assert "--source-proof source-proof/spanish-comprehensive-live-proof.json" in workflow
        assert "github.event.workflow_run.run_attempt" in workflow
        assert "${{ github.run_attempt }}" in workflow
    assert "Wait for exact-SHA Mobile production proof" in ios
    assert 'required_context = "NICO Mobile Restart Production Proof"' in ios

    spanish_wait = mobile.index("Download sole Comprehensive run handoff")
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


def test_sole_fresh_producer_fails_closed_on_wrong_production_scope() -> None:
    spanish = Path(
        ".github/workflows/spanish-comprehensive-production-proof.yml"
    ).read_text(encoding="utf-8")

    assert 'test "${NICO_PRODUCTION_FRONTEND_URL}" = "https://app.nicoaudit.com"' in spanish
    assert 'test "${NICO_PRODUCTION_SMOKE_REPOSITORY}" = "BoneManTGRM/NICO"' in spanish
    assert 'test "${GITHUB_REF}" = "refs/heads/main"' in spanish
    assert 'test "$(git rev-parse HEAD)" = "${RELEASE_SHA}"' in spanish


def test_closure_chain_has_bounded_fixture_producer_and_consumer_only_downstream() -> None:
    paths = {
        name: Path(".github/workflows") / name
        for name in (
            "spanish-comprehensive-production-proof.yml",
            "mobile-restart-production-proof.yml",
            "ios-webkit-paint-proof.yml",
            "two-service-production-acceptance.yml",
        )
    }
    workflows = {
        name: path.read_text(encoding="utf-8") for name, path in paths.items()
    }

    producer = workflows["spanish-comprehensive-production-proof.yml"]
    assert producer.count("python scripts/spanish_comprehensive_live_acceptance_v3.py") == 2
    assert "NICO_SPANISH_PROOF_ENGAGEMENT_FIXTURE: excluded" in producer
    assert "Run explicit exclusion-state Comprehensive proof" in producer
    for name, source in workflows.items():
        if name == "spanish-comprehensive-production-proof.yml":
            continue
        assert "python scripts/spanish_comprehensive_live_acceptance" not in source
        assert "/comprehensive-intake" not in source
        assert "/continue" not in source
        assert "--source-proof source-proof/spanish-comprehensive-live-proof.json" in source
        assert '--source-workflow-run-attempt "${SOURCE_RUN_ATTEMPT}"' in source
