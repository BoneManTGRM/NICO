"""Fail-closed identity checks for terminal assessment artifacts."""

from __future__ import annotations

import re
from typing import Any, Mapping

TIERS = ("express", "mid", "full")
FORMATS = ("markdown", "html", "pdf")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")


def qualify_cross_tier_artifact_identity(
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

        assessment_id = str(package.get("assessment_id") or "").strip()
        run_id = str(package.get("run_id") or "").strip()
        snapshot_sha = str(package.get("snapshot_sha") or "").lower().strip()
        if not assessment_id:
            failures.append(f"{tier}:missing_assessment_id")
        if not run_id:
            failures.append(f"{tier}:missing_run_id")
        if not _COMMIT.fullmatch(snapshot_sha):
            failures.append(f"{tier}:invalid_snapshot_sha")

        artifacts = package.get("artifacts")
        if not isinstance(artifacts, Mapping):
            failures.append(f"{tier}:missing_artifacts")
            continue

        identities: set[tuple[str, str, str]] = set()
        for format_name in FORMATS:
            artifact = artifacts.get(format_name)
            if not isinstance(artifact, Mapping):
                failures.append(f"{tier}:{format_name}:missing")
                continue
            digest = str(artifact.get("sha256") or "").lower().strip()
            artifact_assessment = str(artifact.get("assessment_id") or "").strip()
            artifact_run = str(artifact.get("run_id") or "").strip()
            artifact_snapshot = str(artifact.get("snapshot_sha") or "").lower().strip()
            if not _SHA256.fullmatch(digest):
                failures.append(f"{tier}:{format_name}:invalid_sha256")
            if artifact.get("available") is not True:
                failures.append(f"{tier}:{format_name}:unavailable")
            if artifact.get("manual_inspection_passed") is not True:
                failures.append(f"{tier}:{format_name}:manual_inspection_missing")
            if artifact_assessment != assessment_id:
                failures.append(f"{tier}:{format_name}:assessment_identity_mismatch")
            if artifact_run != run_id:
                failures.append(f"{tier}:{format_name}:run_identity_mismatch")
            if artifact_snapshot != snapshot_sha:
                failures.append(f"{tier}:{format_name}:snapshot_identity_mismatch")
            identities.add((artifact_assessment, artifact_run, artifact_snapshot))

        if len(identities) > 1:
            failures.append(f"{tier}:cross_format_identity_mismatch")
        if package.get("human_review_required") is not True:
            failures.append(f"{tier}:human_review_not_required")
        if package.get("client_ready") is not False:
            failures.append(f"{tier}:client_ready_before_approval")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
        "formats_checked": list(FORMATS),
    }
