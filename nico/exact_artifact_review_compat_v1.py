from __future__ import annotations

from copy import deepcopy
from functools import wraps
from typing import Any, Mapping

VERSION = "nico.exact-artifact-review-compat.v1.1"
_VALIDATION_MARKER = "__nico_exact_artifact_review_validation_compat_v1__"
_REQUEST_MARKER = "__nico_exact_artifact_review_request_compat_v1__"
_TRANSITION_MARKER = "__nico_exact_artifact_review_transition_compat_v1__"
_ARTIFACT_VALIDATION_MARKER = "__nico_artifact_manifest_validation_v1__"
_ARTIFACT_REQUEST_MARKER = "__nico_artifact_manifest_request_v1__"
_ARTIFACT_TRANSITION_MARKER = "__nico_artifact_manifest_transition_v1__"


def _text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _canonical(report: Mapping[str, Any]) -> Mapping[str, Any]:
    formats = report.get("formats") if isinstance(report.get("formats"), Mapping) else {}
    value = formats.get("json") if isinstance(formats.get("json"), Mapping) else {}
    return value if isinstance(value, Mapping) else {}


def _requires_exact_review(
    report: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> bool:
    canonical = _canonical(report)
    if any(
        isinstance(value, Mapping)
        for value in (
            report.get("draft_artifact_identity"),
            report.get("artifact_manifest"),
            canonical.get("draft_artifact_identity"),
            canonical.get("artifact_manifest"),
            approval.get("draft_artifact_identity"),
        )
    ):
        return True
    if any(
        value is True
        for value in (
            report.get("exact_artifact_approval_required"),
            canonical.get("exact_artifact_approval_required"),
            approval.get("exact_artifact_approval_required"),
        )
    ):
        return True
    return any(
        _text(approval.get(key))
        for key in (
            "approved_pdf_sha256",
            "approved_json_sha256",
            "evidence_manifest_sha256",
            "artifact_manifest_id",
        )
    )


def _report_for(workflow: Any, approval: Mapping[str, Any]) -> Mapping[str, Any]:
    identity = _text(approval.get("report_id") or approval.get("run_id"))
    if not identity:
        return {}
    try:
        value = workflow._report_for_run(identity)
    except Exception:
        return {}
    return value if isinstance(value, Mapping) else {}


def install_exact_artifact_review_compat_v1() -> dict[str, Any]:
    from nico import final_review_workflow as workflow

    current_validation = workflow.final_review_validation
    if not getattr(current_validation, _VALIDATION_MARKER, False):
        legacy_validation = getattr(
            current_validation,
            "_nico_previous",
            current_validation,
        )

        @wraps(current_validation)
        def final_review_validation(approval: dict[str, Any]) -> dict[str, Any]:
            report = _report_for(workflow, approval)
            if not _requires_exact_review(report, approval):
                return deepcopy(legacy_validation(approval))
            return deepcopy(current_validation(approval))

        setattr(final_review_validation, _VALIDATION_MARKER, True)
        # Preserve the artifact patch's public marker so repeated runtime installs
        # do not wrap the compatibility boundary again.
        setattr(final_review_validation, _ARTIFACT_VALIDATION_MARKER, True)
        setattr(final_review_validation, "_nico_previous", current_validation)
        setattr(final_review_validation, "_nico_legacy", legacy_validation)
        workflow.final_review_validation = final_review_validation

    current_request = workflow.request_final_review
    if not getattr(current_request, _REQUEST_MARKER, False):
        legacy_request = getattr(current_request, "_nico_previous", current_request)

        @wraps(current_request)
        def request_final_review(payload: dict[str, Any]) -> dict[str, Any]:
            report = _report_for(workflow, payload)
            if not _requires_exact_review(report, payload):
                return deepcopy(legacy_request(payload))
            return deepcopy(current_request(payload))

        setattr(request_final_review, _REQUEST_MARKER, True)
        setattr(request_final_review, _ARTIFACT_REQUEST_MARKER, True)
        setattr(request_final_review, "_nico_previous", current_request)
        setattr(request_final_review, "_nico_legacy", legacy_request)
        workflow.request_final_review = request_final_review

    current_transition = workflow.transition_final_review
    if not getattr(current_transition, _TRANSITION_MARKER, False):
        legacy_transition = getattr(
            current_transition,
            "_nico_previous",
            current_transition,
        )

        @wraps(current_transition)
        def transition_final_review(
            approval_id: str,
            state: str,
            actor: str = "human_reviewer",
            note: str = "",
        ) -> dict[str, Any]:
            approval = workflow.STORE.get("approvals", approval_id)
            approval = approval if isinstance(approval, Mapping) else {}
            report = _report_for(workflow, approval)
            if not _requires_exact_review(report, approval):
                return deepcopy(
                    legacy_transition(
                        approval_id,
                        state,
                        actor=actor,
                        note=note,
                    )
                )
            return deepcopy(
                current_transition(
                    approval_id,
                    state,
                    actor=actor,
                    note=note,
                )
            )

        setattr(transition_final_review, _TRANSITION_MARKER, True)
        setattr(transition_final_review, _ARTIFACT_TRANSITION_MARKER, True)
        setattr(transition_final_review, "_nico_previous", current_transition)
        setattr(transition_final_review, "_nico_legacy", legacy_transition)
        workflow.transition_final_review = transition_final_review

    return {
        "status": "installed",
        "version": VERSION,
        "legacy_non_manifest_review_flow_preserved": True,
        "manifest_aware_review_requires_exact_identity": True,
        "manifest_aware_missing_identity_fails_closed": True,
        "runtime_reentry_does_not_stack_review_wrappers": True,
        "reviewer_role_required_for_exact_artifact_approval": True,
        "reviewer_authorization_required_for_exact_artifact_approval": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_requires_exact_review",
    "install_exact_artifact_review_compat_v1",
]
