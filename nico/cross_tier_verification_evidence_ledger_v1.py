from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from nico.cross_tier_two_pass_verification_v1 import TIERS, verify_two_consecutive_release_passes

VERSION = "cross_tier_verification_evidence_ledger_v1"
_REQUIRED_ENVIRONMENTS = ("staging", "production")
_REQUIRED_ARTIFACT_FORMATS = ("pdf", "html", "markdown")


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _parse_timestamp(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def build_cross_tier_verification_evidence_ledger(
    passes: Iterable[Mapping[str, Any]],
    *,
    expected_commit_sha: str,
) -> dict[str, Any]:
    """Bind two clean release passes to immutable deployment and artifact evidence."""
    records = [_record(item) for item in passes]
    base = verify_two_consecutive_release_passes(records, expected_commit_sha=expected_commit_sha)
    issues = list(base["issues"])
    evidence_passes: list[dict[str, Any]] = []
    prior_completed_at: datetime | None = None

    for index, record in enumerate(records[:2], start=1):
        pass_issues: list[str] = []
        completed_at = _parse_timestamp(record.get("completed_at"))
        if completed_at is None:
            pass_issues.append("missing_or_invalid_completed_at")
        elif prior_completed_at is not None and completed_at <= prior_completed_at:
            pass_issues.append("non_consecutive_timestamp")
        if completed_at is not None:
            prior_completed_at = completed_at

        environments = _record(record.get("environments"))
        environment_summary: dict[str, Any] = {}
        for environment in _REQUIRED_ENVIRONMENTS:
            environment_record = _record(environments.get(environment))
            deployment_id = str(environment_record.get("deployment_id") or "").strip()
            deployed_sha = str(environment_record.get("commit_sha") or "").strip()
            healthy = environment_record.get("healthy") is True
            if not deployment_id:
                pass_issues.append(f"missing_{environment}_deployment_id")
            if deployed_sha != str(expected_commit_sha or "").strip():
                pass_issues.append(f"{environment}_deployment_sha_mismatch")
            if not healthy:
                pass_issues.append(f"{environment}_not_healthy")
            environment_summary[environment] = {
                "deployment_id": deployment_id or None,
                "commit_sha": deployed_sha or None,
                "healthy": healthy,
            }

        tiers = _record(record.get("tiers"))
        tier_summary: dict[str, Any] = {}
        for tier in TIERS:
            tier_record = _record(tiers.get(tier))
            artifacts = _record(tier_record.get("artifacts"))
            format_summary: dict[str, Any] = {}
            for artifact_format in _REQUIRED_ARTIFACT_FORMATS:
                artifact = _record(artifacts.get(artifact_format))
                artifact_id = str(artifact.get("artifact_id") or "").strip()
                checksum = str(artifact.get("sha256") or "").strip().lower()
                if not artifact_id:
                    pass_issues.append(f"{tier}_{artifact_format}_missing_artifact_id")
                if len(checksum) != 64 or any(character not in "0123456789abcdef" for character in checksum):
                    pass_issues.append(f"{tier}_{artifact_format}_invalid_sha256")
                format_summary[artifact_format] = {
                    "artifact_id": artifact_id or None,
                    "sha256": checksum or None,
                }
            tier_summary[tier] = {"artifacts": format_summary}

        clean = not pass_issues
        evidence_passes.append({
            "pass_number": index,
            "completed_at": completed_at.isoformat().replace("+00:00", "Z") if completed_at else None,
            "environments": environment_summary,
            "tiers": tier_summary,
            "clean": clean,
            "issues": pass_issues,
        })
        issues.extend(f"evidence_pass_{index}:{issue}" for issue in pass_issues)

    verified = base["release_verified"] is True and len(records) == 2 and not issues
    return {
        "version": VERSION,
        "expected_commit_sha": str(expected_commit_sha or "").strip() or None,
        "required_environments": list(_REQUIRED_ENVIRONMENTS),
        "required_artifact_formats": list(_REQUIRED_ARTIFACT_FORMATS),
        "base_verification": base,
        "evidence_passes": evidence_passes,
        "issues": issues,
        "release_evidence_verified": verified,
        "client_delivery_allowed": verified,
    }


__all__ = ["VERSION", "build_cross_tier_verification_evidence_ledger"]
