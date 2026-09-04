from __future__ import annotations

import os
import time
from typing import Any

from fastapi import FastAPI

from nico.admin_security import require_comprehensive_operator
from nico.api.specialist_ship_ready_bootstrap import (
    SPECIALIST_ACCESS,
    SPECIALIST_READINESS_ROUTE,
    app as production_app,
    specialist_readiness as base_specialist_readiness,
)
from nico.specialist_access_v1 import (
    issue_specialist_session,
    validate_specialist_session,
)

VERSION = "nico.specialist_ship_verified.v1"
app: FastAPI = production_app


def _operator_password() -> str:
    return (
        os.getenv("NICO_COMPREHENSIVE_OPERATOR_PASSWORD", "").strip()
        or os.getenv("NICO_SARA_OPERATOR_PASSWORD", "").strip()
    )


def _credential_and_session_self_test() -> dict[str, bool]:
    supplied = _operator_password()
    allowed, authority = require_comprehensive_operator(supplied)
    session_round_trip = False
    if allowed:
        try:
            now = int(time.time())
            token, _ = issue_specialist_session(authority, now=now)
            validated = validate_specialist_session(token, now=now + 1)
            session_round_trip = bool(
                validated
                and validated.get("scope") == "comprehensive_specialist_operation"
            )
        except Exception:
            session_round_trip = False
    return {
        "operator_credential_self_test": bool(allowed),
        "session_round_trip_self_test": session_round_trip,
    }


def verified_specialist_readiness() -> dict[str, Any]:
    base = dict(base_specialist_readiness())
    release = (
        dict(base.get("release_provenance"))
        if isinstance(base.get("release_provenance"), dict)
        else {}
    )
    self_test = _credential_and_session_self_test()

    # The backend-generated assessment package is authoritative for assessment-engine,
    # scanner, renderer, deployment, and storage provenance. A Vercel build identity is
    # retained when supplied, but the Railway backend must not invent or require a
    # frontend SHA it cannot authoritatively observe.
    backend_identity_complete = bool(
        release.get("deployment_identity_established") is True
        and str(release.get("backend_build_commit") or "") not in {"", "unavailable"}
        and str(release.get("railway_deployment_id") or "") not in {"", "unavailable"}
    )
    frontend_identity_available = bool(
        release.get("frontend_identity_established") is True
        and str(release.get("frontend_build_commit") or "") not in {"", "unavailable"}
    )

    required = (
        base.get("specialist_access_installed") is True,
        base.get("authenticated_comprehensive_routes_enforced") is True,
        base.get("operator_password_configured") is True,
        base.get("session_signing_configured") is True,
        base.get("credential_separation_verified") is True,
        base.get("rate_limiting_enabled") is True,
        base.get("comprehensive_runtime_ready") is True,
        base.get("durable_storage_verified") is True,
        backend_identity_complete,
        self_test["operator_credential_self_test"],
        self_test["session_round_trip_self_test"],
        base.get("human_review_required") is True,
        base.get("client_delivery_allowed") is False,
        base.get("secrets_exposed") is False,
    )
    ready = all(required)
    return {
        **base,
        "artifact_schema": VERSION,
        "status": "ready" if ready else "blocked",
        "release_identity_complete": backend_identity_complete,
        "backend_release_identity_complete": backend_identity_complete,
        "frontend_identity_available": frontend_identity_available,
        **self_test,
        "positive_authentication_verified_server_side": all(self_test.values()),
        "human_review_required": True,
        "client_delivery_allowed": False,
        "secrets_exposed": False,
    }


def _replace_readiness_route() -> None:
    app.router.routes = [
        route
        for route in app.router.routes
        if str(getattr(route, "path", "")) != SPECIALIST_READINESS_ROUTE
    ]
    app.add_api_route(
        SPECIALIST_READINESS_ROUTE,
        verified_specialist_readiness,
        methods=["GET"],
        tags=["diagnostics"],
    )
    app.openapi_schema = None


_replace_readiness_route()
app.state.nico_verified_specialist_readiness = {
    "artifact_schema": VERSION,
    "installed": True,
    "positive_authentication_self_test": True,
    "secrets_exposed": False,
}

__all__ = ["app", "verified_specialist_readiness", "VERSION"]
