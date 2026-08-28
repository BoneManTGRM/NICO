from __future__ import annotations

from copy import deepcopy
from collections.abc import Mapping
from typing import Any

VERSION = "nico.comprehensive_intake_display_metadata.v2.2"
_MARKER = "_nico_direct_display_metadata_v2"
_INSTALLED = False


def _with_names(stakeholder_value: Any, *, client_name: str, project_name: str) -> dict[str, Any]:
    stakeholder = dict(stakeholder_value) if isinstance(stakeholder_value, Mapping) else {}
    evidence = stakeholder.get("evidence")
    evidence = dict(evidence) if isinstance(evidence, Mapping) else {}
    if client_name:
        evidence["customer_name"] = client_name
    if project_name:
        evidence["project_name"] = project_name
    stakeholder["evidence"] = evidence
    return stakeholder


def _human_evidence_with_display_metadata(
    value: Any,
    *,
    client_name: str,
    project_name: str,
) -> Any:
    """Mirror optional display-only names into retained human evidence.

    Preserve all three intake shapes accepted by the existing normalizer: a module map,
    a module list, or direct top-level module keys. Canonical scope identifiers remain
    authoritative; these two strings are descriptive report metadata only.
    """

    if not client_name and not project_name:
        return value
    source = deepcopy(value) if isinstance(value, Mapping) else {}
    modules = source.get("modules")

    if isinstance(modules, Mapping):
        copied_modules = dict(modules)
        copied_modules["stakeholder_context"] = _with_names(
            copied_modules.get("stakeholder_context"),
            client_name=client_name,
            project_name=project_name,
        )
        source["modules"] = copied_modules
        return source

    if isinstance(modules, list):
        copied_modules = deepcopy(modules)
        found = False
        for index, item in enumerate(copied_modules):
            if not isinstance(item, Mapping):
                continue
            if str(item.get("module_id") or "") != "stakeholder_context":
                continue
            updated = _with_names(
                item,
                client_name=client_name,
                project_name=project_name,
            )
            updated["module_id"] = "stakeholder_context"
            copied_modules[index] = updated
            found = True
            break
        if not found:
            appended = _with_names(
                {},
                client_name=client_name,
                project_name=project_name,
            )
            appended["module_id"] = "stakeholder_context"
            copied_modules.append(appended)
        source["modules"] = copied_modules
        return source

    # Legacy/direct module-key input is also a supported normalizer contract. Do not
    # convert it to a new ``modules`` object because doing so would make the normalizer
    # ignore its other direct module keys.
    source["stakeholder_context"] = _with_names(
        source.get("stakeholder_context"),
        client_name=client_name,
        project_name=project_name,
    )
    return source


def install_comprehensive_intake_display_metadata_v2() -> dict[str, Any]:
    """Bind client/project display metadata directly into the real intake payload.

    Earlier production repair relied on a ContextVar around ``routes._intake`` because
    the historical intake stripped ``client_name`` and ``project_name`` before calling
    ``ComprehensiveApiController.start``. The production route executes intake in a
    threadpool and multiple late runtime wrappers exist, so that side-channel was still
    not reliable in a real fresh run. This v2 binding removes the side-channel at the
    boundary: the exact values received from the browser are passed to the controller
    explicitly. It also mirrors the two display-only values into retained stakeholder
    evidence so the isolated final-report worker has a durable fallback. Canonical
    customer/project scope IDs remain unchanged.

    These values are display metadata only and do not affect scoring, scanners, approval,
    candidate truth, or delivery authority.
    """

    global _INSTALLED
    import nico.comprehensive_api_routes as routes

    current = routes._intake
    if getattr(current, _MARKER, False):
        _INSTALLED = True
        return {
            "artifact_schema": VERSION,
            "status": "already_installed",
            "bound": True,
            "direct_controller_payload": True,
            "durable_report_display_metadata_fallback": True,
            "contextvar_required_for_display_metadata": False,
            "canonical_scope_ids_unchanged": True,
            "human_review_required": True,
            "client_delivery_allowed": False,
        }

    def intake_with_direct_display_metadata(
        request: Any,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise TypeError("request_body_must_be_object")
        from nico.comprehensive_engagement_metadata_v1 import _literal

        client_name = _literal(payload.get("client_name"), 180)
        project_name = _literal(payload.get("project_name"), 180)
        human_evidence = _human_evidence_with_display_metadata(
            payload.get("human_evidence"),
            client_name=client_name,
            project_name=project_name,
        )
        # Compose with the already-installed intake boundary instead of replacing it.
        # In production that boundary includes the Phase-3 client-engagement guard,
        # which validates real client scope and binds client/project delivery identity.
        # Bypassing it would preserve display strings but silently remove required
        # authorization evidence and make a legitimate client run unapprovable later.
        enriched_payload = dict(payload)
        enriched_payload["client_name"] = client_name
        enriched_payload["project_name"] = project_name
        enriched_payload["human_evidence"] = human_evidence
        return current(request, enriched_payload)

    setattr(intake_with_direct_display_metadata, _MARKER, True)
    setattr(intake_with_direct_display_metadata, "_nico_previous", current)
    routes._intake = intake_with_direct_display_metadata
    _INSTALLED = True
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "direct_controller_payload": True,
        "durable_report_display_metadata_fallback": True,
        "contextvar_required_for_display_metadata": False,
        "canonical_scope_ids_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "VERSION",
    "_human_evidence_with_display_metadata",
    "install_comprehensive_intake_display_metadata_v2",
]
