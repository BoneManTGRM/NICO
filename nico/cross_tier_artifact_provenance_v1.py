"""Fail-closed provenance checks for cross-tier report artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

TIERS = ("express", "mid", "full")
FORMATS = ("markdown", "html", "pdf")


def _parse_utc(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def qualify_cross_tier_artifact_provenance(
    packages: Mapping[str, Mapping[str, Any]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for tier in TIERS:
        package = packages.get(tier)
        if not isinstance(package, Mapping):
            failures.append(f"{tier}:missing_package")
            continue

        generated_at = _parse_utc(package.get("generated_at"))
        inspected_at = _parse_utc(package.get("inspected_at"))
        reviewer = str(package.get("reviewer") or "").strip()
        generator_version = str(package.get("generator_version") or "").strip()
        deployment_sha = str(package.get("deployment_sha") or "").strip().lower()

        if generated_at is None:
            failures.append(f"{tier}:invalid_generated_at")
        if inspected_at is None:
            failures.append(f"{tier}:invalid_inspected_at")
        if generated_at and inspected_at and inspected_at < generated_at:
            failures.append(f"{tier}:inspection_before_generation")
        if not reviewer:
            failures.append(f"{tier}:missing_reviewer")
        if not generator_version:
            failures.append(f"{tier}:missing_generator_version")
        if len(deployment_sha) != 40 or any(ch not in "0123456789abcdef" for ch in deployment_sha):
            failures.append(f"{tier}:invalid_deployment_sha")

        artifacts = package.get("artifacts")
        if not isinstance(artifacts, Mapping):
            failures.append(f"{tier}:missing_artifacts")
            continue

        for format_name in FORMATS:
            artifact = artifacts.get(format_name)
            if not isinstance(artifact, Mapping):
                failures.append(f"{tier}:{format_name}:missing")
                continue
            artifact_generated = _parse_utc(artifact.get("generated_at"))
            artifact_deployment = str(artifact.get("deployment_sha") or "").strip().lower()
            artifact_generator = str(artifact.get("generator_version") or "").strip()
            if artifact_generated is None:
                failures.append(f"{tier}:{format_name}:invalid_generated_at")
            if generated_at and artifact_generated and artifact_generated != generated_at:
                failures.append(f"{tier}:{format_name}:generation_time_mismatch")
            if artifact_deployment != deployment_sha:
                failures.append(f"{tier}:{format_name}:deployment_sha_mismatch")
            if artifact_generator != generator_version:
                failures.append(f"{tier}:{format_name}:generator_version_mismatch")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "release_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
        "formats_checked": list(FORMATS),
    }
