from __future__ import annotations

# Import the complete established production chain first. The report provider resolves
# its module-level helper functions at execution time, so the provenance wrapper can be
# installed afterward without being overwritten by a later compatibility installer.
from nico.api.same_run_locale_report_bootstrap import app as production_app
from nico.comprehensive_release_provenance_v1 import (
    comprehensive_release_provenance,
    install_comprehensive_release_provenance,
)
from nico.specialist_access_v1 import install_specialist_access
from nico.specialist_review_session_bridge_v1 import (
    install_specialist_review_session_bridge,
)

VERSION = "nico.api.specialist_ship_ready_bootstrap.v2"
app = production_app
RELEASE_PROVENANCE = install_comprehensive_release_provenance()
SPECIALIST_ACCESS = install_specialist_access(app)
SPECIALIST_REVIEW_SESSION_BRIDGE = install_specialist_review_session_bridge(app)

if RELEASE_PROVENANCE.get("installed") is not True:
    raise RuntimeError("NICO release provenance binding was not installed")
if SPECIALIST_ACCESS.get("installed") is not True:
    raise RuntimeError("NICO specialist access boundary was not installed")
if SPECIALIST_REVIEW_SESSION_BRIDGE.get("installed") is not True:
    raise RuntimeError("NICO specialist review-session bridge was not installed")

# A missing signing secret does not weaken the boundary: every protected request still
# fails closed, and session creation returns 503. Avoid making import-time CI and static
# verification depend on deployment secrets; production diagnostics prove configuration.
def release_provenance_diagnostics():
    return {
        "status": (
            "ready"
            if SPECIALIST_ACCESS.get("session_signing_configured") is True
            else "blocked"
        ),
        "bootstrap_version": VERSION,
        **comprehensive_release_provenance(),
        "specialist_access_installed": SPECIALIST_ACCESS.get("installed") is True,
        "specialist_session_signing_configured": (
            SPECIALIST_ACCESS.get("session_signing_configured") is True
        ),
        "specialist_review_session_bridge_installed": (
            SPECIALIST_REVIEW_SESSION_BRIDGE.get("installed") is True
        ),
        "protected_requests_fail_closed_without_session_signing": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


app.add_api_route(
    "/diagnostics/nico-release-provenance",
    release_provenance_diagnostics,
    methods=["GET"],
    tags=["diagnostics"],
)
app.openapi_schema = None
app.state.nico_release_provenance = RELEASE_PROVENANCE
app.state.nico_specialist_access = SPECIALIST_ACCESS
app.state.nico_specialist_review_session_bridge = SPECIALIST_REVIEW_SESSION_BRIDGE
app.state.nico_specialist_ship_ready_bootstrap_version = VERSION

__all__ = [
    "app",
    "VERSION",
    "RELEASE_PROVENANCE",
    "SPECIALIST_ACCESS",
    "SPECIALIST_REVIEW_SESSION_BRIDGE",
]
