from __future__ import annotations

from copy import deepcopy
from typing import Any

from nico.assessment_checkpointed_orchestration import (
    run_checkpointed_assessment_orchestration,
)


def test_checkpointed_orchestration_emits_preflight_step_and_final_states() -> None:
    payload = {
        "run_id": "fullrun_1234567890abcdef",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "authorized_by": "owner",
        "authorization_scope": "repository assessment only",
        "authorization_confirmed": True,
        "run_scanners": False,
        "build_reports": False,
        "create_final_review_request": False,
    }
    checkpoints: list[tuple[str, str, dict[str, Any]]] = []

    def checkpoint(result: dict[str, Any], step: str, phase: str) -> None:
        checkpoints.append((step, phase, deepcopy(result)))

    handlers = {
        "repo_evidence": lambda context, outputs: {
            "status": "complete",
            "message": "repository evidence complete",
            "evidence": {"run_id": context["run_id"], "evidence_id": "evidence_1"},
        },
        "scanner_worker": lambda context, outputs: {
            "status": "skipped",
            "message": "scanner skipped",
            "evidence": {"run_id": context["run_id"]},
        },
        "evidence_attachment": lambda context, outputs: {
            "status": "skipped",
            "message": "no scanner evidence",
            "evidence": {"run_id": context["run_id"]},
        },
        "scoring": lambda context, outputs: {
            "status": "skipped",
            "message": "scoring skipped",
            "evidence": {"run_id": context["run_id"]},
        },
        "reports": lambda context, outputs: {
            "status": "skipped",
            "message": "reports skipped",
            "evidence": {"run_id": context["run_id"]},
        },
        "approval_request": lambda context, outputs: {
            "status": "skipped",
            "message": "approval skipped",
            "evidence": {"run_id": context["run_id"]},
        },
    }

    result = run_checkpointed_assessment_orchestration(
        payload,
        handlers=handlers,
        checkpoint=checkpoint,
    )

    assert result["status"] == "complete"
    assert checkpoints[0][0:2] == ("preflight", "preflight")
    assert checkpoints[-1][0:2] == ("orchestration", "orchestration_finalized")
    phases = [(step, phase) for step, phase, _ in checkpoints]
    for step in handlers:
        assert (step, "step_started") in phases
        assert (step, "step_completed") in phases

    repo_complete = next(
        item
        for step, phase, item in checkpoints
        if step == "repo_evidence" and phase == "step_completed"
    )
    progress = {
        entry["step"]: entry
        for entry in repo_complete["progress"]
    }
    assert progress["authorization"]["status"] == "complete"
    assert progress["repo_evidence"]["status"] == "complete"
    assert progress["repo_evidence"]["evidence"]["evidence_id"] == "evidence_1"


def test_failed_handler_emits_failed_checkpoint_without_raw_exception() -> None:
    payload = {
        "run_id": "fullrun_1234567890abcdef",
        "repository": "BoneManTGRM/NICO",
        "customer_id": "customer_1",
        "project_id": "project_1",
        "authorized_by": "owner",
        "authorization_scope": "repository assessment only",
        "authorization_confirmed": True,
    }
    checkpoints: list[tuple[str, str, dict[str, Any]]] = []

    def checkpoint(result: dict[str, Any], step: str, phase: str) -> None:
        checkpoints.append((step, phase, deepcopy(result)))

    def fail(context, outputs):
        raise RuntimeError("secret=must-not-leak")

    result = run_checkpointed_assessment_orchestration(
        payload,
        handlers={"repo_evidence": fail},
        checkpoint=checkpoint,
    )

    assert result["status"] == "failed"
    failed = next(
        item for step, phase, item in checkpoints if phase == "step_failed"
    )
    rendered = repr(failed)
    assert failed["failed_step"] == "repo_evidence"
    assert "must-not-leak" not in rendered
    assert "secret=" not in rendered
