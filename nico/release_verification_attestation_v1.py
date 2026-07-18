"""Validate final release verification evidence for issue #529.

The attestation is intentionally fail-closed. A release is eligible only when two
consecutive complete verification passes target the same immutable commit and both
staging and production deployments are aligned to that commit.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

REQUIRED_WORKFLOWS = {
    "NICO CI",
    "Audit Evidence",
    "Security Audit Evidence",
    "Remediation Evidence",
    "Postgres Restart Proof",
    "Recorded Golden Demonstration",
    "Resilience Proof",
    "CodeQL Advanced",
}
REQUIRED_TIERS = {"express", "mid", "full"}
REQUIRED_FORMATS = {"pdf", "html", "markdown"}
REQUIRED_LANGUAGES = {"en", "es"}


def qualify_release_verification(
    attestation: Mapping[str, Any], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    intended_sha = str(attestation.get("intended_sha", "")).strip()
    if len(intended_sha) != 40:
        failures.append("invalid_intended_sha")

    passes = attestation.get("verification_passes")
    if not isinstance(passes, Sequence) or isinstance(passes, (str, bytes)):
        failures.append("missing_verification_passes")
        passes = []
    if len(passes) != 2:
        failures.append("requires_two_consecutive_passes")

    prior_completed_at = ""
    for index, verification in enumerate(passes):
        prefix = f"pass_{index + 1}"
        if not isinstance(verification, Mapping):
            failures.append(f"{prefix}:invalid")
            continue
        if verification.get("head_sha") != intended_sha:
            failures.append(f"{prefix}:head_sha_mismatch")
        completed_at = str(verification.get("completed_at", "")).strip()
        if not completed_at:
            failures.append(f"{prefix}:missing_completed_at")
        elif prior_completed_at and completed_at <= prior_completed_at:
            failures.append(f"{prefix}:not_consecutive")
        prior_completed_at = completed_at

        workflows = verification.get("workflows")
        if not isinstance(workflows, Mapping):
            failures.append(f"{prefix}:missing_workflows")
        else:
            if set(workflows) != REQUIRED_WORKFLOWS:
                failures.append(f"{prefix}:workflow_set_mismatch")
            for name in REQUIRED_WORKFLOWS:
                if workflows.get(name) != "success":
                    failures.append(f"{prefix}:workflow_failed:{name}")

        for field in (
            "staging_smoke_passed",
            "production_smoke_passed",
            "restart_recovery_passed",
            "stale_payload_rejected",
            "partial_evidence_rejected",
            "failed_tools_recovered",
            "timeouts_recovered",
            "approval_revocation_passed",
            "duplicate_run_prevention_passed",
            "large_repository_passed",
            "large_evidence_packet_passed",
            "iphone_downloads_passed",
            "manual_inspection_complete",
            "no_known_critical_or_high_defects",
        ):
            if verification.get(field) is not True:
                failures.append(f"{prefix}:{field}:failed")

        if set(verification.get("tiers", [])) != REQUIRED_TIERS:
            failures.append(f"{prefix}:tier_coverage_mismatch")
        if set(verification.get("formats", [])) != REQUIRED_FORMATS:
            failures.append(f"{prefix}:format_coverage_mismatch")
        if set(verification.get("languages", [])) != REQUIRED_LANGUAGES:
            failures.append(f"{prefix}:language_coverage_mismatch")
        if verification.get("cross_format_equivalent") is not True:
            failures.append(f"{prefix}:cross_format_equivalence_failed")
        if verification.get("cross_language_equivalent") is not True:
            failures.append(f"{prefix}:cross_language_equivalence_failed")
        if verification.get("cross_tier_isolation_passed") is not True:
            failures.append(f"{prefix}:cross_tier_isolation_failed")

    deployments = attestation.get("deployments")
    if not isinstance(deployments, Mapping):
        failures.append("missing_deployments")
    else:
        for environment in ("vercel", "backend_staging", "backend_production"):
            deployment = deployments.get(environment)
            if not isinstance(deployment, Mapping):
                failures.append(f"deployment:{environment}:missing")
                continue
            if deployment.get("sha") != intended_sha:
                failures.append(f"deployment:{environment}:sha_mismatch")
            if deployment.get("healthy") is not True:
                failures.append(f"deployment:{environment}:unhealthy")
            if not str(deployment.get("verified_at", "")).strip():
                failures.append(f"deployment:{environment}:missing_verified_at")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "release_allowed": not unique,
        "failures": unique,
        "intended_sha": intended_sha,
    }
