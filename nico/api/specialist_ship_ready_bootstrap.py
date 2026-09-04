from __future__ import annotations

from nico.comprehensive_release_provenance_v1 import (
    install_comprehensive_release_provenance,
)

# Install the deterministic report provenance boundary before the established
# production bootstrap imports and captures report builders.
RELEASE_PROVENANCE = install_comprehensive_release_provenance()

from nico.api.same_run_locale_report_bootstrap import app as production_app  # noqa: E402
from nico.specialist_access_v1 import install_specialist_access  # noqa: E402

app = production_app
SPECIALIST_ACCESS = install_specialist_access(app)

if RELEASE_PROVENANCE.get("installed") is not True:
    raise RuntimeError("NICO release provenance binding was not installed")
if SPECIALIST_ACCESS.get("installed") is not True:
    raise RuntimeError("NICO specialist access boundary was not installed")
if SPECIALIST_ACCESS.get("session_signing_configured") is not True:
    raise RuntimeError("NICO specialist session signing is not configured")

app.state.nico_release_provenance = RELEASE_PROVENANCE
app.state.nico_specialist_access = SPECIALIST_ACCESS

__all__ = ["app", "RELEASE_PROVENANCE", "SPECIALIST_ACCESS"]
