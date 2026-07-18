"""Fail-closed final release certification for Express, Mid, and Full."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS: Sequence[str] = ("express", "mid", "full")
ENVIRONMENTS: Sequence[str] = ("staging", "production")
FORMATS: Sequence[str] = ("pdf", "html", "markdown")
LOCALES: Sequence[str] = ("en", "es")


def certify_release(
    evidence: Mapping[str, Any],
    *,
    expected_sha: str,
    prior_delivery_allowed: bool = True,
) -> dict[str, Any]:
    """Return a final release decision that fails closed on incomplete evidence."""

    failures: list[str] = []
    if not prior_delivery_allowed:
        failures.append("prior_delivery_block")

    if not expected_sha:
        failures.append("missing_expected_sha")

    passes = evidence.get("verification_passes")
    if not isinstance(passes, list) or len(passes) != 2:
        failures.append("requires_exactly_two_verification_passes")
    else:
        for index, item in enumerate(passes):
            if not isinstance(item, Mapping):
                failures.append(f"verification_pass_{index}:invalid")
                continue
            if item.get("status") != "clean":
                failures.append(f"verification_pass_{index}:not_clean")
            if item.get("commit_sha") != expected_sha:
                failures.append(f"verification_pass_{index}:sha_mismatch")

    deployments = evidence.get("deployments")
    if not isinstance(deployments, Mapping):
        failures.append("missing_deployments")
    else:
        for environment in ENVIRONMENTS:
            deployment = deployments.get(environment)
            if not isinstance(deployment, Mapping):
                failures.append(f"{environment}:missing_deployment")
                continue
            if deployment.get("healthy") is not True:
                failures.append(f"{environment}:unhealthy")
            if deployment.get("commit_sha") != expected_sha:
                failures.append(f"{environment}:sha_mismatch")
            if not deployment.get("deployment_id"):
                failures.append(f"{environment}:missing_deployment_id")

    tiers = evidence.get("tiers")
    if not isinstance(tiers, Mapping):
        failures.append("missing_tier_evidence")
    else:
        for tier in TIERS:
            record = tiers.get(tier)
            if not isinstance(record, Mapping):
                failures.append(f"{tier}:missing")
                continue
            if record.get("commit_sha") != expected_sha:
                failures.append(f"{tier}:sha_mismatch")
            if record.get("smoke_test_passed") is not True:
                failures.append(f"{tier}:smoke_test_failed")
            if record.get("mobile_download_passed") is not True:
                failures.append(f"{tier}:mobile_download_failed")
            if record.get("manual_inspection_passed") is not True:
                failures.append(f"{tier}:manual_inspection_failed")
            artifacts = record.get("artifacts")
            if not isinstance(artifacts, Mapping):
                failures.append(f"{tier}:missing_artifacts")
                continue
            for locale in LOCALES:
                locale_artifacts = artifacts.get(locale)
                if not isinstance(locale_artifacts, Mapping):
                    failures.append(f"{tier}:{locale}:missing_artifacts")
                    continue
                for format_name in FORMATS:
                    if not locale_artifacts.get(format_name):
                        failures.append(f"{tier}:{locale}:{format_name}:missing")

    if evidence.get("critical_defects", 1) != 0:
        failures.append("critical_defects_remaining")
    if evidence.get("high_defects", 1) != 0:
        failures.append("high_defects_remaining")

    unique = sorted(set(failures))
    return {
        "status": "certified" if not unique else "blocked",
        "release_allowed": not unique,
        "failures": unique,
        "expected_sha": expected_sha,
    }
