from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Any

from nico import comprehensive_final_report_background_v1 as final_report_background
from nico import repository_snapshot

VERSION = "nico.comprehensive_production_runtime_recovery.v1"
_MARKER = "_nico_comprehensive_production_runtime_recovery_v1"
_DEFAULT_QUEUE_CAP_SECONDS = 180.0
_DEFAULT_RENDER_CAP_SECONDS = 900.0


def _public_default_head(repository: str) -> tuple[dict[str, Any] | None, str | None]:
    """Resolve one public GitHub default HEAD through isolated anonymous HTTPS Git."""

    if not repository_snapshot._SAFE_REPOSITORY_RE.fullmatch(repository):
        return None, "public_git_invalid_repository"
    repository_url = f"https://github.com/{repository}.git"
    try:
        with tempfile.TemporaryDirectory(prefix="nico-public-head-snapshot-") as temporary:
            workspace = Path(temporary)
            git_dir = workspace / "repository.git"
            git_dir.mkdir(mode=0o700)
            environment = repository_snapshot._git_environment(workspace)
            initialized = repository_snapshot._git_init_bare(
                git_dir,
                environment,
                runner=subprocess.run,
            )
            if initialized.returncode != 0:
                return None, "public_git_initialize_failed"
            repository_snapshot._configure_public_origin(git_dir, repository_url)
            fetched = subprocess.run(
                [
                    "git",
                    "-c",
                    "credential.helper=",
                    "-c",
                    "http.extraHeader=",
                    "fetch",
                    "--depth=1",
                    "--no-tags",
                    "origin",
                    "HEAD",
                ],
                cwd=str(git_dir),
                capture_output=True,
                text=True,
                timeout=60,
                check=False,
                shell=False,
                env=environment,
            )
            if fetched.returncode != 0:
                return None, "public_git_default_head_fetch_failed"
            described = repository_snapshot._git_describe_fetch_head(
                git_dir,
                environment,
                runner=subprocess.run,
            )
            if described.returncode != 0:
                return None, "public_git_commit_description_failed"
            fields = described.stdout.rstrip("\n").split("\x00", 3)
            if len(fields) != 4:
                return None, "public_git_commit_description_invalid"
            commit_sha, tree_sha, commit_date, message = fields
            commit_sha = commit_sha.strip().lower()
            tree_sha = tree_sha.strip().lower()
            if not repository_snapshot._EXACT_SHA_RE.fullmatch(commit_sha):
                return None, "public_git_commit_sha_invalid"
            if tree_sha and not repository_snapshot._SHA_RE.fullmatch(tree_sha):
                return None, "public_git_tree_sha_invalid"
            return {
                "sha": commit_sha,
                "commit": {
                    "committer": {"date": commit_date.strip()},
                    "author": {"date": commit_date.strip()},
                    "tree": {"sha": tree_sha},
                    "message": message.strip(),
                },
            }, None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None, "public_git_execution_failed"


def _install_repository_snapshot_fallback() -> dict[str, Any]:
    current = repository_snapshot.resolve_repository_commit
    if getattr(current, _MARKER, False):
        return {"bound": True, "changed": False}
    original = current

    def wrapped(context: dict[str, Any], *, client=None) -> dict[str, Any]:
        result = original(context, client=client)
        if not isinstance(result, dict) or result.get("status") != "unavailable":
            return result
        if str(result.get("resolution_failure_code") or "") != "repository_metadata_unavailable":
            return result
        repository = str(context.get("repository") or "").strip()
        expected_sha, binding_source = repository_snapshot._expected_commit_sha(context)
        if expected_sha or binding_source == "invalid_explicit_commit_sha":
            return result

        commit, error = _public_default_head(repository)
        if not commit:
            output = dict(result)
            output["public_git_default_head_fallback_attempted"] = True
            output["public_git_default_head_failure_code"] = str(
                error or "public_git_default_head_unavailable"
            )
            return output

        commit_sha = str(commit.get("sha") or "").strip().lower()
        commit_body = commit.get("commit") if isinstance(commit.get("commit"), dict) else {}
        tree = commit_body.get("tree") if isinstance(commit_body.get("tree"), dict) else {}
        return {
            "status": "attached",
            "repository": repository,
            "default_branch": "HEAD",
            "requested_ref": "HEAD",
            "expected_commit_sha": commit_sha,
            "commit_binding_source": "public_default_head_resolved_once",
            "repository_metadata_available": False,
            "repository_confirmed_private": False,
            "api_commit_lookup_attempts": 0,
            "public_git_fallback_attempted": True,
            "public_git_default_head_fallback_attempted": True,
            "commit_capture_method": "public_git_default_head",
            "commit_sha": commit_sha,
            "tree_sha": str(tree.get("sha") or "").strip().lower(),
            "commit_date": str(
                (commit_body.get("committer") or {}).get("date")
                or (commit_body.get("author") or {}).get("date")
                or ""
            ),
            "commit_message": str(commit_body.get("message") or "").strip(),
            "exact_commit_verified": True,
            "immutable_snapshot": True,
            "unavailable_data_notes": [
                "GitHub API metadata was unavailable, so NICO resolved the public repository default HEAD once through isolated credential-free HTTPS Git and bound the assessment to that exact immutable commit."
            ],
        }

    setattr(wrapped, _MARKER, True)
    setattr(wrapped, "__wrapped__", original)
    repository_snapshot.resolve_repository_commit = wrapped
    return {"bound": repository_snapshot.resolve_repository_commit is wrapped, "changed": True}


def _install_final_report_deadline_caps() -> dict[str, Any]:
    if getattr(final_report_background, _MARKER, False):
        return {"bound": True, "changed": False}
    original_queue = final_report_background._max_queue_seconds
    original_render = final_report_background._max_publication_seconds

    def bounded_queue_seconds() -> float:
        return min(float(original_queue()), _DEFAULT_QUEUE_CAP_SECONDS)

    def bounded_render_seconds() -> float:
        return min(float(original_render()), _DEFAULT_RENDER_CAP_SECONDS)

    final_report_background._max_queue_seconds = bounded_queue_seconds
    final_report_background._max_publication_seconds = bounded_render_seconds
    setattr(final_report_background, _MARKER, True)
    return {
        "bound": True,
        "changed": True,
        "max_queue_seconds": bounded_queue_seconds(),
        "max_publication_seconds": bounded_render_seconds(),
    }


def install_comprehensive_production_runtime_recovery() -> dict[str, Any]:
    """Install bounded fail-closed recovery for observed intake and report stalls."""

    snapshot = _install_repository_snapshot_fallback()
    final_report = _install_final_report_deadline_caps()
    return {
        "artifact_schema": VERSION,
        "status": (
            "installed"
            if snapshot.get("changed") or final_report.get("changed")
            else "already_installed"
        ),
        "bound": snapshot.get("bound") is True and final_report.get("bound") is True,
        "repository_snapshot_public_head_fallback": snapshot,
        "final_report_deadline_caps": final_report,
        "scoring_changed": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_comprehensive_production_runtime_recovery"]
