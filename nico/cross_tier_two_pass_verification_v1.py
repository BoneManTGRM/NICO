from __future__ import annotations

from copy import deepcopy
from typing import Any, Iterable, Mapping

VERSION = "cross_tier_two_pass_verification_v1"
TIERS = ("express", "mid", "full")
_REQUIRED_CHECKS = (
    "tests_passed",
    "security_passed",
    "build_passed",
    "render_qa_passed",
    "identity_invariants_passed",
    "deployment_sha_aligned",
)


def _record(value: Any) -> dict[str, Any]:
    return deepcopy(dict(value)) if isinstance(value, Mapping) else {}


def verify_two_consecutive_release_passes(
    passes: Iterable[Mapping[str, Any]],
    *,
    expected_commit_sha: str,
) -> dict[str, Any]:
    """Require two consecutive, complete, same-commit clean passes for every tier."""
    records = [_record(item) for item in passes]
    issues: list[str] = []
    expected = str(expected_commit_sha or "").strip()

    if not expected:
        issues.append("missing_expected_commit_sha")
    if len(records) != 2:
        issues.append("exactly_two_passes_required")

    pass_summaries: list[dict[str, Any]] = []
    for index, record in enumerate(records[:2], start=1):
        pass_issues: list[str] = []
        commit_sha = str(record.get("commit_sha") or "").strip()
        if not commit_sha:
            pass_issues.append("missing_commit_sha")
        elif expected and commit_sha != expected:
            pass_issues.append("commit_sha_mismatch")

        tiers = _record(record.get("tiers"))
        for tier in TIERS:
            tier_record = _record(tiers.get(tier))
            if not tier_record:
                pass_issues.append(f"missing_{tier}_record")
                continue
            for check in _REQUIRED_CHECKS:
                if tier_record.get(check) is not True:
                    pass_issues.append(f"{tier}_{check}_failed")
            if tier_record.get("client_delivery_allowed") is not True:
                pass_issues.append(f"{tier}_delivery_not_allowed")

        clean = not pass_issues
        pass_summaries.append({
            "pass_number": index,
            "commit_sha": commit_sha or None,
            "clean": clean,
            "issues": pass_issues,
        })
        issues.extend(f"pass_{index}:{issue}" for issue in pass_issues)

    if len(pass_summaries) == 2:
        first_sha = pass_summaries[0].get("commit_sha")
        second_sha = pass_summaries[1].get("commit_sha")
        if first_sha != second_sha:
            issues.append("verification_pass_sha_mismatch")

    allowed = len(records) == 2 and not issues and all(item["clean"] for item in pass_summaries)
    return {
        "version": VERSION,
        "expected_commit_sha": expected or None,
        "required_passes": 2,
        "completed_passes": len(records),
        "tiers": list(TIERS),
        "required_checks": list(_REQUIRED_CHECKS),
        "passes": pass_summaries,
        "issues": issues,
        "release_verified": allowed,
        "client_delivery_allowed": allowed,
    }


__all__ = ["TIERS", "VERSION", "verify_two_consecutive_release_passes"]
