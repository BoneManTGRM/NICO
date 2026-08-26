from __future__ import annotations

from typing import Any

VERSION = "nico.comprehensive_intake_display_metadata.v2"
_MARKER = "_nico_direct_display_metadata_v2"
_INSTALLED = False


def install_comprehensive_intake_display_metadata_v2() -> dict[str, Any]:
    """Bind client/project display metadata directly into the real intake payload.

    Earlier production repair relied on a ContextVar around ``routes._intake`` because
    the historical intake stripped ``client_name`` and ``project_name`` before calling
    ``ComprehensiveApiController.start``. The production route executes intake in a
    threadpool and multiple late runtime wrappers exist, so that side-channel was still
    not reliable in a real fresh run. This v2 binding removes the side-channel at the
    boundary: the exact values received from the browser are passed to the controller
    explicitly. The already-installed report/review integrity binding then persists them
    in the initial canonical run record before the durable create.

    Canonical customer/project scope IDs remain unchanged. These values are display
    metadata only and do not affect scoring, scanners, approval, or delivery authority.
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
        if (
            payload.get("authorized") is not True
            or payload.get("authorization_confirmed") is not True
        ):
            raise ValueError("explicit_authorization_required")

        repository = routes.normalize_repository(
            routes._required(payload.get("repository"), "repository")
        )
        customer_id = routes._required(
            payload.get("customer_id") or "default_customer",
            "customer_id",
        )
        project_id = routes._required(
            payload.get("project_id") or "default_project",
            "project_id",
        )
        assessment_depth = routes._required(
            payload.get("assessment_depth") or "strategic",
            "assessment_depth",
        )
        report_language = routes._required(
            payload.get("report_language") or "en",
            "report_language",
        )
        client_name = " ".join(str(payload.get("client_name") or "").split())[:180]
        project_name = " ".join(str(payload.get("project_name") or "").split())[:180]
        requested_sha = routes.expected_commit_sha(payload)
        run_id = f"comprun_{routes.uuid4().hex}"
        evidence_ledger_id = f"ledger_comprehensive_{routes.uuid4().hex}"

        snapshot = routes.capture_repository_snapshot(
            {
                "run_id": run_id,
                "repository": repository,
                "customer_id": customer_id,
                "project_id": project_id,
                "authorized": True,
                "authorized_by": routes._required(
                    payload.get("authorized_by") or "public_assessment_requester",
                    "authorized_by",
                ),
                "authorization_scope": routes._required(
                    payload.get("authorization_scope")
                    or "authorized defensive repository assessment",
                    "authorization_scope",
                ),
                "expected_commit_sha": requested_sha,
            }
        )
        if snapshot.get("status") != "attached" or not str(
            snapshot.get("commit_sha") or ""
        ).strip():
            notes = [
                str(item)
                for item in snapshot.get("unavailable_data_notes") or []
                if str(item).strip()
            ]
            reason = notes[0] if notes else "repository_snapshot_unavailable"
            raise ValueError(f"repository_snapshot_unavailable:{reason}")
        if (
            requested_sha
            and str(snapshot.get("commit_sha") or "").strip().lower()
            != requested_sha
        ):
            raise ValueError("repository_snapshot_commit_mismatch")

        response = routes._controller(request).start(
            {
                "repository": repository,
                "commit_sha": snapshot["commit_sha"],
                "run_id": run_id,
                "evidence_ledger_id": evidence_ledger_id,
                "customer_id": customer_id,
                "project_id": project_id,
                "client_name": client_name,
                "project_name": project_name,
                "assessment_depth": assessment_depth,
                "report_language": report_language,
                "human_evidence": payload.get("human_evidence"),
                "authorized": True,
                "authorization_confirmed": True,
            }
        )
        return routes._with_runtime_truth(
            request,
            {
                **response,
                "operation": "intake_started",
                "repository_snapshot": snapshot,
                "client_name": client_name,
                "project_name": project_name,
            },
        )

    setattr(intake_with_direct_display_metadata, _MARKER, True)
    setattr(intake_with_direct_display_metadata, "_nico_previous", current)
    routes._intake = intake_with_direct_display_metadata
    _INSTALLED = True
    return {
        "artifact_schema": VERSION,
        "status": "installed",
        "bound": True,
        "direct_controller_payload": True,
        "contextvar_required_for_display_metadata": False,
        "canonical_scope_ids_unchanged": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_intake_display_metadata_v2"]
