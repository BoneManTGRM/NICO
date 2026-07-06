from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.storage import STORE


def _repo_key(value: Any) -> str:
    return str(value or "").strip().lower().removesuffix(".git")


def _completed_runs(repository: str, customer_id: str, project_id: str) -> list[dict[str, Any]]:
    repo = _repo_key(repository)
    runs: list[dict[str, Any]] = []
    for item in STORE.list("scanner_runs"):
        if not isinstance(item, dict):
            continue
        if item.get("status") != "complete" or not item.get("scanner_results"):
            continue
        if _repo_key(item.get("repository")) != repo:
            continue
        if customer_id and item.get("customer_id") not in {customer_id, None, ""}:
            continue
        if project_id and item.get("project_id") not in {project_id, None, ""}:
            continue
        runs.append(item)
    runs.sort(key=lambda item: str(item.get("completed_at") or item.get("updated_at") or item.get("created_at") or ""), reverse=True)
    return runs


def attach_existing_worker_evidence(result: dict[str, Any], request: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(result)
    if output.get("status") != "complete":
        output["worker_evidence_attachment"] = {"status": "not_started", "reason": "Assessment was not complete."}
        return output
    if not request.get("authorized"):
        output["worker_evidence_attachment"] = {"status": "blocked", "reason": "Evidence attachment requires explicit authorization."}
        return output

    repository = request.get("repository") or output.get("repository") or ""
    customer_id = request.get("customer_id") or "default_customer"
    project_id = request.get("project_id") or "default_project"
    runs = _completed_runs(repository, customer_id, project_id)
    if not runs:
        output["worker_evidence_attachment"] = {
            "status": "unavailable",
            "mode": "existing_completed_worker_evidence_only",
            "reason": "No completed worker evidence was available for this repository/project at assessment time.",
            "human_review_required": True,
        }
        output.setdefault("unavailable_data_notes", []).append("No completed worker evidence was available to attach to this Express assessment. Run the worker, then rerun or create a report package before worker-backed claims.")
        return output

    run = runs[0]
    output["scanner_run"] = run
    output["scanner_results"] = run.get("scanner_results", [])
    output["worker_evidence_attachment"] = {
        "status": "complete",
        "scan_id": run.get("scan_id"),
        "mode": "existing_completed_worker_evidence_only",
        "completed_at": run.get("completed_at"),
        "human_review_required": True,
    }
    output.setdefault("evidence_readiness", {})["existing_worker_evidence_attached"] = True
    return output
