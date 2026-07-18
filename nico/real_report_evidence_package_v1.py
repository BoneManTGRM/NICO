"""Fail-closed validation for real report value evidence packages."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

TIERS = ("express", "mid", "full")
FORMATS = ("pdf", "html", "markdown")
MIN_VERIFIED_FINDINGS = {"express": 3, "mid": 7, "full": 12}


def qualify_real_report_evidence_package(
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

        for field in (
            "assessment_id",
            "repository_identity",
            "snapshot_sha",
            "generated_at",
            "independent_reviewer",
            "review_rubric_version",
            "client_decision",
        ):
            if not str(package.get(field, "")).strip():
                failures.append(f"{tier}:missing:{field}")

        if package.get("synthetic_fixture") is not False:
            failures.append(f"{tier}:synthetic_or_unverified_package")
        if package.get("client_authorized") is not True:
            failures.append(f"{tier}:client_authorization_missing")
        if package.get("manual_artifact_inspection_complete") is not True:
            failures.append(f"{tier}:manual_inspection_incomplete")

        artifacts = package.get("artifacts")
        if not isinstance(artifacts, Mapping):
            failures.append(f"{tier}:missing_artifacts")
        else:
            for fmt in FORMATS:
                artifact = artifacts.get(fmt)
                if not isinstance(artifact, Mapping):
                    failures.append(f"{tier}:missing_artifact:{fmt}")
                    continue
                if not str(artifact.get("uri", "")).strip():
                    failures.append(f"{tier}:{fmt}:missing_uri")
                checksum = str(artifact.get("sha256", "")).strip().lower()
                if len(checksum) != 64 or any(c not in "0123456789abcdef" for c in checksum):
                    failures.append(f"{tier}:{fmt}:invalid_sha256")
                if artifact.get("opened_successfully") is not True:
                    failures.append(f"{tier}:{fmt}:not_opened")

        findings = package.get("verified_findings")
        if not isinstance(findings, Sequence) or isinstance(findings, (str, bytes)):
            failures.append(f"{tier}:missing_verified_findings")
        else:
            if len(findings) < MIN_VERIFIED_FINDINGS[tier]:
                failures.append(f"{tier}:insufficient_verified_findings")
            for index, finding in enumerate(findings):
                if not isinstance(finding, Mapping):
                    failures.append(f"{tier}:finding_{index}:invalid")
                    continue
                for field in ("finding_id", "evidence_pointer", "business_impact", "recommended_action"):
                    if not str(finding.get(field, "")).strip():
                        failures.append(f"{tier}:finding_{index}:missing:{field}")
                if finding.get("evidence_verified") is not True:
                    failures.append(f"{tier}:finding_{index}:evidence_unverified")

        scores = package.get("review_scores")
        if not isinstance(scores, Mapping):
            failures.append(f"{tier}:missing_review_scores")
        else:
            for field in ("accuracy", "specificity", "actionability", "decision_utility", "economic_value"):
                try:
                    score = float(scores.get(field, -1))
                    if score < 0 or score > 100:
                        failures.append(f"{tier}:invalid_score:{field}")
                except (TypeError, ValueError):
                    failures.append(f"{tier}:invalid_score:{field}")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "tiers_checked": list(TIERS),
    }
