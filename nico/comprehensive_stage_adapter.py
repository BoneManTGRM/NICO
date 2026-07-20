from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from nico.comprehensive_orchestration_contract import COMPREHENSIVE_STAGES, build_comprehensive_contract

VERSION = "nico.comprehensive_stage_adapter.v1"
TERMINAL_FAILURE_STATES = {"blocked", "failed", "error", "timed_out", "unavailable"}
StageExecutor = Callable[[dict[str, Any]], dict[str, Any]]


@dataclass(frozen=True)
class ComprehensiveIdentity:
    run_id: str
    repository: str
    commit_sha: str
    evidence_ledger_id: str

    def as_dict(self) -> dict[str, str]:
        return {
            "run_id": self.run_id,
            "repository": self.repository,
            "commit_sha": self.commit_sha,
            "evidence_ledger_id": self.evidence_ledger_id,
        }


def _required_text(value: Any, field: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field}_required")
    return normalized


def build_comprehensive_run_state(
    *,
    run_id: str,
    repository: str,
    commit_sha: str,
    evidence_ledger_id: str,
    authorized: bool,
) -> dict[str, Any]:
    identity = ComprehensiveIdentity(
        run_id=_required_text(run_id, "run_id"),
        repository=_required_text(repository, "repository"),
        commit_sha=_required_text(commit_sha, "commit_sha"),
        evidence_ledger_id=_required_text(evidence_ledger_id, "evidence_ledger_id"),
    )
    contract = build_comprehensive_contract(
        repository=identity.repository,
        authorized=authorized,
        commit_sha=identity.commit_sha,
    )
    return {
        "artifact_schema": VERSION,
        "service_id": "comprehensive",
        "status": "blocked" if contract["blockers"] else "ready",
        "identity": identity.as_dict(),
        "contract": contract,
        "current_stage": None,
        "completed_stages": [],
        "stage_results": {},
        "blockers": list(contract["blockers"]),
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def _assert_identity(expected: Mapping[str, str], result: Mapping[str, Any], stage_id: str) -> None:
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        actual = str(result.get(field) or expected[field]).strip()
        if actual != expected[field]:
            raise ValueError(f"{stage_id}:{field}_identity_drift")


def _normalized_stage_result(stage_id: str, raw: dict[str, Any], identity: Mapping[str, str]) -> dict[str, Any]:
    _assert_identity(identity, raw, stage_id)
    status = str(raw.get("status") or "complete").strip().lower()
    return {
        **deepcopy(raw),
        "stage_id": stage_id,
        "status": status,
        "run_id": identity["run_id"],
        "repository": identity["repository"],
        "commit_sha": identity["commit_sha"],
        "evidence_ledger_id": identity["evidence_ledger_id"],
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def run_comprehensive_stages(
    state: dict[str, Any],
    executors: Mapping[str, StageExecutor],
    *,
    stop_after: str | None = None,
) -> dict[str, Any]:
    updated = deepcopy(state)
    identity = updated.get("identity") or {}
    for field in ("run_id", "repository", "commit_sha", "evidence_ledger_id"):
        _required_text(identity.get(field), field)

    if updated.get("service_id") != "comprehensive":
        raise ValueError("service_id_must_be_comprehensive")
    if updated.get("client_delivery_allowed") is not False:
        raise ValueError("client_delivery_must_remain_blocked")
    if updated.get("human_review_required") is not True:
        raise ValueError("human_review_required")
    if updated.get("blockers"):
        updated["status"] = "blocked"
        return updated

    completed = list(updated.get("completed_stages") or [])
    stage_results = dict(updated.get("stage_results") or {})

    for stage_id in COMPREHENSIVE_STAGES:
        if stage_id in completed:
            continue
        executor = executors.get(stage_id)
        if executor is None:
            updated["status"] = "blocked"
            updated["current_stage"] = stage_id
            updated.setdefault("blockers", []).append(f"missing_executor:{stage_id}")
            break

        updated["status"] = "running"
        updated["current_stage"] = stage_id
        context = {
            "service_id": "comprehensive",
            "stage_id": stage_id,
            **identity,
            "prior_stage_results": deepcopy(stage_results),
            "human_review_required": True,
            "client_delivery_allowed": False,
        }
        result = _normalized_stage_result(stage_id, executor(context), identity)
        stage_results[stage_id] = result

        if result["status"] in TERMINAL_FAILURE_STATES:
            updated["status"] = "blocked"
            updated.setdefault("blockers", []).append(f"stage_failed:{stage_id}:{result['status']}")
            break

        completed.append(stage_id)
        updated["completed_stages"] = completed
        updated["stage_results"] = stage_results

        if stop_after == stage_id:
            updated["status"] = "paused"
            break
    else:
        updated["status"] = "review_required"
        updated["current_stage"] = "human_review_request"

    updated["completed_stages"] = completed
    updated["stage_results"] = stage_results
    updated["progress_percent"] = round((len(completed) / len(COMPREHENSIVE_STAGES)) * 100, 2)
    updated["human_review_required"] = True
    updated["client_delivery_allowed"] = False
    return updated


__all__ = [
    "ComprehensiveIdentity",
    "StageExecutor",
    "TERMINAL_FAILURE_STATES",
    "VERSION",
    "build_comprehensive_run_state",
    "run_comprehensive_stages",
]
