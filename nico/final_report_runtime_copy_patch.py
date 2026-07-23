from __future__ import annotations

from functools import wraps
from typing import Any, Callable

VERSION = "nico.final_report_runtime_copy.v1"
_MARKER = "_nico_final_report_runtime_copy_v1"

_REPLACEMENTS = (
    ("draft report artifacts are ready for human review", "final report artifacts are ready for required human review"),
    ("Draft report artifacts are ready for required human review", "Final report artifacts are ready for required human review"),
    ("Full Assessment draft", "Full Assessment final report pending approval"),
    ("stored draft PDF", "stored final PDF pending approval"),
    ("valid draft PDF", "valid final PDF pending approval"),
    ("exact reviewed draft", "exact reviewed final report"),
    ("source_draft_pdf_sha256", "source_final_report_sha256"),
)


def _replace_text(value: str) -> str:
    output = value
    for previous, replacement in _REPLACEMENTS:
        output = output.replace(previous, replacement)
    return output


def _normalize(value: Any) -> Any:
    if isinstance(value, str):
        return _replace_text(value)
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_normalize(item) for item in value)
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            # Preserve the legacy hash key as a compatibility alias while exposing
            # the canonical final-report key to all new consumers.
            output[key] = _normalize(item)
            if key == "source_draft_pdf_sha256" and "source_final_report_sha256" not in output:
                output["source_final_report_sha256"] = _normalize(item)
        return output
    return value


def _wrap(module: Any, name: str) -> bool:
    current: Callable[..., Any] = getattr(module, name)
    if getattr(current, _MARKER, False):
        return False

    @wraps(current)
    def wrapped(*args: Any, **kwargs: Any) -> Any:
        return _normalize(current(*args, **kwargs))

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "_nico_previous", current)
    setattr(module, name, wrapped)
    return True


def install_final_report_runtime_copy_patch() -> dict[str, Any]:
    from nico import client_acceptance, express_async_api, final_review_workflow

    express_async_api._EXPRESS_STAGE_DEFINITIONS = tuple(
        (
            step,
            "Assessment completed and final report artifacts are ready for required human review."
            if step == "complete"
            else _replace_text(label),
        )
        for step, label in express_async_api._EXPRESS_STAGE_DEFINITIONS
    )

    wrapped = 0
    for module, names in (
        (client_acceptance, ("build_client_acceptance_gate",)),
        (
            final_review_workflow,
            (
                "final_review_validation",
                "final_review_status",
                "request_final_review",
                "transition_final_review",
            ),
        ),
    ):
        for name in names:
            wrapped += int(_wrap(module, name))

    original_gate: Callable[[dict[str, Any]], dict[str, Any]] = client_acceptance.build_client_acceptance_gate
    if not getattr(original_gate, "_nico_final_report_gate_fields_v1", False):
        @wraps(original_gate)
        def final_gate(result: dict[str, Any]) -> dict[str, Any]:
            gate = dict(original_gate(result))
            gate.update(
                {
                    "report_finality": "final",
                    "approval_status": "pending_human_approval",
                    "delivery_status": "blocked_pending_human_approval",
                    "automation_finality": "final_report_pending_human_approval",
                    "client_delivery_allowed": False,
                }
            )
            return gate

        setattr(final_gate, "_nico_final_report_gate_fields_v1", True)
        setattr(final_gate, "_nico_previous", original_gate)
        client_acceptance.build_client_acceptance_gate = final_gate
        wrapped += 1

    return {
        "status": "installed" if wrapped else "already_installed",
        "version": VERSION,
        "functions_wrapped": wrapped,
        "express_complete_stage_uses_final_report": True,
        "approval_validation_uses_final_report": True,
        "legacy_hash_alias_preserved": True,
        "report_finality": "final",
        "approval_status": "pending_human_approval",
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_final_report_runtime_copy_patch"]
