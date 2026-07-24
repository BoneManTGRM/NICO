from __future__ import annotations

import re
import threading
from functools import wraps
from typing import Any, Callable
from urllib.parse import quote

from nico.repository_snapshot import resolve_repository_commit

EXACT_COMMIT_BINDING_VERSION = "nico.exact_commit_binding.v2"
_SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")
_MARKER_RE = re.compile(r"(?:^|[;\s])expected_commit_sha=([0-9a-fA-F]{40})(?:$|[;\s])")
_ASSESSMENT_MARKER = "_nico_exact_commit_assessment_v1"
_CLIENT_MARKER = "_nico_exact_commit_client_v1"
_SCANNER_MARKER = "_nico_exact_commit_scanner_v1"
_STATE = threading.local()


def expected_commit_sha(payload: dict[str, Any]) -> str:
    """Return an explicitly requested immutable commit without inventing one."""

    for key in ("expected_commit_sha", "commit_sha", "snapshot_commit_sha"):
        value = str(payload.get(key) or "").strip().lower()
        if _SHA_RE.fullmatch(value):
            return value
    marker = str(payload.get("authorized_by") or "")
    match = _MARKER_RE.search(marker)
    return match.group(1).lower() if match else ""


def _blocked(repository: str, code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "code": code,
        "repository": repository,
        "error": message,
        "human_review_required": True,
        "client_ready": False,
        "client_delivery_allowed": False,
        "exact_commit_binding": {
            "version": EXACT_COMMIT_BINDING_VERSION,
            "status": "blocked",
            "code": code,
        },
    }


def _resolve_commit_details(
    payload: dict[str, Any],
    *,
    client: Any | None = None,
) -> dict[str, Any]:
    from nico.hosted_assessment import normalize_repository

    repository = normalize_repository(str(payload.get("repository") or ""))
    request_payload = dict(payload or {})
    request_payload["repository"] = repository
    return resolve_repository_commit(request_payload, client=client)


def _resolve_commit(payload: dict[str, Any]) -> tuple[str, str, str]:
    """Compatibility wrapper around the shared immutable commit resolver."""

    resolution = _resolve_commit_details(payload)
    repository = str(resolution.get("repository") or payload.get("repository") or "")
    resolved = str(resolution.get("commit_sha") or "").strip().lower()
    if resolution.get("status") == "attached" and _SHA_RE.fullmatch(resolved):
        return repository, resolved, ""
    message = " ".join(
        str(item or "").strip()
        for item in resolution.get("unavailable_data_notes") or []
        if str(item or "").strip()
    )
    return repository, "", message or "The requested repository commit could not be resolved."


def _active_ref(repository: str) -> str:
    active_repository = str(getattr(_STATE, "repository", "") or "").lower()
    active_ref = str(getattr(_STATE, "commit_sha", "") or "").lower()
    return active_ref if active_repository == repository.lower() and _SHA_RE.fullmatch(active_ref) else ""


def _install_exact_github_reads() -> dict[str, Any]:
    from nico.hosted_assessment import GitHubAssessmentClient

    current_contents = GitHubAssessmentClient.get_contents
    current_tree = GitHubAssessmentClient.get_tree
    if getattr(current_contents, _CLIENT_MARKER, False) and getattr(current_tree, _CLIENT_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current_contents)
    def get_contents_at_exact_commit(self: Any, repo: str, path: str = "") -> tuple[Any | None, str | None]:
        ref = _active_ref(repo)
        if not ref:
            return current_contents(self, repo, path)
        url_path = f"/contents/{path}" if path else "/contents"
        return self.get_json(self.repo_url(repo, url_path), {"ref": ref})

    @wraps(current_tree)
    def get_tree_at_exact_commit(self: Any, repo: str, branch: str) -> tuple[list[dict[str, Any]], str | None]:
        ref = _active_ref(repo)
        if not ref:
            return current_tree(self, repo, branch)
        data, error = self.get_json(
            self.repo_url(repo, f"/git/trees/{quote(ref, safe='')}"),
            {"recursive": "1"},
        )
        if error:
            return [], error
        if isinstance(data, dict) and isinstance(data.get("tree"), list):
            return data["tree"], None
        return [], "Git tree was unavailable or not a list."

    setattr(get_contents_at_exact_commit, _CLIENT_MARKER, True)
    setattr(get_contents_at_exact_commit, "_nico_previous", current_contents)
    setattr(get_tree_at_exact_commit, _CLIENT_MARKER, True)
    setattr(get_tree_at_exact_commit, "_nico_previous", current_tree)
    GitHubAssessmentClient.get_contents = get_contents_at_exact_commit
    GitHubAssessmentClient.get_tree = get_tree_at_exact_commit
    return {
        "status": "installed",
        "owner_verified": (
            getattr(GitHubAssessmentClient.get_contents, _CLIENT_MARKER, False) is True
            and getattr(GitHubAssessmentClient.get_tree, _CLIENT_MARKER, False) is True
        ),
    }


def _command_failure(scanner: Any, result: Any, message: str) -> Any:
    return scanner.WorkerCommandResult(
        args=tuple(result.args),
        returncode=result.returncode if result.returncode else 1,
        stdout=result.stdout,
        stderr=(str(result.stderr or "") + "\n" + message).strip(),
        timed_out=result.timed_out,
        output_truncated=result.output_truncated,
    )


def _install_exact_scanner_checkout() -> dict[str, Any]:
    from nico import hosted_scanner_worker as scanner

    current = scanner.checkout_for_hosted_scan
    if getattr(current, _SCANNER_MARKER, False):
        return {"status": "already_installed", "owner_verified": True}

    @wraps(current)
    def checkout_exact_commit(payload: dict[str, Any], workspace: Any) -> Any:
        expected = expected_commit_sha(payload)
        if not expected:
            return current(payload, workspace)

        repository = scanner.validate_repository(str(payload.get("repository") or ""))
        clone_command = scanner._clone_command(repository, None, workspace, full_history=True)
        clone_auth = scanner.build_github_clone_auth_env()
        cloned = scanner.run_command(
            clone_command,
            cwd=workspace.root,
            limits=scanner.WorkerLimits(timeout_seconds=300, max_output_chars=12_000),
            extra_env=clone_auth.extra_env,
        )
        if not cloned.ok:
            return cloned

        checked_out = scanner.run_command(
            ("git", "checkout", "--detach", expected),
            cwd=workspace.repo_dir,
            limits=scanner.WorkerLimits(timeout_seconds=90, max_output_chars=4_000),
        )
        if not checked_out.ok:
            fetched = scanner.run_command(
                ("git", "fetch", "--no-tags", "origin", expected),
                cwd=workspace.repo_dir,
                limits=scanner.WorkerLimits(timeout_seconds=180, max_output_chars=4_000),
                extra_env=clone_auth.extra_env,
            )
            if not fetched.ok:
                return fetched
            checked_out = scanner.run_command(
                ("git", "checkout", "--detach", expected),
                cwd=workspace.repo_dir,
                limits=scanner.WorkerLimits(timeout_seconds=90, max_output_chars=4_000),
            )
            if not checked_out.ok:
                return checked_out

        verified = scanner.run_command(
            ("git", "rev-parse", "HEAD"),
            cwd=workspace.repo_dir,
            limits=scanner.WorkerLimits(timeout_seconds=30, max_output_chars=2_000),
        )
        observed = str(verified.stdout or "").strip().lower()
        if not verified.ok or observed != expected:
            return _command_failure(
                scanner,
                verified,
                f"Exact commit checkout verification failed: expected {expected}, observed {observed or 'missing'}.",
            )
        _STATE.scanner_checkout_sha = observed
        return checked_out

    setattr(checkout_exact_commit, _SCANNER_MARKER, True)
    setattr(checkout_exact_commit, "_nico_previous", current)
    scanner.checkout_for_hosted_scan = checkout_exact_commit
    return {
        "status": "installed",
        "owner_verified": getattr(scanner.checkout_for_hosted_scan, _SCANNER_MARKER, False) is True,
        "detached_exact_commit_checkout": True,
    }


def _bind_result(
    result: dict[str, Any],
    *,
    repository: str,
    commit_sha: str,
    requested_sha: str,
    scanner_checkout_sha: str,
    resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if result.get("status") != "complete":
        return result

    resolution = resolution if isinstance(resolution, dict) else {}
    observed = str(result.get("commit_sha") or "").strip().lower()
    conflict = bool(observed and _SHA_RE.fullmatch(observed) and observed != commit_sha)
    if result.get("scanner_worker_auto_ran") is True and scanner_checkout_sha != commit_sha:
        return _blocked(
            repository,
            "exact_scanner_checkout_unverified",
            "The hosted scanner worker did not verify the exact immutable commit, so the assessment was stopped.",
        )

    capture_method = str(resolution.get("commit_capture_method") or "verified_exact_commit")
    source = str(resolution.get("source") or "verified_exact_commit")
    result["repository"] = repository
    result["commit_sha"] = commit_sha
    result["repository_snapshot"] = {
        "status": "attached",
        "repository": repository,
        "commit_sha": commit_sha,
        "expected_commit_sha": requested_sha or commit_sha,
        "source": source,
        "commit_capture_method": capture_method,
        "api_commit_lookup_attempts": int(resolution.get("api_commit_lookup_attempts") or 0),
        "public_git_fallback_used": bool(resolution.get("public_git_fallback_used")),
        "repository_metadata_available": bool(resolution.get("repository_metadata_available")),
        "exact_commit_verified": True,
        "human_review_required": True,
    }
    result["exact_commit_binding"] = {
        "version": EXACT_COMMIT_BINDING_VERSION,
        "status": "verified",
        "repository": repository,
        "requested_commit_sha": requested_sha or "default_branch_resolved_once",
        "resolved_commit_sha": commit_sha,
        "resolution_source": source,
        "commit_capture_method": capture_method,
        "api_commit_lookup_attempts": int(resolution.get("api_commit_lookup_attempts") or 0),
        "public_git_fallback_used": bool(resolution.get("public_git_fallback_used")),
        "repository_metadata_available": bool(resolution.get("repository_metadata_available")),
        "repository_files_ref": commit_sha,
        "scanner_checkout_sha": scanner_checkout_sha or "not_executed",
        "scanner_exact_commit_verified": scanner_checkout_sha == commit_sha if scanner_checkout_sha else False,
        "preexisting_commit_conflict_removed": conflict,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    if conflict:
        result["commit_identity_conflict"] = {
            "detected": True,
            "observed": observed,
            "canonical": commit_sha,
            "resolution": "The verified immutable commit binding is authoritative; conflicting derived metadata was retained as a review signal but cannot replace it.",
            "human_review_required": True,
        }
    return result


def _install_assessment_binding(api_main: Any, attribute: str) -> dict[str, Any]:
    current: Callable[[dict[str, Any]], dict[str, Any]] = getattr(api_main, attribute)
    if getattr(current, _ASSESSMENT_MARKER, False):
        return {"status": "already_installed", "function": attribute, "owner_verified": True}

    @wraps(current)
    def assessment_at_exact_commit(payload: dict[str, Any]) -> dict[str, Any]:
        request_payload = dict(payload or {})
        requested = expected_commit_sha(request_payload)
        try:
            resolution = _resolve_commit_details(request_payload)
        except Exception as exc:
            return _blocked(
                str(request_payload.get("repository") or ""),
                "exact_commit_resolution_failed",
                f"Exact commit resolution failed before assessment: {type(exc).__name__}.",
            )
        repository = str(resolution.get("repository") or request_payload.get("repository") or "")
        resolved = str(resolution.get("commit_sha") or "").strip().lower()
        if resolution.get("status") != "attached" or not _SHA_RE.fullmatch(resolved):
            message = " ".join(
                str(item or "").strip()
                for item in resolution.get("unavailable_data_notes") or []
                if str(item or "").strip()
            )
            return _blocked(repository, "exact_commit_unavailable", message or "Exact commit was unavailable.")

        bound_payload = dict(request_payload)
        bound_payload["expected_commit_sha"] = resolved
        bound_payload["commit_sha"] = resolved
        bound_payload["ref"] = resolved
        bound_payload["exact_commit_resolution"] = {
            key: value
            for key, value in resolution.items()
            if key not in {"unavailable_data_notes"}
        }
        previous_repository = getattr(_STATE, "repository", None)
        previous_commit = getattr(_STATE, "commit_sha", None)
        previous_scanner = getattr(_STATE, "scanner_checkout_sha", None)
        _STATE.repository = repository
        _STATE.commit_sha = resolved
        _STATE.scanner_checkout_sha = ""
        try:
            result = current(bound_payload)
            scanner_checkout = str(getattr(_STATE, "scanner_checkout_sha", "") or "").lower()
        finally:
            if previous_repository is None:
                _STATE.__dict__.pop("repository", None)
            else:
                _STATE.repository = previous_repository
            if previous_commit is None:
                _STATE.__dict__.pop("commit_sha", None)
            else:
                _STATE.commit_sha = previous_commit
            if previous_scanner is None:
                _STATE.__dict__.pop("scanner_checkout_sha", None)
            else:
                _STATE.scanner_checkout_sha = previous_scanner

        if not isinstance(result, dict):
            return _blocked(repository, "invalid_assessment_result", "Assessment did not return a JSON object.")
        return _bind_result(
            result,
            repository=repository,
            commit_sha=resolved,
            requested_sha=requested,
            scanner_checkout_sha=scanner_checkout,
            resolution=resolution,
        )

    setattr(assessment_at_exact_commit, _ASSESSMENT_MARKER, True)
    setattr(assessment_at_exact_commit, "_nico_previous", current)
    setattr(api_main, attribute, assessment_at_exact_commit)
    return {
        "status": "installed",
        "function": attribute,
        "owner_verified": getattr(getattr(api_main, attribute), _ASSESSMENT_MARKER, False) is True,
    }


def install_exact_commit_binding() -> dict[str, Any]:
    from nico.api import main as api_main

    client_reads = _install_exact_github_reads()
    scanner_checkout = _install_exact_scanner_checkout()
    direct = _install_assessment_binding(api_main, "run_github_assessment")
    scanner = _install_assessment_binding(api_main, "run_github_assessment_with_scanner_artifacts")
    return {
        "artifact_schema": EXACT_COMMIT_BINDING_VERSION,
        "status": "installed",
        "github_reads": client_reads,
        "scanner_checkout": scanner_checkout,
        "direct_assessment": direct,
        "scanner_assessment": scanner,
        "shared_snapshot_resolver": True,
        "anonymous_exact_sha_fallback": True,
        "preverified_resolution_reused": True,
        "expected_commit_marker_supported": True,
        "default_branch_resolved_once_when_marker_absent": True,
        "repository_files_bound_to_exact_commit": True,
        "scanner_bound_to_exact_commit": True,
        "conflicting_commit_metadata_authoritative": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "EXACT_COMMIT_BINDING_VERSION",
    "expected_commit_sha",
    "install_exact_commit_binding",
]
