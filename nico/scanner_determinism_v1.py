from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import replace
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Mapping

VERSION = "nico.scanner-determinism.v1"
_INSTALLED = False
_STATUS: dict[str, Any] = {}
_VOLATILE_KEYS = {
    "analysis_time",
    "created_at",
    "elapsed",
    "elapsed_ms",
    "end_time",
    "execution_time",
    "generated_at",
    "observed_at",
    "scan_completed_at",
    "scan_started_at",
    "started_at",
    "timestamp",
    "updated_at",
}


def _digest(value: Any) -> str:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _relative(value: str, repo_dir: Path) -> str:
    text = str(value or "").replace("\\", "/")
    root = str(repo_dir.resolve()).replace("\\", "/").rstrip("/")
    return text[len(root) + 1 :] if text.startswith(root + "/") else text


def _canonical(value: Any, repo_dir: Path) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _canonical(child, repo_dir)
            for key, child in sorted(value.items(), key=lambda item: str(item[0]))
            if str(key).casefold() not in _VOLATILE_KEYS
        }
    if isinstance(value, list):
        items = [_canonical(child, repo_dir) for child in value]
        return sorted(
            items,
            key=lambda child: json.dumps(
                child,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
            ),
        )
    if isinstance(value, tuple):
        return _canonical(list(value), repo_dir)
    if isinstance(value, str):
        return _relative(value, repo_dir)
    return value


def canonicalize_findings(
    findings: list[Any],
    repo_dir: Path,
) -> tuple[list[Any], dict[str, Any]]:
    unique: dict[str, Any] = {}
    for finding in findings:
        normalized = _canonical(finding, repo_dir)
        unique.setdefault(_digest(normalized), normalized)
    ordered = [unique[key] for key in sorted(unique)]
    return ordered, {
        "raw_count": len(findings),
        "canonical_count": len(ordered),
        "duplicates_removed": max(0, len(findings) - len(ordered)),
        "volatile_fields_excluded": sorted(_VOLATILE_KEYS),
        "ordering": "normalized_finding_sha256",
    }


def clone_repository_at_snapshot(
    repository: str,
    commit_sha: str,
    workspace: Path,
    env: dict[str, str],
) -> tuple[Path | None, str, list[str]]:
    """Materialize only history reachable from the immutable assessed commit."""

    from nico import scanner_worker as base
    from nico import snapshot_scanner_worker as snapshot

    if shutil.which("git") is None:
        return None, "", ["git is unavailable in this worker image."]
    if not snapshot._COMMIT_SHA_RE.fullmatch(str(commit_sha or "")):
        return None, "", ["A valid full snapshot commit SHA is required."]

    repo_dir = workspace / "repo"
    repo_dir.mkdir(parents=True, exist_ok=False)

    def run(command: list[str], timeout: int = 180):
        return snapshot._git(command, cwd=repo_dir, env=env, timeout=timeout)

    initialized = snapshot._git(
        ["git", "init", "--quiet", str(repo_dir)],
        cwd=None,
        env=env,
        timeout=30,
    )
    if initialized.returncode != 0:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, "", ["Snapshot repository initialization failed."]
    remote = run(["git", "remote", "add", "origin", base.safe_repo_url(repository)], 30)
    if remote.returncode != 0:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, "", ["Snapshot repository remote setup failed."]
    fetched = run(
        [
            "git",
            "-c",
            "protocol.version=2",
            "fetch",
            "--force",
            "--no-tags",
            "origin",
            commit_sha,
        ],
        300,
    )
    if fetched.returncode != 0:
        preview, _ = base.redact((fetched.stdout or "") + "\n" + (fetched.stderr or ""))
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, "", [f"Exact snapshot ancestry fetch failed: {preview[:800]}"]
    checked_out = run(["git", "checkout", "--detach", "--force", "FETCH_HEAD"])
    if checked_out.returncode != 0:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, "", ["Exact snapshot checkout failed."]
    resolved = run(["git", "rev-parse", "HEAD"], 30)
    actual = str(resolved.stdout or "").strip().casefold()
    if resolved.returncode != 0 or actual != commit_sha.casefold():
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, actual, ["Scanner checkout did not match the assessed commit."]
    refs = run(
        [
            "git",
            "for-each-ref",
            "--format=%(refname)",
            "refs/heads",
            "refs/remotes",
            "refs/tags",
        ],
        30,
    )
    retained = [line for line in str(refs.stdout or "").splitlines() if line.strip()]
    if refs.returncode != 0 or retained:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, actual, ["Snapshot checkout retained mutable branch, remote, or tag refs."]
    size = base.directory_size(repo_dir)
    if size > base.MAX_REPO_BYTES:
        shutil.rmtree(repo_dir, ignore_errors=True)
        return None, actual, [f"Repository exceeds scanner size limit: {size} bytes."]
    return repo_dir, actual, []


def _replace_specs(specs: tuple[Any, ...]) -> tuple[Any, ...]:
    rules = Path(__file__).with_name("semgrep_rules_v1.yml").resolve()
    updated: list[Any] = []
    for spec in specs:
        if spec.name == "semgrep":
            updated.append(
                replace(
                    spec,
                    command=(
                        "semgrep",
                        "scan",
                        "--config",
                        str(rules),
                        "--json",
                        "--jobs",
                        "1",
                        "--max-memory",
                        "1024",
                        "--timeout",
                        "30",
                        "--exclude",
                        "node_modules",
                        "--exclude",
                        ".next",
                        "--exclude",
                        "dist",
                        "--exclude",
                        "build",
                        ".",
                    ),
                )
            )
        elif spec.name == "gitleaks":
            updated.append(
                replace(
                    spec,
                    command=(
                        "gitleaks",
                        "detect",
                        "--no-banner",
                        "--redact",
                        "--report-format",
                        "json",
                        "--source",
                        ".",
                        "--log-opts",
                        "HEAD",
                    ),
                )
            )
        elif spec.name == "trufflehog":
            updated.append(
                replace(
                    spec,
                    command=(
                        "trufflehog",
                        "git",
                        "file://{repo_dir}",
                        "--json",
                        "--no-update",
                        "--no-verification",
                        "--branch",
                        "HEAD",
                    ),
                )
            )
        else:
            updated.append(spec)
    return tuple(updated)


def _resolve_eslint(
    original: Callable[..., Any],
    spec: Any,
    workspace: Any,
    preparation: Any,
):
    command, cwd, reason = original(spec, workspace, preparation)
    if spec.name != "eslint" or command is not None:
        return command, cwd, reason
    from nico import scanner_tool_runners as runners

    web = workspace.repo_dir / "apps" / "web"
    configured = runners._has_eslint_config(web) or bool(runners._package_script(web, "lint"))
    binary = shutil.which("eslint")
    module_root = Path(os.getenv("NICO_ESLINT_MODULE_ROOT", "/usr/local/lib/node_modules"))
    parser = Path(
        os.getenv(
            "NICO_ESLINT_PARSER_ENTRY",
            "/usr/local/lib/node_modules/@typescript-eslint/parser/dist/index.js",
        )
    )
    eslint_js = module_root / "@eslint" / "js" / "package.json"
    if (
        configured
        and preparation is not None
        and preparation.node_modules_ready
        and binary
        and parser.is_file()
        and eslint_js.is_file()
    ):
        return (binary, ".", "--format", "json"), web, None
    return command, cwd, reason


def _tool_version(spec: Any, workspace: Any) -> str:
    from nico.worker_execution import WorkerLimits, run_command

    web = workspace.repo_dir / "apps" / "web"
    binary = (
        web / "node_modules" / ".bin" / spec.command[0]
        if spec.name in {"eslint", "typescript"}
        else Path(shutil.which(str(spec.command[0])) or "")
    )
    if not binary.is_file():
        candidate = shutil.which(str(spec.command[0]))
        binary = Path(candidate) if candidate else Path()
    if not binary.is_file():
        return "unavailable"
    result = run_command(
        (str(binary), "--version"),
        cwd=workspace.repo_dir,
        limits=WorkerLimits(timeout_seconds=20, max_output_chars=2000),
        extra_env={"CI": "true", "NO_COLOR": "1", "FORCE_COLOR": "0"},
        stdout_path=None,
    )
    return " ".join(((result.stdout or "") + " " + (result.stderr or "")).split())[:300] or "unavailable"


def _wrap_result(original: Callable[..., dict[str, Any]], spec: Any, workspace: Any, *args: Any, **kwargs: Any) -> dict[str, Any]:
    result = original(spec, workspace, *args, **kwargs)
    if not isinstance(result, dict):
        return result
    canonical, summary = canonicalize_findings(list(result.get("findings") or []), workspace.repo_dir)
    result["findings"] = canonical
    version = _tool_version(spec, workspace)
    rules = Path(__file__).with_name("semgrep_rules_v1.yml")
    config = {
        "tool": spec.name,
        "tool_version": version,
        "command": ["nico/semgrep_rules_v1.yml" if str(part) == str(rules.resolve()) else str(part) for part in spec.command],
        "rules_sha256": hashlib.sha256(rules.read_bytes()).hexdigest() if spec.name == "semgrep" and rules.is_file() else "",
        "history_scope": "reachable_ancestry_at_assessed_commit" if spec.scans_git_history else "current_tree",
    }
    result["finding_canonicalization"] = summary
    result["tool_version"] = version
    result["scanner_configuration_fingerprint"] = _digest(config)
    result["scanner_evidence_fingerprint"] = _digest(
        {
            "status": result.get("status"),
            "returncode": result.get("returncode"),
            "configuration": result["scanner_configuration_fingerprint"],
            "findings": canonical,
        }
    )
    result["determinism_contract"] = {
        "version": VERSION,
        "same_input_same_output_required": True,
        "mutable_runtime_order_affects_result": False,
        "descendant_refs_excluded": bool(spec.scans_git_history),
    }
    if spec.name == "osv-scanner" and result.get("fallback") == "OSV querybatch API":
        result["execution_source"] = "osv_api_fallback"
        result["current_run"] = True
    if spec.scans_git_history:
        completed = result.get("status") == "completed"
        result["history_scope"] = "reachable_ancestry_at_assessed_commit"
        result["history_depth_verified"] = completed
        result["full_history_verified"] = completed
        result["descendant_refs_scanned"] = False
    return result


def install_scanner_determinism() -> dict[str, Any]:
    global _INSTALLED, _STATUS
    if _INSTALLED:
        return dict(_STATUS)
    from nico import scanner_tool_runners as runners
    from nico import snapshot_scanner_worker as snapshot

    snapshot.clone_repository_at_snapshot = clone_repository_at_snapshot
    runners.TOOL_SPECS = _replace_specs(runners.TOOL_SPECS)

    resolver = runners._resolve_command_and_cwd
    if not getattr(resolver, "__nico_deterministic_eslint__", False):
        @wraps(resolver)
        def resolved(spec: Any, workspace: Any, preparation: Any):
            return _resolve_eslint(resolver, spec, workspace, preparation)

        resolved.__nico_deterministic_eslint__ = True
        runners._resolve_command_and_cwd = resolved

    runner = runners.run_scanner_tool
    if not getattr(runner, "__nico_deterministic_runner__", False):
        @wraps(runner)
        def deterministic(spec: Any, workspace: Any, *args: Any, **kwargs: Any):
            deterministic_spec = _replace_specs((spec,))[0]
            return _wrap_result(runner, deterministic_spec, workspace, *args, **kwargs)

        deterministic.__nico_deterministic_runner__ = True
        runners.run_scanner_tool = deterministic

    _INSTALLED = True
    _STATUS = {
        "version": VERSION,
        "installed": True,
        "exact_commit_ancestry_clone_bound": True,
        "descendant_refs_excluded_from_history_scans": True,
        "history_scanners_bound_to_head": True,
        "local_semgrep_ruleset_bound": True,
        "eslint_configuration_must_execute": True,
        "findings_canonicalized_and_deduplicated": True,
        "scanner_fingerprints_retained": True,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }
    return dict(_STATUS)


__all__ = [
    "VERSION",
    "canonicalize_findings",
    "clone_repository_at_snapshot",
    "install_scanner_determinism",
]
