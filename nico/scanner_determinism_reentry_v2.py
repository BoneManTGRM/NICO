from __future__ import annotations

from dataclasses import replace
from functools import wraps
from typing import Any, Callable

from nico import scanner_determinism_v1 as determinism

VERSION = "nico.scanner-determinism-reentry.v4"
_MARKER = "__nico_scanner_determinism_reentry_v4__"
_HISTORY_MARKER = "__nico_exact_sha_history_metadata_v2__"
_ORIGINAL_ATTR = "_nico_scanner_determinism_original_installer_v4"


def _force_option(command: tuple[str, ...], option: str, value: str) -> tuple[str, ...]:
    parts = list(command)
    if option in parts:
        index = parts.index(option)
        if index + 1 < len(parts):
            parts[index + 1] = value
        else:
            parts.append(value)
    else:
        parts.extend((option, value))
    return tuple(parts)


def _head_scoped_spec(spec: Any) -> Any:
    command = tuple(getattr(spec, "command", ()) or ())
    name = str(getattr(spec, "name", "") or "").casefold()
    if name == "gitleaks":
        command = _force_option(command, "--log-opts", "HEAD")
    elif name == "trufflehog":
        command = _force_option(command, "--branch", "HEAD")
    if command == tuple(getattr(spec, "command", ()) or ()):
        return spec
    return replace(spec, command=command)


def _bind_history_metadata() -> None:
    from nico import scanner_tool_runners as runners

    current = runners.run_scanner_tool
    if getattr(current, _HISTORY_MARKER, False):
        return

    @wraps(current)
    def exact_sha_history_metadata(spec: Any, workspace: Any, *args: Any, **kwargs: Any):
        scoped_spec = _head_scoped_spec(spec) if bool(getattr(spec, "scans_git_history", False)) else spec
        result = current(scoped_spec, workspace, *args, **kwargs)
        if not isinstance(result, dict) or not bool(getattr(scoped_spec, "scans_git_history", False)):
            return result
        output = dict(result)
        completed = str(output.get("status") or "").casefold() == "completed"
        output["history_scope"] = "reachable_ancestry_at_assessed_commit"
        output["history_depth_verified"] = completed
        output["full_history_verified"] = completed
        output["immutable_head_selector"] = "HEAD"
        output["deterministic_head_selector_applied"] = True
        output["descendant_refs_scanned"] = False
        return output

    setattr(exact_sha_history_metadata, _HISTORY_MARKER, True)
    setattr(exact_sha_history_metadata, "_nico_previous", current)
    runners.run_scanner_tool = exact_sha_history_metadata


def install_scanner_determinism_reentry() -> dict[str, Any]:
    """Make the deterministic scanner installer safely re-entrant."""

    current: Callable[[], dict[str, Any]] = determinism.install_scanner_determinism
    if not getattr(current, _MARKER, False):
        original = getattr(determinism, _ORIGINAL_ATTR, current)

        @wraps(original)
        def reentrant_install() -> dict[str, Any]:
            determinism._INSTALLED = False
            status = dict(original())
            _bind_history_metadata()
            return status

        setattr(reentrant_install, _MARKER, True)
        setattr(reentrant_install, "_nico_previous", original)
        setattr(determinism, _ORIGINAL_ATTR, original)
        determinism.install_scanner_determinism = reentrant_install

    status = dict(determinism.install_scanner_determinism())
    from nico import scanner_tool_runners as runners
    from nico import snapshot_scanner_worker as snapshot

    clone_bound = snapshot.clone_repository_at_snapshot is determinism.clone_repository_at_snapshot
    runner_bound = bool(getattr(runners.run_scanner_tool, "__nico_deterministic_runner__", False))
    history_bound = bool(getattr(runners.run_scanner_tool, _HISTORY_MARKER, False))
    specs = {spec.name: spec for spec in runners.TOOL_SPECS}
    head_bound = bool(
        specs.get("gitleaks")
        and specs["gitleaks"].command[-1] == "HEAD"
        and specs.get("trufflehog")
        and specs["trufflehog"].command[-1] == "HEAD"
    )
    bound = clone_bound and runner_bound and history_bound and head_bound
    return {
        **status,
        "status": "installed" if bound else "blocked",
        "reentry_version": VERSION,
        "reentrant_installer_bound": bool(getattr(determinism.install_scanner_determinism, _MARKER, False)),
        "exact_commit_ancestry_clone_bound": clone_bound,
        "deterministic_runner_outermost": runner_bound,
        "exact_sha_history_metadata_bound": history_bound,
        "history_scanners_bound_to_head": head_bound,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = ["VERSION", "install_scanner_determinism_reentry"]
