from __future__ import annotations

import os
from dataclasses import replace
from functools import wraps
from typing import Any, Callable

from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult

SCANNER_OUTPUT_TRUTH_COMPAT_VERSION = "nico.scanner_output_truth_compat.v3"
_COMPLETE_MARKER = "_nico_scanner_output_truth_clean_gitleaks_v1"
_RUN_MARKER = "_nico_scanner_history_timeout_ceiling_v2"
_GITLEAKS_ABSOLUTE_CEILING_SECONDS = 120
_TRUFFLEHOG_ABSOLUTE_CEILING_SECONDS = 180


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)).strip())
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _history_timeout_cap(spec: ScannerToolSpec) -> int:
    # The generic setting may shorten a history scan, but it may never extend a
    # tool beyond NICO's absolute non-blocking ceiling. A deployment-level value
    # left over from an older release therefore cannot recreate the stall.
    generic_cap = _bounded_int("NICO_HISTORY_TOOL_TIMEOUT_SECONDS", 300, 30, 900)
    if spec.name == "gitleaks":
        configured = _bounded_int(
            "NICO_GITLEAKS_TIMEOUT_SECONDS",
            _GITLEAKS_ABSOLUTE_CEILING_SECONDS,
            30,
            _GITLEAKS_ABSOLUTE_CEILING_SECONDS,
        )
        return min(generic_cap, configured, _GITLEAKS_ABSOLUTE_CEILING_SECONDS)
    if spec.name == "trufflehog":
        configured = _bounded_int(
            "NICO_TRUFFLEHOG_TIMEOUT_SECONDS",
            _TRUFFLEHOG_ABSOLUTE_CEILING_SECONDS,
            30,
            _TRUFFLEHOG_ABSOLUTE_CEILING_SECONDS,
        )
        return min(generic_cap, configured, _TRUFFLEHOG_ABSOLUTE_CEILING_SECONDS)
    return generic_cap


def install_scanner_output_truth_compat() -> dict[str, Any]:
    from nico import hosted_secret_scanner_execution_patch as secret

    installed: dict[str, bool] = {}

    current_completed: Callable[..., dict[str, Any]] = secret._completed
    if not getattr(current_completed, _COMPLETE_MARKER, False):
        @wraps(current_completed)
        def completed_with_clean_gitleaks_contract(
            spec: ScannerToolSpec,
            result: WorkerCommandResult,
            **kwargs: Any,
        ) -> dict[str, Any]:
            normalized = result
            if (
                spec.name == "gitleaks"
                and result.returncode == 0
                and not result.timed_out
                and not result.output_truncated
                and not str(result.stdout or "").strip()
            ):
                # gitleaks may omit an empty report file on a clean run. Exit code 0
                # plus complete, non-truncated execution is the documented clean
                # boundary; represent it as an explicit empty JSON report so the
                # parser remains fail-closed for every other case.
                normalized = WorkerCommandResult(
                    args=result.args,
                    returncode=result.returncode,
                    stdout="[]",
                    stderr=result.stderr,
                    timed_out=False,
                    output_truncated=False,
                )
            return current_completed(spec, normalized, **kwargs)

        setattr(completed_with_clean_gitleaks_contract, _COMPLETE_MARKER, True)
        setattr(completed_with_clean_gitleaks_contract, "_nico_previous", current_completed)
        secret._completed = completed_with_clean_gitleaks_contract
        installed["clean_gitleaks_contract"] = True

    current_run: Callable[..., dict[str, Any]] = secret._run_secret_tool
    if not getattr(current_run, _RUN_MARKER, False):
        # Bypass the legacy minimum-timeout wrapper and impose a true ceiling.
        # This remains fail-closed: a timed-out scan is disclosed as unverified,
        # then the snapshot pipeline continues to the next requested tool.
        underlying_run: Callable[..., dict[str, Any]] = getattr(current_run, "_nico_previous", current_run)

        @wraps(current_run)
        def run_with_history_timeout_ceiling(
            spec: ScannerToolSpec,
            workspace: Any,
            *,
            runner: Callable[..., WorkerCommandResult],
        ) -> dict[str, Any]:
            timeout_cap = _history_timeout_cap(spec)
            output_floor = _bounded_int("NICO_SECRET_SCANNER_MAX_OUTPUT_CHARS", 500_000, 80_000, 2_000_000)
            effective_timeout = min(max(1, int(spec.timeout_seconds)), timeout_cap)
            bounded_spec = replace(
                spec,
                timeout_seconds=effective_timeout,
                max_output_chars=max(spec.max_output_chars, output_floor),
            )
            payload = underlying_run(bounded_spec, workspace, runner=runner)
            if not isinstance(payload, dict):
                return payload
            output = dict(payload)
            output.update(
                {
                    "requested_timeout_seconds": int(spec.timeout_seconds),
                    "timeout_limit_seconds": timeout_cap,
                    "effective_timeout_seconds": effective_timeout,
                    "timeout_policy": "absolute_hard_ceiling",
                    "timeout_ceiling_source": SCANNER_OUTPUT_TRUTH_COMPAT_VERSION,
                    "pipeline_blocking_allowed": False,
                }
            )
            return output

        setattr(run_with_history_timeout_ceiling, _RUN_MARKER, True)
        setattr(run_with_history_timeout_ceiling, "_nico_previous", current_run)
        secret._run_secret_tool = run_with_history_timeout_ceiling
        installed["history_timeout_ceiling"] = True

    return {
        "status": "installed" if installed else "already_installed",
        "version": SCANNER_OUTPUT_TRUTH_COMPAT_VERSION,
        "installed": installed,
        "clean_gitleaks_exit_zero_explicit_empty_json": True,
        "nonzero_empty_gitleaks_treated_as_clean": False,
        "timeout_treated_as_clean": False,
        "truncated_output_treated_as_clean": False,
        "history_timeout_is_hard_ceiling": True,
        "deployment_env_can_extend_absolute_ceiling": False,
        "gitleaks_timeout_seconds": _history_timeout_cap(
            ScannerToolSpec("gitleaks", ("gitleaks",), "secret", timeout_seconds=240)
        ),
        "trufflehog_timeout_seconds": _history_timeout_cap(
            ScannerToolSpec("trufflehog", ("trufflehog",), "secret", timeout_seconds=300)
        ),
        "single_scanner_can_block_pipeline": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "SCANNER_OUTPUT_TRUTH_COMPAT_VERSION",
    "install_scanner_output_truth_compat",
]
