from __future__ import annotations

from typing import Any

from nico.comprehensive_api_controller import ComprehensiveApiController
from nico.comprehensive_run_service import ComprehensiveRunService

VERSION = "nico.comprehensive_exact_sha_recovery.v1"


def recover_and_continue(
    controller: ComprehensiveApiController,
    *,
    run_id: str,
    recovery: dict[str, Any],
    max_stages: int | None,
) -> dict[str, Any]:
    """Reconstruct a missing run from immutable identity and deterministic replay.

    The recovery payload never carries stage outputs. It identifies the exact commit and
    the ordered stage prefix that the browser previously observed. The service executes
    that prefix again, then advances by the caller's normal continuation budget.
    """

    service = getattr(controller, "_service", None)
    if not isinstance(service, ComprehensiveRunService):
        raise RuntimeError("comprehensive_recovery_service_unavailable")

    record = service.recover_exact_sha(
        run_id=run_id,
        repository=str(recovery["repository"]),
        commit_sha=str(recovery["commit_sha"]),
        evidence_ledger_id=str(recovery["evidence_ledger_id"]),
        customer_id=str(recovery["customer_id"]),
        project_id=str(recovery["project_id"]),
        completed_stages=[str(item) for item in recovery.get("completed_stages") or []],
        authorized=True,
    )
    if not record.get("terminal"):
        record = service.resume(run_id, max_stages=max_stages)

    response = controller._response(record, operation="recovered_and_continued")
    response["recovery"] = {
        "artifact_schema": VERSION,
        "mode": "exact_sha_stage_replay",
        "identity_revalidated": True,
        "stage_outputs_accepted_from_client": False,
        "replayed_stage_count": len(recovery.get("completed_stages") or []),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return response


__all__ = ["VERSION", "recover_and_continue"]