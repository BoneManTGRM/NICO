from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from nico.production_release_gate import build_production_release_manifest, safe_origin

DEFAULT_GITHUB_API = "https://api.github.com"


def _canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _headers(token: str = "", *, github: bool = False) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "nico-production-release-gate",
    }
    if github:
        headers["Accept"] = "application/vnd.github+json"
        headers["X-GitHub-Api-Version"] = "2022-11-28"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _request_json(
    url: str,
    *,
    token: str = "",
    github: bool = False,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = 30,
) -> tuple[Any, dict[str, Any]]:
    data = None
    headers = _headers(token, github=github)
    if payload is not None:
        data = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            raw = response.read().decode("utf-8")
            status_code = int(getattr(response, "status", None) or getattr(response, "code", 0) or 0)
    except HTTPError as exc:
        return {}, {"status": "failed", "error_type": "http_error", "status_code": int(exc.code)}
    except (URLError, TimeoutError, OSError):
        return {}, {"status": "failed", "error_type": "network_error", "status_code": None}
    try:
        value = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {}, {"status": "failed", "error_type": "invalid_json", "status_code": status_code}
    return value, {"status": "ok", "status_code": status_code}


def _github_url(api_base: str, repository: str, suffix: str) -> str:
    owner_repo = "/".join(quote(part, safe="") for part in repository.split("/", 1))
    return f"{api_base.rstrip('/')}/repos/{owner_repo}/{suffix.lstrip('/')}"


def collect_github_evidence(
    repository: str,
    expected_sha: str,
    *,
    token: str,
    api_base: str = DEFAULT_GITHUB_API,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    repo, repo_status = _request_json(
        _github_url(api_base, repository, ""),
        token=token,
        github=True,
        timeout_seconds=timeout_seconds,
    )
    repo_payload = repo if isinstance(repo, dict) else {}
    default_branch = str(repo_payload.get("default_branch") or "main")
    ref, ref_status = _request_json(
        _github_url(api_base, repository, f"git/ref/heads/{quote(default_branch, safe='')}") ,
        token=token,
        github=True,
        timeout_seconds=timeout_seconds,
    )
    ref_payload = ref if isinstance(ref, dict) else {}
    main_head_sha = str((ref_payload.get("object") or {}).get("sha") or "") if isinstance(ref_payload.get("object"), dict) else ""

    runs, runs_status = _request_json(
        _github_url(api_base, repository, f"actions/runs?head_sha={quote(expected_sha, safe='')}&per_page=100"),
        token=token,
        github=True,
        timeout_seconds=timeout_seconds,
    )
    checks, checks_status = _request_json(
        _github_url(api_base, repository, f"commits/{quote(expected_sha, safe='')}/check-runs?per_page=100"),
        token=token,
        github=True,
        timeout_seconds=timeout_seconds,
    )
    statuses, statuses_status = _request_json(
        _github_url(api_base, repository, f"commits/{quote(expected_sha, safe='')}/status"),
        token=token,
        github=True,
        timeout_seconds=timeout_seconds,
    )
    runs_payload = runs if isinstance(runs, dict) else {}
    checks_payload = checks if isinstance(checks, dict) else {}
    statuses_payload = statuses if isinstance(statuses, dict) else {}
    return {
        "default_branch": default_branch,
        "main_head_sha": main_head_sha,
        "workflow_runs": runs_payload.get("workflow_runs") if isinstance(runs_payload.get("workflow_runs"), list) else [],
        "check_runs": checks_payload.get("check_runs") if isinstance(checks_payload.get("check_runs"), list) else [],
        "commit_statuses": statuses_payload.get("statuses") if isinstance(statuses_payload.get("statuses"), list) else [],
        "collection": {
            "repository": repo_status,
            "main_ref": ref_status,
            "workflow_runs": runs_status,
            "check_runs": checks_status,
            "commit_statuses": statuses_status,
        },
    }


def collect_deployment_evidence(
    backend_url: str,
    frontend_url: str,
    *,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    backend_origin = safe_origin(backend_url)
    frontend_origin = safe_origin(frontend_url)
    backend, backend_status = _request_json(
        f"{backend_origin}/operations/readiness" if backend_origin else "invalid://backend",
        timeout_seconds=timeout_seconds,
    )
    frontend, frontend_status = _request_json(
        f"{frontend_origin}/api/deployment" if frontend_origin else "invalid://frontend",
        timeout_seconds=timeout_seconds,
    )
    return {
        "backend": backend if isinstance(backend, dict) else {},
        "frontend": frontend if isinstance(frontend, dict) else {},
        "collection": {
            "backend_readiness": backend_status,
            "frontend_deployment": frontend_status,
        },
    }


def record_last_known_good(
    *,
    repository: str,
    release_sha: str,
    frontend_url: str,
    backend_url: str,
    release_identity_sha256: str,
    token: str,
    api_base: str = DEFAULT_GITHUB_API,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    if not token:
        return {"status": "blocked", "error_type": "github_token_missing"}
    deployment_payload = {
        "ref": release_sha,
        "environment": "production",
        "description": f"NICO last-known-good release {release_sha[:12]} identity {release_identity_sha256[:12]}",
        "auto_merge": False,
        "required_contexts": [],
        "transient_environment": False,
        "production_environment": True,
        "payload": {
            "artifact_schema": "nico.last_known_good.v1",
            "release_sha": release_sha,
            "release_identity_sha256": release_identity_sha256,
            "frontend_origin": safe_origin(frontend_url),
            "backend_origin": safe_origin(backend_url),
        },
    }
    deployment, deployment_status = _request_json(
        _github_url(api_base, repository, "deployments"),
        token=token,
        github=True,
        method="POST",
        payload=deployment_payload,
        timeout_seconds=timeout_seconds,
    )
    deployment_value = deployment if isinstance(deployment, dict) else {}
    deployment_id = deployment_value.get("id")
    if deployment_status.get("status") != "ok" or not deployment_id:
        return {"status": "blocked", "error_type": deployment_status.get("error_type") or "deployment_record_failed"}

    server = os.getenv("GITHUB_SERVER_URL", "https://github.com").rstrip("/")
    run_id = os.getenv("GITHUB_RUN_ID", "").strip()
    log_url = f"{server}/{repository}/actions/runs/{run_id}" if run_id else ""
    status_payload = {
        "state": "success",
        "description": f"Release gate passed for {release_sha[:12]}",
        "environment": "production",
        "environment_url": safe_origin(frontend_url),
        "auto_inactive": True,
    }
    if log_url:
        status_payload["log_url"] = log_url
    status_record, status_result = _request_json(
        _github_url(api_base, repository, f"deployments/{deployment_id}/statuses"),
        token=token,
        github=True,
        method="POST",
        payload=status_payload,
        timeout_seconds=timeout_seconds,
    )
    status_value = status_record if isinstance(status_record, dict) else {}
    if status_result.get("status") != "ok":
        return {
            "status": "blocked",
            "error_type": status_result.get("error_type") or "deployment_status_failed",
            "deployment_id": deployment_id,
        }
    return {
        "status": "recorded",
        "record_type": "github_production_deployment",
        "deployment_id": deployment_id,
        "deployment_status_id": status_value.get("id") or "",
        "release_sha": release_sha,
        "release_identity_sha256": release_identity_sha256,
        "environment": "production",
        "environment_url": safe_origin(frontend_url),
        "backend_origin": safe_origin(backend_url),
        "log_url": log_url,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Fail-closed NICO production release gate.")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--sha", default=os.getenv("GITHUB_SHA", ""))
    parser.add_argument("--backend-url", default=os.getenv("NICO_PRODUCTION_API_URL", ""))
    parser.add_argument("--frontend-url", default=os.getenv("NICO_PRODUCTION_FRONTEND_URL", ""))
    parser.add_argument("--github-api", default=os.getenv("GITHUB_API_URL", DEFAULT_GITHUB_API))
    parser.add_argument("--output", default="release-manifest.json")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--record-deployment", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    token = os.getenv("GITHUB_TOKEN", "").strip()
    collection_errors: dict[str, Any] = {}
    try:
        github = collect_github_evidence(
            args.repository,
            args.sha,
            token=token,
            api_base=args.github_api,
            timeout_seconds=max(5, args.timeout),
        )
    except Exception:
        github = {"main_head_sha": "", "workflow_runs": [], "check_runs": [], "commit_statuses": [], "collection": {}}
        collection_errors["github"] = "collection_failed"
    try:
        deployments = collect_deployment_evidence(
            args.backend_url,
            args.frontend_url,
            timeout_seconds=max(5, args.timeout),
        )
    except Exception:
        deployments = {"backend": {}, "frontend": {}, "collection": {}}
        collection_errors["deployments"] = "collection_failed"

    manifest = build_production_release_manifest(
        repository=args.repository,
        expected_sha=args.sha,
        main_head_sha=str(github.get("main_head_sha") or ""),
        workflow_runs=github.get("workflow_runs") if isinstance(github.get("workflow_runs"), list) else [],
        check_runs=github.get("check_runs") if isinstance(github.get("check_runs"), list) else [],
        commit_statuses=github.get("commit_statuses") if isinstance(github.get("commit_statuses"), list) else [],
        backend_readiness=deployments.get("backend") if isinstance(deployments.get("backend"), dict) else {},
        frontend_deployment=deployments.get("frontend") if isinstance(deployments.get("frontend"), dict) else {},
        backend_url=args.backend_url,
        frontend_url=args.frontend_url,
    )
    manifest["collection"] = {
        "github": github.get("collection") if isinstance(github.get("collection"), dict) else {},
        "deployments": deployments.get("collection") if isinstance(deployments.get("collection"), dict) else {},
        "errors": collection_errors,
    }

    if args.record_deployment:
        if manifest.get("release_ready") is True:
            manifest["last_known_good_record"] = record_last_known_good(
                repository=args.repository,
                release_sha=str(manifest.get("release_sha") or ""),
                frontend_url=args.frontend_url,
                backend_url=args.backend_url,
                release_identity_sha256=str(manifest.get("release_identity_sha256") or ""),
                token=token,
                api_base=args.github_api,
                timeout_seconds=max(5, args.timeout),
            )
            if manifest["last_known_good_record"].get("status") != "recorded":
                manifest["status"] = "blocked"
                manifest["release_ready"] = False
                manifest["last_known_good_eligible"] = False
                manifest.setdefault("blockers", []).append("last_known_good_record")
                manifest["next_action"] = "Fix GitHub deployment-record permissions and rerun the complete release gate."
        else:
            manifest["last_known_good_record"] = {"status": "not_recorded", "reason": "release_gate_blocked"}

    manifest.pop("manifest_sha256", None)
    manifest["manifest_sha256"] = _canonical_hash(manifest)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if manifest.get("release_ready") is True else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
