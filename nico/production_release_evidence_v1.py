"""Fail-closed production release evidence for Express, Mid, and Full."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

TIERS = ("express", "mid", "full")
FORMATS = ("pdf", "html", "markdown")
LANGUAGES = ("en", "es")


def verify_production_release(
    evidence: Mapping[str, Any],
    *,
    expected_commit_sha: str,
) -> dict[str, Any]:
    """Allow release only when production evidence is complete and immutable."""

    failures: list[str] = []
    if not expected_commit_sha:
        failures.append("expected_commit_sha_missing")

    deployments = evidence.get("deployments")
    if not isinstance(deployments, Mapping):
        failures.append("deployments_missing")
    else:
        for environment in ("staging", "production"):
            deployment = deployments.get(environment)
            if not isinstance(deployment, Mapping):
                failures.append(f"{environment}:deployment_missing")
                continue
            if deployment.get("commit_sha") != expected_commit_sha:
                failures.append(f"{environment}:commit_sha_mismatch")
            if deployment.get("healthy") is not True:
                failures.append(f"{environment}:unhealthy")
            if not deployment.get("deployment_id"):
                failures.append(f"{environment}:deployment_id_missing")
            if not deployment.get("frontend_url"):
                failures.append(f"{environment}:frontend_url_missing")
            if not deployment.get("backend_url"):
                failures.append(f"{environment}:backend_url_missing")

    passes = evidence.get("verification_passes")
    if not isinstance(passes, list) or len(passes) != 2:
        failures.append("two_verification_passes_required")
    else:
        for index, verification in enumerate(passes, start=1):
            if not isinstance(verification, Mapping):
                failures.append(f"pass-{index}:invalid")
                continue
            if verification.get("commit_sha") != expected_commit_sha:
                failures.append(f"pass-{index}:commit_sha_mismatch")
            if verification.get("clean") is not True:
                failures.append(f"pass-{index}:not_clean")

    tiers = evidence.get("tiers")
    if not isinstance(tiers, Mapping):
        failures.append("tiers_missing")
    else:
        for tier in TIERS:
            tier_evidence = tiers.get(tier)
            if not isinstance(tier_evidence, Mapping):
                failures.append(f"{tier}:evidence_missing")
                continue
            if tier_evidence.get("smoke_test_passed") is not True:
                failures.append(f"{tier}:smoke_test_failed")
            if tier_evidence.get("mobile_download_passed") is not True:
                failures.append(f"{tier}:mobile_download_failed")
            if tier_evidence.get("manual_inspection_passed") is not True:
                failures.append(f"{tier}:manual_inspection_failed")
            outputs = tier_evidence.get("outputs")
            if not isinstance(outputs, Mapping):
                failures.append(f"{tier}:outputs_missing")
                continue
            for language in LANGUAGES:
                language_outputs = outputs.get(language)
                if not isinstance(language_outputs, Mapping):
                    failures.append(f"{tier}:{language}:outputs_missing")
                    continue
                for output_format in FORMATS:
                    artifact = language_outputs.get(output_format)
                    if not isinstance(artifact, Mapping):
                        failures.append(f"{tier}:{language}:{output_format}:missing")
                        continue
                    if artifact.get("commit_sha") != expected_commit_sha:
                        failures.append(f"{tier}:{language}:{output_format}:commit_sha_mismatch")
                    if not artifact.get("artifact_id"):
                        failures.append(f"{tier}:{language}:{output_format}:artifact_id_missing")
                    checksum = artifact.get("sha256")
                    if not isinstance(checksum, str) or len(checksum) != 64:
                        failures.append(f"{tier}:{language}:{output_format}:checksum_invalid")

    defects = evidence.get("open_defects")
    if not isinstance(defects, Mapping):
        failures.append("open_defects_missing")
    else:
        if int(defects.get("critical", -1)) != 0:
            failures.append("critical_defects_open")
        if int(defects.get("high", -1)) != 0:
            failures.append("high_defects_open")

    allowed = not failures
    return {
        "status": "release_ready" if allowed else "blocked",
        "release_allowed": allowed,
        "expected_commit_sha": expected_commit_sha,
        "tiers_checked": list(TIERS),
        "languages_checked": list(LANGUAGES),
        "formats_checked": list(FORMATS),
        "failures": sorted(set(failures)),
    }
