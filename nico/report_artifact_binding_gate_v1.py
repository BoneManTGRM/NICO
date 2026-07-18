"""Require inspectable report artifacts for every release tier."""

from __future__ import annotations

from typing import Any, Mapping

TIERS = ("express", "mid", "full")
FORMATS = ("pdf", "html", "markdown")
LANGUAGES = ("en", "es")


def qualify_report_artifacts(
    manifests: Mapping[str, Mapping[str, Any]], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    seen_assessments: set[str] = set()
    for tier in TIERS:
        manifest = manifests.get(tier)
        if not isinstance(manifest, Mapping):
            failures.append(f"{tier}:missing_manifest")
            continue

        assessment_id = str(manifest.get("assessment_id", "")).strip()
        if not assessment_id:
            failures.append(f"{tier}:missing:assessment_id")
        elif assessment_id in seen_assessments:
            failures.append(f"{tier}:duplicate_assessment_id")
        else:
            seen_assessments.add(assessment_id)

        for field in ("snapshot_sha", "generated_at", "generator_version"):
            if not str(manifest.get(field, "")).strip():
                failures.append(f"{tier}:missing:{field}")

        artifacts = manifest.get("artifacts")
        if not isinstance(artifacts, Mapping):
            failures.append(f"{tier}:missing:artifacts")
            continue

        hashes: set[str] = set()
        for language in LANGUAGES:
            localized = artifacts.get(language)
            if not isinstance(localized, Mapping):
                failures.append(f"{tier}:missing_language:{language}")
                continue
            for output_format in FORMATS:
                artifact = localized.get(output_format)
                if not isinstance(artifact, Mapping):
                    failures.append(f"{tier}:{language}:missing_format:{output_format}")
                    continue
                for field in ("uri", "sha256", "content_fingerprint"):
                    if not str(artifact.get(field, "")).strip():
                        failures.append(f"{tier}:{language}:{output_format}:missing:{field}")
                sha256 = str(artifact.get("sha256", "")).strip()
                if sha256:
                    if sha256 in hashes:
                        failures.append(f"{tier}:{language}:{output_format}:duplicate_artifact_hash")
                    hashes.add(sha256)
                if artifact.get("download_verified") is not True:
                    failures.append(f"{tier}:{language}:{output_format}:download_unverified")
                if artifact.get("manual_inspection_complete") is not True:
                    failures.append(f"{tier}:{language}:{output_format}:inspection_incomplete")
                if artifact.get("mobile_verified") is not True:
                    failures.append(f"{tier}:{language}:{output_format}:mobile_unverified")

        if manifest.get("cross_format_equivalent") is not True:
            failures.append(f"{tier}:cross_format_mismatch")
        if manifest.get("cross_language_equivalent") is not True:
            failures.append(f"{tier}:cross_language_mismatch")
        if manifest.get("tier_isolation_verified") is not True:
            failures.append(f"{tier}:tier_isolation_failed")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
