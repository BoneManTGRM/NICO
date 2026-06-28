from __future__ import annotations

from .base import ConnectorPolicy


GITHUB_CONNECTOR_POLICY = ConnectorPolicy(
    name="github",
    allowed_scopes=("repo:read", "pull_request:read", "actions:read"),
    required_role="admin",
    required_approval_level="external_connector_access",
    allowed_operations=("inspect_repository", "inspect_pull_request", "inspect_actions"),
    blocked_operations=("write_repository", "merge_pull_request", "modify_secrets", "deploy"),
    enabled=False,
)
