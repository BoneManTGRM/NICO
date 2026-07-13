from __future__ import annotations

from typing import Any


_INSTALLED = False


def install_full_scanner_recovery() -> None:
    """Recover a missing persisted scanner record without changing run identity.

    A hosted Full assessment can continue on a different process after the
    initial scanner job was queued. When the referenced scanner record is no
    longer available, the normal handler correctly reports unavailable
    evidence, but the run cannot progress. This wrapper starts one replacement
    scanner bound to the same authorized Full run and returns the new scan ID
    explicitly. The replacement remains queued/running until normal evidence
    attachment observes a completed retained record.
    """

    global _INSTALLED
    if _INSTALLED:
        return

    from nico import full_assessment_orchestrator as orchestrator
    from nico.scanner_worker import start_scan

    original = orchestrator._scanner_worker_handler

    def recovering_scanner_worker_handler(
        context: dict[str, Any], outputs: dict[str, Any]
    ) -> dict[str, Any]:
        result = original(context, outputs)
        scan = result.get("scan") if isinstance(result.get("scan"), dict) else {}
        missing_requested_scan = (
            bool(context.get("scan_id"))
            and result.get("status") == "unavailable"
            and scan.get("status") == "not_found"
        )
        if not missing_requested_scan or not context.get("run_scanners"):
            return result

        replacement = start_scan(
            {
                "repository": context.get("repository") or "",
                "authorized": True,
                "customer_id": context.get("customer_id") or "default_customer",
                "project_id": context.get("project_id") or "default_project",
                "run_id": context.get("run_id") or "",
                "authorized_by": context.get("authorized_by") or "unspecified",
                "authorization_scope": context.get("authorization_scope") or "repository assessment only",
                "tools": context.get("tools") or orchestrator.DEFAULT_FULL_RUN_TOOLS,
            }
        )
        if replacement.get("status") == "blocked" or not replacement.get("scan_id"):
            result.setdefault("evidence", {})["recovery_attempted"] = True
            result["message"] = (
                "Requested scanner run was not found and a same-run replacement "
                "scanner could not be started; completed scanner evidence remains unavailable."
            )
            return result

        return {
            "status": replacement.get("status") or "queued",
            "message": (
                "Requested scanner record was unavailable, so NICO queued one "
                "replacement scanner bound to the same Full run. No scanner "
                "completion credit is granted until retained evidence completes."
            ),
            "scan": replacement,
            "evidence": {
                "run_id": context.get("run_id") or "",
                "missing_scan_id": context.get("scan_id") or "",
                "replacement_scan_id": replacement.get("scan_id") or "",
                "recovery_attempted": True,
                "duplicate_full_run_started": False,
                "tools_requested": replacement.get("tools_requested", []),
            },
        }

    orchestrator._scanner_worker_handler = recovering_scanner_worker_handler
    _INSTALLED = True
