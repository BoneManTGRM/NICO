from __future__ import annotations

from .github import GITHUB_CONNECTOR_POLICY

CONNECTOR_POLICIES = {"github": GITHUB_CONNECTOR_POLICY}


def get_connector_policy(name: str):
    return CONNECTOR_POLICIES.get(name)
