from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VERSION = "cross_tier_release_invariants_v1"
TIERS = ("express", "mid", "full")
FORMATS = ("pdf", "html", "markdown")


def _mapping(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def _text(value: Any) -> str:
    return " ".join(str(value or "").split())


def validate_cross_tier_release(
    release: Mapping[str, Any],
    *,
    expected_tier: str,
    expected_assessment_id: str,
    expected_repository_id: str,
    expected_snapshot_sha: str,
    expected_evidence_packet_id: str,
    expected_locale: str,
) -> dict[str, Any]:
    """Validate common release truth across Express, Mid, and Full artifacts."""
    data = _mapping(release)
    issues: list[str] = []
    tier = _text(data.get("tier")).lower()
    assessment_id = _text(data.get("assessment_id"))
    repository_id = _text(data.get("repository_id"))
    snapshot_sha = _text(data.get("snapshot_sha"))
    evidence_packet_id = _text(data.get("evidence_packet_id"))
    locale = _text(data.get("locale")).lower()
    canonical_score = data.get("canonical_score")
    displayed_score = data.get("displayed_score")
    automated_complete = bool(data.get("automated_complete"))
    human_approved = bool(data.get("human_approved"))
    revoked = bool(data.get("revoked"))
    approval = _mapping(data.get("approval"))
    artifacts = _mapping(data.get("artifacts"))

    if tier not in TIERS:
        issues.append("unsupported_tier")
    elif tier != _text(expected_tier).lower():
        issues.append("tier_identity_mismatch")
    if assessment_id != _text(expected_assessment_id):
        issues.append("assessment_identity_mismatch")
    if repository_id != _text(expected_repository_id):
        issues.append("repository_identity_mismatch")
    if snapshot_sha != _text(expected_snapshot_sha):
        issues.append("snapshot_identity_mismatch")
    if evidence_packet_id != _text(expected_evidence_packet_id):
        issues.append("evidence_packet_identity_mismatch")
    if locale != _text(expected_locale).lower():
        issues.append("locale_identity_mismatch")

    if canonical_score is None:
        issues.append("missing_canonical_score")
    if displayed_score != canonical_score:
        issues.append("score_reconciliation_failure")
    if not automated_complete:
        issues.append("automation_incomplete")
    if not human_approved:
        issues.append("human_approval_missing")
    if revoked:
        issues.append("approval_revoked")
    if human_approved:
        if not _text(approval.get("reviewer_id")):
            issues.append("missing_approval_reviewer")
        if not _text(approval.get("approved_at")):
            issues.append("missing_approval_timestamp")

    for report_format in FORMATS:
        artifact = _mapping(artifacts.get(report_format))
        if not artifact:
            issues.append(f"missing_{report_format}_artifact")
            continue
        if _text(artifact.get("assessment_id")) != assessment_id:
            issues.append(f"{report_format}_assessment_mismatch")
        if _text(artifact.get("snapshot_sha")) != snapshot_sha:
            issues.append(f"{report_format}_snapshot_mismatch")
        if _text(artifact.get("evidence_packet_id")) != evidence_packet_id:
            issues.append(f"{report_format}_evidence_packet_mismatch")
        if _text(artifact.get("tier")).lower() != tier:
            issues.append(f"{report_format}_tier_mismatch")
        if _text(artifact.get("locale")).lower() != locale:
            issues.append(f"{report_format}_locale_mismatch")
        if not _text(artifact.get("artifact_id")):
            issues.append(f"missing_{report_format}_artifact_id")
        checksum = _text(artifact.get("sha256"))
        if len(checksum) != 64 or any(character not in "0123456789abcdefABCDEF" for character in checksum):
            issues.append(f"invalid_{report_format}_sha256")

    allowed = not issues
    return {
        "version": VERSION,
        "tier": tier,
        "assessment_id": assessment_id,
        "issues": issues,
        "all_invariants_passed": allowed,
        "client_delivery_allowed": allowed,
    }


def attach_cross_tier_release_invariants(
    result: dict[str, Any],
    **expected: str,
) -> dict[str, Any]:
    decision = validate_cross_tier_release(result, **expected)
    result["cross_tier_release_invariants"] = decision
    result["client_delivery_allowed"] = bool(result.get("client_delivery_allowed")) and decision["client_delivery_allowed"]
    return result


__all__ = [
    "FORMATS",
    "TIERS",
    "VERSION",
    "attach_cross_tier_release_invariants",
    "validate_cross_tier_release",
]
