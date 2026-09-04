from __future__ import annotations

import hmac
import os
from typing import Any

from nico.comprehensive_approved_lifecycle_consistency_v1 import (
    install_approved_lifecycle_consistency,
)
from nico.comprehensive_release_provenance_v1 import (
    comprehensive_release_provenance,
    install_comprehensive_release_provenance,
)

# Install deterministic report boundaries before the established production
# bootstrap imports and captures report builders.
APPROVED_LIFECYCLE_CONSISTENCY = install_approved_lifecycle_consistency()
RELEASE_PROVENANCE = install_comprehensive_release_provenance()

from nico.api.same_run_locale_report_bootstrap import app as production_app  # noqa: E402
from nico.github_actions_proof_session_v1 import (  # noqa: E402
    install_github_actions_proof_session,
)
from nico.specialist_access_v1 import (  # noqa: E402
    SESSION_SIGNING_SECRET_ENV,
    install_specialist_access,
)
from nico.specialist_review_session_bridge_v1 import (  # noqa: E402
    install_specialist_review_session_bridge,
)

SPECIALIST_READINESS_ROUTE = "/diagnostics/specialist-readiness"
app = production_app
SPECIALIST_ACCESS = install_specialist_access(app)
GITHUB_ACTIONS_PROOF_SESSION = install_github_actions_proof_session(app)
REVIEW_SESSION_BRIDGE = install_specialist_review_session_bridge(app)

if APPROVED_LIFECYCLE_CONSISTENCY.get("installed") is not True:
    raise RuntimeError("NICO approved lifecycle consistency binding was not installed")
if RELEASE_PROVENANCE.get("installed") is not True:
    raise RuntimeError("NICO release provenance binding was not installed")
if SPECIALIST_ACCESS.get("installed") is not True:
    raise RuntimeError("NICO specialist access boundary was not installed")
if GITHUB_ACTIONS_PROOF_SESSION.get("installed") is not True:
    raise RuntimeError("NICO GitHub Actions proof-session boundary was not installed")
if REVIEW_SESSION_BRIDGE.get("installed") is not True:
    raise RuntimeError("NICO specialist review-session bridge was not installed")


def _route_count(path: str) -> int:
    return sum(1 for route in app.routes if str(getattr(route, "path", "")) == path)


def _configured_credentials() -> dict[str, str]:
    return {
        "admin": os.getenv("NICO_ADMIN_TOKEN", "").strip(),
        "operator": os.getenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "").strip(),
        "legacy_operator": os.getenv("NICO_SARA_OPERATOR_PASSWORD", "").strip(),
        "session_signing": os.getenv(SESSION_SIGNING_SECRET_ENV, "").strip(),
    }


def _distinct_nonempty(values: list[str]) -> bool:
    supplied = [value for value in values if value]
    return all(
        not hmac.compare_digest(left, right)
        for index, left in enumerate(supplied)
        for right in supplied[index + 1 :]
    )


def specialist_readiness() -> dict[str, Any]:
    credentials = _configured_credentials()
    credential_separation = _distinct_nonempty(
        [
            credentials["admin"],
            credentials["operator"],
            credentials["legacy_operator"],
            credentials["session_signing"],
        ]
    )
    release = comprehensive_release_provenance()
    runtime = dict(getattr(app.state, "nico_comprehensive_production_runtime", {}) or {})
    runtime_ready = (
        runtime.get("status") == "ready"
        and runtime.get("survives_container_replacement_verified") is True
        and runtime.get("human_review_required") is True
        and runtime.get("client_delivery_allowed") is False
    )
    session_signing_configured = SPECIALIST_ACCESS.get("session_signing_configured") is True
    generic_operator_password_configured = bool(credentials["operator"])
    review_session_bridge_installed = REVIEW_SESSION_BRIDGE.get("installed") is True
    github_actions_proof_installed = GITHUB_ACTIONS_PROOF_SESSION.get("installed") is True
    approved_lifecycle_consistency_installed = (
        APPROVED_LIFECYCLE_CONSISTENCY.get("installed") is True
        and APPROVED_LIFECYCLE_CONSISTENCY.get("cross_format_fail_closed") is True
    )
    release_identity_complete = (
        release.get("deployment_identity_established") is True
        and release.get("frontend_identity_established") is True
    )
    ready = all(
        (
            SPECIALIST_ACCESS.get("installed") is True,
            session_signing_configured,
            generic_operator_password_configured,
            credential_separation,
            review_session_bridge_installed,
            github_actions_proof_installed,
            approved_lifecycle_consistency_installed,
            runtime_ready,
            release_identity_complete,
        )
    )
    return {
        "artifact_schema": "nico.specialist_ship_readiness.v1",
        "status": "ready" if ready else "blocked",
        "specialist_access_installed": SPECIALIST_ACCESS.get("installed") is True,
        "authenticated_comprehensive_routes_enforced": True,
        "signed_review_sessions_enforced": review_session_bridge_installed,
        "github_actions_production_proof_enabled": github_actions_proof_installed,
        "github_actions_proof_exact_release_bound": GITHUB_ACTIONS_PROOF_SESSION.get("exact_release_bound") is True,
        "github_actions_proof_workflow_allowlist_bound": GITHUB_ACTIONS_PROOF_SESSION.get("workflow_allowlist_bound") is True,
        "approved_lifecycle_consistency_enforced": approved_lifecycle_consistency_installed,
        "operator_password_configured": generic_operator_password_configured,
        "generic_operator_password_configured": generic_operator_password_configured,
        "legacy_operator_password_configured": bool(credentials["legacy_operator"]),
        "specialist_credential_migration_complete": generic_operator_password_configured,
        "session_signing_configured": session_signing_configured,
        "credential_separation_verified": credential_separation,
        "session_cookie_http_only": True,
        "session_cookie_same_site": "strict",
        "rate_limiting_enabled": SPECIALIST_ACCESS.get("rate_limiting") is True,
        "comprehensive_runtime_ready": runtime_ready,
        "durable_storage_verified": runtime.get("survives_container_replacement_verified") is True,
        "release_identity_complete": release_identity_complete,
        "release_provenance": release,
        "human_review_required": True,
        "client_delivery_allowed": False,
        "secrets_exposed": False,
    }


if _route_count(SPECIALIST_READINESS_ROUTE) == 0:
    app.add_api_route(
        SPECIALIST_READINESS_ROUTE,
        specialist_readiness,
        methods=["GET"],
        tags=["diagnostics"],
    )
    app.openapi_schema = None

# A secret-free test import remains possible, but every protected assessment route
# still fails closed and browser session creation returns 503 until deployment
# credentials establish a signing key. Production verification must prove readiness.
app.state.nico_approved_lifecycle_consistency = APPROVED_LIFECYCLE_CONSISTENCY
app.state.nico_release_provenance = RELEASE_PROVENANCE
app.state.nico_specialist_access = SPECIALIST_ACCESS
app.state.nico_github_actions_proof_session = GITHUB_ACTIONS_PROOF_SESSION
app.state.nico_specialist_review_session_bridge = REVIEW_SESSION_BRIDGE

__all__ = [
    "app",
    "APPROVED_LIFECYCLE_CONSISTENCY",
    "RELEASE_PROVENANCE",
    "SPECIALIST_ACCESS",
    "GITHUB_ACTIONS_PROOF_SESSION",
    "REVIEW_SESSION_BRIDGE",
    "SPECIALIST_READINESS_ROUTE",
    "specialist_readiness",
]
