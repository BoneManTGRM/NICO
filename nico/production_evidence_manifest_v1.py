"""Validate immutable production release evidence for Express, Mid, and Full."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
LANGUAGES = ("en", "es")
FORMATS = ("pdf", "html", "markdown")


def validate_production_evidence_manifest(
    manifest: Mapping[str, Any], *, expected_sha: str
) -> dict[str, Any]:
    """Return a fail-closed production release decision."""
    failures: list[str] = []

    if not expected_sha or len(expected_sha) != 40:
        failures.append("invalid_expected_sha")

    for environment in ("staging", "production"):
        deployment = manifest.get("deployments", {}).get(environment)
        if not isinstance(deployment, Mapping):
            failures.append(f"{environment}:missing_deployment")
            continue
        if deployment.get("sha") != expected_sha:
            failures.append(f"{environment}:sha_mismatch")
        if deployment.get("healthy") is not True:
            failures.append(f"{environment}:unhealthy")

    passes = manifest.get("verification_passes")
    if not isinstance(passes, list) or len(passes) != 2:
        failures.append("verification_passes:must_equal_two")
    else:
        for index, record in enumerate(passes, start=1):
            if not isinstance(record, Mapping):
                failures.append(f"verification_pass_{index}:invalid")
                continue
            if record.get("sha") != expected_sha:
                failures.append(f"verification_pass_{index}:sha_mismatch")
            if record.get("clean") is not True:
                failures.append(f"verification_pass_{index}:not_clean")

    tier_records = manifest.get("tiers", {})
    for tier in TIERS:
        record = tier_records.get(tier)
        if not isinstance(record, Mapping):
            failures.append(f"{tier}:missing")
            continue
        for check in ("smoke_test", "mobile_download", "manual_inspection"):
            if record.get(check) is not True:
                failures.append(f"{tier}:{check}:failed")
        artifacts = record.get("artifacts", {})
        for language in LANGUAGES:
            for format_name in FORMATS:
                artifact = artifacts.get(language, {}).get(format_name)
                key = f"{tier}:{language}:{format_name}"
                if not isinstance(artifact, Mapping):
                    failures.append(f"{key}:missing")
                    continue
                if artifact.get("sha") != expected_sha:
                    failures.append(f"{key}:sha_mismatch")
                checksum = artifact.get("sha256")
                if not isinstance(checksum, str) or len(checksum) != 64:
                    failures.append(f"{key}:invalid_checksum")

    defects = manifest.get("open_defects", {})
    if defects.get("critical", 0) != 0:
        failures.append("open_critical_defects")
    if defects.get("high", 0) != 0:
        failures.append("open_high_defects")

    return {
        "status": "release_ready" if not failures else "blocked",
        "release_allowed": not failures,
        "failures": sorted(set(failures)),
        "expected_sha": expected_sha,
    }
