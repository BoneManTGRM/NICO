from __future__ import annotations

APPROVAL_GATED_ACTIONS = {
    "production_mutation",
    "dependency_upgrade",
    "external_connector_access",
    "report_export",
    "secret_usage",
    "repo_setting_change",
    "hosted_saas_behavior",
    "high_risk_swarm_action",
}


def approval_required(action: str, risk_level: str = "low") -> bool:
    return action in APPROVAL_GATED_ACTIONS or risk_level in {"high", "critical"}
