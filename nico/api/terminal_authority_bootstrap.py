from __future__ import annotations

from nico.api.comprehensive_production_bootstrap import app
from nico.express_terminal_authority import install_express_terminal_authority

VERSION = "nico.api.terminal_authority_bootstrap.v1"
EXPRESS_TERMINAL_AUTHORITY = install_express_terminal_authority()
app.state.nico_express_terminal_authority = EXPRESS_TERMINAL_AUTHORITY

if EXPRESS_TERMINAL_AUTHORITY.get("status") != "installed":
    raise RuntimeError(f"Express terminal authority did not install: {EXPRESS_TERMINAL_AUTHORITY}")
if EXPRESS_TERMINAL_AUTHORITY.get("compact_terminal_precedes_rich_record") is not True:
    raise RuntimeError("Express compact terminal evidence is not persisted before the rich record")
if EXPRESS_TERMINAL_AUTHORITY.get("exact_run_readback_required") is not True:
    raise RuntimeError("Express exact-run terminal readback is not required")
if EXPRESS_TERMINAL_AUTHORITY.get("browser_terminalization_from_active_status_allowed") is not False:
    raise RuntimeError("Active backend status can still be terminalized by the browser")
if EXPRESS_TERMINAL_AUTHORITY.get("human_review_required") is not True:
    raise RuntimeError("Express terminal authority must require human review")
if EXPRESS_TERMINAL_AUTHORITY.get("client_delivery_allowed") is not False:
    raise RuntimeError("Express terminal authority must block client delivery")

__all__ = ["app", "EXPRESS_TERMINAL_AUTHORITY", "VERSION"]
