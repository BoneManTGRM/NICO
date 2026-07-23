from __future__ import annotations

from nico.api.comprehensive_production_bootstrap import app
from nico.exact_commit_binding import install_exact_commit_binding
from nico.express_terminal_authority import install_express_terminal_authority

VERSION = "nico.api.terminal_authority_bootstrap.v2"
EXACT_COMMIT_BINDING = install_exact_commit_binding()
EXPRESS_TERMINAL_AUTHORITY = install_express_terminal_authority()
app.state.nico_exact_commit_binding = EXACT_COMMIT_BINDING
app.state.nico_express_terminal_authority = EXPRESS_TERMINAL_AUTHORITY

if EXACT_COMMIT_BINDING.get("status") != "installed":
    raise RuntimeError(f"Exact commit binding did not install: {EXACT_COMMIT_BINDING}")
if EXACT_COMMIT_BINDING.get("repository_files_bound_to_exact_commit") is not True:
    raise RuntimeError("Repository file evidence is not bound to the exact immutable commit")
if EXACT_COMMIT_BINDING.get("scanner_bound_to_exact_commit") is not True:
    raise RuntimeError("Scanner execution is not bound to the exact immutable commit")
if EXACT_COMMIT_BINDING.get("conflicting_commit_metadata_authoritative") is not False:
    raise RuntimeError("Conflicting derived commit metadata can still replace verified commit truth")
if EXACT_COMMIT_BINDING.get("human_review_required") is not True:
    raise RuntimeError("Exact commit binding must preserve required human review")
if EXACT_COMMIT_BINDING.get("client_delivery_allowed") is not False:
    raise RuntimeError("Exact commit binding must block client delivery")

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

__all__ = ["app", "EXACT_COMMIT_BINDING", "EXPRESS_TERMINAL_AUTHORITY", "VERSION"]
