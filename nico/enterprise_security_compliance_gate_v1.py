"""Fail-closed enterprise security and compliance qualification."""

from __future__ import annotations

from typing import Any, Mapping

REQUIRED_CONTROLS = (
    "authorization_scope_documented",
    "least_privilege_enforced",
    "secrets_scanning_enabled",
    "dependency_scanning_enabled",
    "code_scanning_enabled",
    "audit_logging_enabled",
    "retention_policy_documented",
    "incident_response_documented",
    "backup_restore_tested",
    "data_deletion_tested",
    "tenant_isolation_verified",
    "encryption_in_transit_verified",
    "encryption_at_rest_verified",
    "subprocessor_inventory_current",
    "security_contact_published",
)


def qualify_enterprise_security_compliance(
    evidence: Mapping[str, Any], *, prior_release_allowed: bool = True
) -> dict[str, Any]:
    """Block enterprise release unless every required control has evidence."""
    failures: list[str] = []
    if not prior_release_allowed:
        failures.append("prior_release_block")

    for control in REQUIRED_CONTROLS:
        if control not in evidence:
            failures.append(f"missing:{control}")
        elif evidence[control] is not True:
            failures.append(f"failed:{control}")

    if not str(evidence.get("reviewer", "")).strip():
        failures.append("missing:reviewer")
    if not str(evidence.get("reviewed_commit_sha", "")).strip():
        failures.append("missing:reviewed_commit_sha")
    if int(evidence.get("open_critical_findings", 1)) != 0:
        failures.append("open_critical_findings")
    if int(evidence.get("open_high_findings", 1)) != 0:
        failures.append("open_high_findings")

    unique = sorted(set(failures))
    return {
        "status": "qualified" if not unique else "blocked",
        "delivery_allowed": not unique,
        "failures": unique,
        "controls_checked": list(REQUIRED_CONTROLS),
    }
