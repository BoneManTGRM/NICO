from __future__ import annotations

import os
import re
from functools import wraps
from typing import Any, Callable, Mapping
from uuid import uuid4

VERSION = "nico.runtime_deployment_commit_resolution.v4"
_MARKER = "_nico_runtime_deployment_commit_resolution_v1"
_INTAKE_CAPTURE_MARKER = "_nico_runtime_deployment_intake_capture_v1"
_DURABLE_INTAKE_MARKER = "_nico_durable_explicit_sha_intake_v1"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_EXPECTED_MARKER_RE = re.compile(
    r"(?:^|[;\s])expected_commit_sha=([0-9a-fA-F]{40})(?=$|[;\s])"
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repository(value: Any) -> str:
    candidate = _text(value)
    return candidate if _REPOSITORY_RE.fullmatch(candidate) else ""


def _expected_sha(context: Mapping[str, Any]) -> str:
    """Read the immutable release SHA from first-class or compatibility transport."""
    for key in ("expected_commit_sha", "commit_sha", "snapshot_commit_sha"):
        value = _text(context.get(key)).lower()
        if _SHA_RE.fullmatch(value):
            return value
    marker = _text(context.get("authorized_by"))
    match = _EXPECTED_MARKER_RE.search(marker)
    return match.group(1).lower() if match else ""


def _provider_candidates(environ: Mapping[str, str]) -> list[dict[str, str]]:
    candidates: list[dict[str, str]] = []
    railway_sha = _text(environ.get("RAILWAY_GIT_COMMIT_SHA")).lower()
    railway_owner = _text(environ.get("RAILWAY_GIT_REPO_OWNER"))
    railway_name = _text(environ.get("RAILWAY_GIT_REPO_NAME"))
    railway_repository = _repository(f"{railway_owner}/{railway_name}" if railway_owner and railway_name else "")
    if _SHA_RE.fullmatch(railway_sha) and railway_repository:
        candidates.append({"provider": "railway", "repository": railway_repository, "commit_sha": railway_sha, "branch": _text(environ.get("RAILWAY_GIT_BRANCH")), "source": "railway_runtime_deployment", "method": "railway_git_commit_sha"})
    vercel_sha = _text(environ.get("VERCEL_GIT_COMMIT_SHA")).lower()
    vercel_owner = _text(environ.get("VERCEL_GIT_REPO_OWNER"))
    vercel_name = _text(environ.get("VERCEL_GIT_REPO_SLUG"))
    vercel_repository = _repository(f"{vercel_owner}/{vercel_name}" if vercel_owner and vercel_name else "")
    if _SHA_RE.fullmatch(vercel_sha) and vercel_repository:
        candidates.append({"provider": "vercel", "repository": vercel_repository, "commit_sha": vercel_sha, "branch": _text(environ.get("VERCEL_GIT_COMMIT_REF")), "source": "vercel_runtime_deployment", "method": "vercel_git_commit_sha"})
    return candidates


def runtime_deployment_resolution(context: Mapping[str, Any], *, environ: Mapping[str, str] | None = None) -> dict[str, Any] | None:
    repository = _repository(context.get("repository"))
    expected = _expected_sha(context)
    if not repository or not expected:
        return None
    for candidate in _provider_candidates(environ or os.environ):
        if candidate["repository"].casefold() != repository.casefold() or candidate["commit_sha"] != expected:
            continue
        return {
            "status": "attached", "repository": repository, "source": candidate["source"],
            "commit_capture_method": candidate["method"], "api_commit_lookup_attempts": 0,
            "public_git_fallback_attempted": False, "public_git_fallback_used": False,
            "repository_metadata_available": True, "default_branch": candidate["branch"],
            "requested_ref": expected, "expected_commit_sha": expected,
            "commit_binding_source": "provider_runtime_deployment", "exact_commit_verified": True,
            "commit_sha": expected, "tree_sha": "", "commit_date": "", "commit_message": "",
            "repository_pushed_at": "", "repository_visibility": "provider_deployment_verified",
            "deployment_provider": candidate["provider"], "deployment_repository_verified": True,
            "deployment_commit_verified": True, "authorization_marker_supported": True,
            "human_review_required": True, "client_delivery_allowed": False,
        }
    return None


def _install_comprehensive_intake_capture() -> dict[str, Any]:
    from nico import comprehensive_api_routes
    current = comprehensive_api_routes.capture_repository_snapshot
    if getattr(current, _INTAKE_CAPTURE_MARKER, False):
        return {"status": "already_installed", "bound": True, "provider_exact_sha_preverified": True}

    @wraps(current)
    def capture(context: dict[str, Any], *, client: Any | None = None, store: Any | None = None) -> dict[str, Any]:
        runtime = runtime_deployment_resolution(context)
        if runtime is None:
            return current(context, client=client, store=store)
        enriched = dict(context)
        enriched["exact_commit_resolution"] = runtime
        return current(enriched, client=client, store=store)

    setattr(capture, _INTAKE_CAPTURE_MARKER, True)
    setattr(capture, "_nico_previous", current)
    comprehensive_api_routes.capture_repository_snapshot = capture
    return {"status": "installed", "bound": comprehensive_api_routes.capture_repository_snapshot is capture, "provider_exact_sha_preverified": True, "external_repository_fallback_preserved": True, "private_repository_policy_preserved": True}


def _install_durable_explicit_sha_intake() -> dict[str, Any]:
    """Persist the exact run identity before any repository-network snapshot I/O.

    An explicitly supplied immutable SHA is sufficient to create the durable run
    identity, but it is not treated as verified evidence. The required
    `immutable_repository_snapshot` stage immediately re-verifies that repository/SHA
    through the existing provider/API/Git fail-closed snapshot provider before any
    repository evidence or scanner stage can proceed. Requests without an explicit SHA
    retain the established intake-time resolution behavior.
    """
    from nico import comprehensive_api_routes as routes

    current = routes._intake
    if getattr(current, _DURABLE_INTAKE_MARKER, False):
        return {"status": "already_installed", "bound": True, "snapshot_verification_deferred_only_for_explicit_sha": True}

    @wraps(current)
    def intake(request: Any, payload: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(payload, dict):
            return current(request, payload)
        requested_sha = routes.expected_commit_sha(payload)
        if not requested_sha:
            return current(request, payload)
        if payload.get("authorized") is not True or payload.get("authorization_confirmed") is not True:
            return current(request, payload)

        repository = routes.normalize_repository(routes._required(payload.get("repository"), "repository"))
        customer_id = routes._required(payload.get("customer_id") or "default_customer", "customer_id")
        project_id = routes._required(payload.get("project_id") or "default_project", "project_id")
        assessment_depth = routes._required(payload.get("assessment_depth") or "strategic", "assessment_depth")
        report_language = routes._required(payload.get("report_language") or "en", "report_language")
        run_id = f"comprun_{uuid4().hex}"
        evidence_ledger_id = f"ledger_comprehensive_{uuid4().hex}"
        response = routes._controller(request).start({
            "repository": repository,
            "commit_sha": requested_sha,
            "run_id": run_id,
            "evidence_ledger_id": evidence_ledger_id,
            "customer_id": customer_id,
            "project_id": project_id,
            "assessment_depth": assessment_depth,
            "report_language": report_language,
            "human_evidence": payload.get("human_evidence"),
            "authorized": True,
            "authorization_confirmed": True,
        })
        projected = routes._with_runtime_truth(request, response)
        projected["explicit_commit_sha_bound"] = requested_sha
        projected["repository_snapshot_verification"] = "required_next_stage"
        projected["repository_processing_begun"] = False
        projected["human_review_required"] = True
        projected["client_delivery_allowed"] = False
        return projected

    setattr(intake, _DURABLE_INTAKE_MARKER, True)
    setattr(intake, "_nico_previous", current)
    routes._intake = intake
    return {
        "status": "installed",
        "bound": routes._intake is intake,
        "snapshot_verification_deferred_only_for_explicit_sha": True,
        "immutable_snapshot_stage_still_required": True,
        "repository_processing_before_snapshot_verification": False,
        "default_branch_intake_behavior_preserved": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


def install_runtime_deployment_commit_resolution() -> dict[str, Any]:
    from nico import exact_commit_binding, repository_snapshot
    from nico.comprehensive_cross_format_finality_v49 import install_comprehensive_cross_format_finality_v49

    cross_format_finality = install_comprehensive_cross_format_finality_v49()
    intake_capture = _install_comprehensive_intake_capture()
    durable_intake = _install_durable_explicit_sha_intake()
    current: Callable[..., dict[str, Any]] = repository_snapshot.resolve_repository_commit
    if getattr(current, _MARKER, False):
        exact_commit_binding.resolve_repository_commit = current
        return {"status": "already_installed", "version": VERSION, "repository_snapshot_bound": True, "exact_commit_binding_bound": True, "authorization_marker_supported": True, "comprehensive_intake_capture": intake_capture, "durable_explicit_sha_intake": durable_intake, "comprehensive_cross_format_finality": cross_format_finality}

    @wraps(current)
    def resolve(context: dict[str, Any], *, client: Any | None = None) -> dict[str, Any]:
        runtime = runtime_deployment_resolution(context)
        if runtime is not None:
            return runtime
        return current(context, client=client)

    setattr(resolve, _MARKER, True)
    setattr(resolve, "_nico_previous", current)
    repository_snapshot.resolve_repository_commit = resolve
    exact_commit_binding.resolve_repository_commit = resolve
    return {
        "status": "installed", "version": VERSION,
        "repository_snapshot_bound": repository_snapshot.resolve_repository_commit is resolve,
        "exact_commit_binding_bound": exact_commit_binding.resolve_repository_commit is resolve,
        "provider_owned_variables_only": True, "repository_identity_required": True,
        "exact_sha_match_required": True, "authorization_marker_supported": True,
        "api_and_public_git_fallback_preserved": True,
        "comprehensive_intake_capture": intake_capture, "durable_explicit_sha_intake": durable_intake,
        "comprehensive_cross_format_finality": cross_format_finality,
        "human_review_required": True, "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_runtime_deployment_commit_resolution", "runtime_deployment_resolution"]
