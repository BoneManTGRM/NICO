from __future__ import annotations

from typing import Any

_MARKER = "_nico_express_async_contract_metadata_v2"


def install_express_async_contract_metadata() -> dict[str, Any]:
    from nico import express_async_api
    from nico.express_report_generation_recovery import install_express_report_generation_recovery

    report_recovery = install_express_report_generation_recovery()
    current = express_async_api.register_express_async_routes
    if getattr(current, _MARKER, False):
        return {"status": "already_installed", "report_generation_recovery": report_recovery}

    def register_with_contract_metadata(app):
        result = dict(current(app))
        result.update(
            {
                "single_long_browser_connection_required": False,
                "exact_run_polling": True,
                "duplicate_active_scope_start_prevented": True,
                "max_active_runs": express_async_api.MAX_ACTIVE_EXPRESS_RUNS,
                "staged_progress_available": True,
                "progress_source": "backend_stage_records",
                "report_generation_recovery": report_recovery,
            }
        )
        return result

    setattr(register_with_contract_metadata, _MARKER, True)
    setattr(register_with_contract_metadata, "_nico_previous", current)
    express_async_api.register_express_async_routes = register_with_contract_metadata
    return {
        "status": "installed",
        "staged_progress_available": True,
        "report_generation_recovery": report_recovery,
    }


__all__ = ["install_express_async_contract_metadata"]
