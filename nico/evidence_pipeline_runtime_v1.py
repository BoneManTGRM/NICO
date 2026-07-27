from __future__ import annotations

from typing import Any

from nico.evidence_pipeline_common_v1 import (
    _REQUIRED_REPEATABILITY_TOOLS,
    _exact_sha,
    _immutable_sha,
)
from nico.evidence_pipeline_runner_v1 import _artifact_hash


def _patch_exact_sha_checkout() -> None:
    from nico import hosted_scanner_worker as hosted

    original = getattr(hosted, "_nico_original_checkout_for_evidence_pipeline_repair_v1", None)
    if original is None:
        original = hosted.checkout_for_hosted_scan
        hosted._nico_original_checkout_for_evidence_pipeline_repair_v1 = original

    def checkout_for_hosted_scan(payload: dict[str, Any], workspace: Any) -> Any:
        ref = _exact_sha(payload.get("ref") or payload.get("commit_sha") or payload.get("target_commit_sha"))
        if not ref:
            return original(payload, workspace)
        repository = hosted.validate_repository(str(payload.get("repository") or ""))
        clone_url = f"https://github.com/{repository}.git"
        clone_auth = hosted.build_github_clone_auth_env()
        clone = hosted.run_command(
            ("git", "clone", "--no-tags", clone_url, str(workspace.repo_dir)),
            cwd=workspace.root,
            limits=hosted.WorkerLimits(timeout_seconds=360, max_output_chars=20_000),
            extra_env=clone_auth.extra_env,
        )
        if not clone.ok:
            return clone
        checkout = hosted.run_command(
            ("git", "checkout", "--detach", ref),
            cwd=workspace.repo_dir,
            limits=hosted.WorkerLimits(timeout_seconds=120, max_output_chars=20_000),
            extra_env=clone_auth.extra_env,
        )
        if checkout.ok:
            verified = hosted.run_command(
                ("git", "rev-parse", "HEAD"),
                cwd=workspace.repo_dir,
                limits=hosted.WorkerLimits(timeout_seconds=30, max_output_chars=2_000),
                extra_env=clone_auth.extra_env,
            )
            if not verified.ok or _exact_sha(verified.stdout) != ref:
                return hosted.WorkerCommandResult(
                    args=("git", "checkout", "--detach", ref),
                    returncode=2,
                    stdout=verified.stdout,
                    stderr="Exact-SHA checkout verification failed.",
                    timed_out=verified.timed_out,
                    output_truncated=verified.output_truncated,
                    stdout_bytes=verified.stdout_bytes,
                    stderr_bytes=verified.stderr_bytes,
                )
        return checkout

    hosted.checkout_for_hosted_scan = checkout_for_hosted_scan


def _patch_fixed_sha_payload() -> None:
    from nico import hosted_full_evidence_runtime_v2 as runtime

    original = getattr(runtime, "_nico_original_payload_for_evidence_pipeline_repair_v1", None)
    if original is None:
        original = runtime._payload_for_result
        runtime._nico_original_payload_for_evidence_pipeline_repair_v1 = original

    def payload_for_result(result: dict[str, Any]) -> dict[str, Any]:
        payload = original(result)
        commit_sha = _immutable_sha(result)
        if commit_sha:
            payload["ref"] = commit_sha
            payload["commit_sha"] = commit_sha
            payload["target_commit_sha"] = commit_sha
        repository = str(payload.get("repository") or "").strip().casefold()
        required = result.get("required_consecutive_scanner_runs")
        if required is None and repository == "bonemantgrm/nico" and commit_sha:
            required = 2
        if required is not None:
            try:
                payload["required_consecutive_runs"] = max(1, min(2, int(required)))
            except (TypeError, ValueError):
                payload["required_consecutive_runs"] = 2
        return payload

    runtime._payload_for_result = payload_for_result


def _artifact_clean(artifact: dict[str, Any], target_sha: str) -> bool:
    from nico.scanner_worker_artifacts import normalize_scanner_worker_artifact

    if str(artifact.get("worker_execution_state") or "") != "completed":
        return False
    checkout = artifact.get("checkout") if isinstance(artifact.get("checkout"), dict) else {}
    if target_sha and _exact_sha(checkout.get("commit_sha")) != target_sha:
        return False
    normalized = artifact.get("normalized") if isinstance(artifact.get("normalized"), dict) else normalize_scanner_worker_artifact(artifact)
    tools = normalized.get("tools") if isinstance(normalized.get("tools"), dict) else {}
    for tool in _REQUIRED_REPEATABILITY_TOOLS:
        tool_data = tools.get(tool) if isinstance(tools.get(tool), dict) else {}
        if not tool_data.get("completed"):
            return False
    if not normalized.get("secret_history_evidence_complete"):
        return False
    return True


def _repeatability_run_record(artifact: dict[str, Any]) -> dict[str, Any]:
    return {
        "artifact_hash": artifact.get("artifact_hash"),
        "repeatability_fingerprint": artifact.get("repeatability_fingerprint"),
        "worker_execution_state": artifact.get("worker_execution_state"),
        "checkout": artifact.get("checkout"),
        "tools": artifact.get("tools"),
        "raw_output_artifacts": artifact.get("raw_output_artifacts"),
        "normalized": artifact.get("normalized"),
    }


def _merge_repeatability_artifacts(artifacts: list[dict[str, Any]], target_sha: str) -> dict[str, Any]:
    final = dict(artifacts[-1])
    fingerprints = [str(item.get("repeatability_fingerprint") or "") for item in artifacts]
    commits = [
        _exact_sha((item.get("checkout") or {}).get("commit_sha"))
        if isinstance(item.get("checkout"), dict)
        else ""
        for item in artifacts
    ]
    clean = [_artifact_clean(item, target_sha) for item in artifacts]
    passed = bool(
        len(artifacts) >= 2
        and all(clean)
        and all(commit == target_sha for commit in commits)
        and len(set(fingerprints)) == 1
        and bool(fingerprints[0])
    )
    final["repeatability"] = {
        "required_runs": 2,
        "completed_runs": len(artifacts),
        "clean_runs": sum(1 for item in clean if item),
        "target_commit_sha": target_sha,
        "observed_commit_shas": commits,
        "fingerprints": fingerprints,
        "stable": len(set(fingerprints)) == 1 and bool(fingerprints[0]),
        "passed": passed,
        "run_artifacts": [_repeatability_run_record(item) for item in artifacts],
    }
    final["repeatability_verified"] = passed
    final["provenance_verified"] = bool(final.get("provenance_verified")) and passed
    if not passed:
        final["worker_execution_state"] = "partial"
        final["reason"] = "scanner_repeatability_gate_failed"
    final["artifact_hash"] = _artifact_hash(final)
    return final


def _patch_repeatable_hosted_worker() -> None:
    from nico import hosted_full_evidence_runtime_v2 as runtime
    from nico import hosted_scanner_worker as hosted

    original = getattr(hosted, "_nico_original_run_hosted_scanner_worker_evidence_pipeline_repair_v1", None)
    if original is None:
        original = hosted.run_hosted_scanner_worker
        hosted._nico_original_run_hosted_scanner_worker_evidence_pipeline_repair_v1 = original

    def run_hosted_scanner_worker(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            required_runs = max(1, min(2, int(payload.get("required_consecutive_runs") or 1)))
        except (TypeError, ValueError):
            required_runs = 1
        if required_runs == 1:
            return original(payload)
        artifacts = [original(dict(payload)) for _ in range(required_runs)]
        if not all(isinstance(item, dict) for item in artifacts):
            return artifacts[-1] if isinstance(artifacts[-1], dict) else {}
        target_sha = _exact_sha(payload.get("ref") or payload.get("commit_sha") or payload.get("target_commit_sha"))
        return _merge_repeatability_artifacts(artifacts, target_sha)

    hosted.run_hosted_scanner_worker = run_hosted_scanner_worker
    runtime.run_hosted_scanner_worker = run_hosted_scanner_worker


__all__ = [
    "_merge_repeatability_artifacts",
    "_patch_exact_sha_checkout",
    "_patch_fixed_sha_payload",
    "_patch_repeatable_hosted_worker",
]
