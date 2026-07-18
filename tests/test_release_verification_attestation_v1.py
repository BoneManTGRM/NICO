from nico.release_verification_attestation_v1 import (
    REQUIRED_WORKFLOWS,
    qualify_release_verification,
)


SHA = "a" * 40


def _verification(completed_at):
    return {
        "head_sha": SHA,
        "completed_at": completed_at,
        "workflows": {name: "success" for name in REQUIRED_WORKFLOWS},
        "staging_smoke_passed": True,
        "production_smoke_passed": True,
        "restart_recovery_passed": True,
        "stale_payload_rejected": True,
        "partial_evidence_rejected": True,
        "failed_tools_recovered": True,
        "timeouts_recovered": True,
        "approval_revocation_passed": True,
        "duplicate_run_prevention_passed": True,
        "large_repository_passed": True,
        "large_evidence_packet_passed": True,
        "iphone_downloads_passed": True,
        "manual_inspection_complete": True,
        "no_known_critical_or_high_defects": True,
        "tiers": ["express", "mid", "full"],
        "formats": ["pdf", "html", "markdown"],
        "languages": ["en", "es"],
        "cross_format_equivalent": True,
        "cross_language_equivalent": True,
        "cross_tier_isolation_passed": True,
    }


def _attestation():
    return {
        "intended_sha": SHA,
        "verification_passes": [
            _verification("2026-07-18T03:00:00Z"),
            _verification("2026-07-18T04:00:00Z"),
        ],
        "deployments": {
            environment: {
                "sha": SHA,
                "healthy": True,
                "verified_at": "2026-07-18T04:05:00Z",
            }
            for environment in ("vercel", "backend_staging", "backend_production")
        },
    }


def test_complete_attestation_qualifies():
    result = qualify_release_verification(_attestation())
    assert result["release_allowed"] is True
    assert result["status"] == "qualified"


def test_requires_two_same_sha_consecutive_passes():
    attestation = _attestation()
    attestation["verification_passes"] = [attestation["verification_passes"][0]]
    result = qualify_release_verification(attestation)
    assert "requires_two_consecutive_passes" in result["failures"]

    attestation = _attestation()
    attestation["verification_passes"][1]["head_sha"] = "b" * 40
    attestation["verification_passes"][1]["completed_at"] = "2026-07-18T02:00:00Z"
    result = qualify_release_verification(attestation)
    assert "pass_2:head_sha_mismatch" in result["failures"]
    assert "pass_2:not_consecutive" in result["failures"]


def test_failed_workflow_and_missing_coverage_block():
    attestation = _attestation()
    second = attestation["verification_passes"][1]
    second["workflows"]["NICO CI"] = "failure"
    second["languages"] = ["en"]
    second["iphone_downloads_passed"] = False
    result = qualify_release_verification(attestation)
    assert "pass_2:workflow_failed:NICO CI" in result["failures"]
    assert "pass_2:language_coverage_mismatch" in result["failures"]
    assert "pass_2:iphone_downloads_passed:failed" in result["failures"]


def test_deployment_sha_and_health_must_align():
    attestation = _attestation()
    attestation["deployments"]["vercel"]["sha"] = "b" * 40
    attestation["deployments"]["backend_production"]["healthy"] = False
    result = qualify_release_verification(attestation)
    assert "deployment:vercel:sha_mismatch" in result["failures"]
    assert "deployment:backend_production:unhealthy" in result["failures"]


def test_prior_release_block_is_preserved():
    result = qualify_release_verification(_attestation(), prior_release_allowed=False)
    assert result["release_allowed"] is False
    assert "prior_release_block" in result["failures"]
