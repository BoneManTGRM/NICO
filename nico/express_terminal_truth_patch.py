from __future__ import annotations

from copy import deepcopy
from typing import Any, Callable, Iterable

from nico import lifecycle_status_hardening as hardening
from nico.storage import STORE

VERSION = "nico.express_terminal_truth.v1"
_PATCH_MARKER = "_nico_express_terminal_truth_v1"
_TERMINAL = {"complete", "completed", "succeeded", "success", "failed", "error", "cancelled", "canceled", "blocked", "skipped", "not_applicable"}
_ACTIVE = {"queued", "pending", "starting", "running", "finalizing", "reviewing", "in_progress"}
_GATE_NAMES = {"truth and review gates", "truth_review_gates", "truth-and-review-gates"}
_SCANNER_NAMES = {"scanner worker evidence", "scanner_worker_evidence", "scanner-worker-evidence"}


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").replace("-", " ").split())


def _status(item: dict[str, Any]) -> str:
    return _text(item.get("status") or item.get("state") or item.get("phase"))


def _iter_step_lists(value: Any) -> Iterable[list[Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            if key in {"steps", "progress_steps", "timeline", "stages", "workflow_steps"} and isinstance(child, list):
                yield child
            yield from _iter_step_lists(child)
    elif isinstance(value, list):
        for child in value:
            yield from _iter_step_lists(child)


def _named(item: dict[str, Any]) -> str:
    return _text(item.get("name") or item.get("title") or item.get("label") or item.get("id") or item.get("key"))


def _required_gate_nonterminal(payload: dict[str, Any]) -> bool:
    for steps in _iter_step_lists(payload):
        for raw in steps:
            if not isinstance(raw, dict):
                continue
            name = _named(raw)
            if name in {_text(value) for value in _GATE_NAMES}:
                status = _status(raw)
                if status in _ACTIVE or status not in _TERMINAL:
                    return True
    return False


def _storage_truth() -> dict[str, Any]:
    try:
        status = dict(STORE.status())
    except Exception:
        status = {}
    adapter = _text(status.get("adapter") or status.get("mode") or "unknown")
    recorded = bool(status.get("persistence_available") or adapter in {"sqlite", "postgres", "memory"})
    durable = bool(status.get("durability_verified") or (adapter == "postgres" and recorded))
    return {
        "recorded": recorded,
        "durable": durable,
        "durability_verified": durable,
        "adapter": adapter or "unknown",
        "label": "Recorded and durable" if durable else ("Recorded, not durable" if recorded else "Not recorded"),
        "warning": str(status.get("durability_warning") or ""),
    }


def _normalize_scanner_sections(value: Any) -> None:
    if isinstance(value, dict):
        name = _named(value)
        if name in {_text(item) for item in _SCANNER_NAMES}:
            value["score_treatment"] = "supplemental_mapped_to_scored_controls"
            value["display_status"] = "SUPPLEMENTAL · MAPPED TO SCORED CONTROLS"
            value["directly_scored"] = False
            value["mapped_to_scored_controls"] = True
            value["gray_not_scored"] = False
            value.setdefault(
                "score_explanation",
                "Scanner output is supplemental evidence. Each result is mapped to its relevant scored control and affects confidence, limitations, or findings without creating a separate maturity-score contribution.",
            )
        for child in value.values():
            _normalize_scanner_sections(child)
    elif isinstance(value, list):
        for child in value:
            _normalize_scanner_sections(child)


def reconcile_terminal_truth(payload: dict[str, Any]) -> dict[str, Any]:
    output = deepcopy(payload)
    persistence = _storage_truth()
    output["persistence"] = persistence
    output["durable_record"] = persistence
    output["durability_verified"] = persistence["durable"]
    output["evidence_readiness"] = "ready" if persistence["durable"] else "pending"
    _normalize_scanner_sections(output)

    overall = _status(output)
    terminal_claim = overall in {"complete", "completed", "succeeded", "success"} or bool(output.get("complete") or output.get("completed"))
    gate_pending = _required_gate_nonterminal(output)
    blocked_by_durability = not persistence["durable"]
    if terminal_claim and (gate_pending or blocked_by_durability):
        output["status"] = "finalizing"
        output["state"] = "finalizing"
        output["complete"] = False
        output["completed"] = False
        output["terminal"] = False
        output["client_ready"] = False
        output["human_review_required"] = True
        output["progress_percent"] = min(int(output.get("progress_percent") or output.get("progress") or 99), 99)
        reasons: list[str] = []
        if gate_pending:
            reasons.append("truth_and_review_gates_nonterminal")
        if blocked_by_durability:
            reasons.append("durable_record_unverified")
        output["completion_blockers"] = sorted(set([*output.get("completion_blockers", []), *reasons]))
        output["completion_state_reconciled"] = True
    else:
        output["completion_state_reconciled"] = False
    output["terminal_truth_version"] = VERSION
    return output


def install_express_terminal_truth_patch() -> dict[str, Any]:
    current: Callable[[str, str, str], dict[str, Any]] = hardening._express_status_response
    if getattr(current, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    def terminal_truth_response(run_id: str, customer_id: str, project_id: str) -> dict[str, Any]:
        response = current(run_id, customer_id, project_id)
        return reconcile_terminal_truth(response)

    setattr(terminal_truth_response, _PATCH_MARKER, True)
    setattr(terminal_truth_response, "_nico_previous", current)
    hardening._express_status_response = terminal_truth_response
    return {
        "status": "installed",
        "version": VERSION,
        "terminal_completion_requires_terminal_gates": True,
        "terminal_completion_requires_durable_record": True,
        "scanner_worker_evidence_mapped_to_controls": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_express_terminal_truth_patch", "reconcile_terminal_truth"]
