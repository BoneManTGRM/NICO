from __future__ import annotations

from functools import wraps
from typing import Any, Callable

from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult

SCANNER_OUTPUT_TRUTH_COMPAT_VERSION = "nico.scanner_output_truth_compat.v1"
_MARKER = "_nico_scanner_output_truth_clean_gitleaks_v1"


def install_scanner_output_truth_compat() -> dict[str, Any]:
    from nico import hosted_secret_scanner_execution_patch as secret

    current: Callable[..., dict[str, Any]] = secret._completed
    if getattr(current, _MARKER, False):
        return {
            "status": "already_installed",
            "version": SCANNER_OUTPUT_TRUTH_COMPAT_VERSION,
        }

    @wraps(current)
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
        return current(spec, normalized, **kwargs)

    setattr(completed_with_clean_gitleaks_contract, _MARKER, True)
    setattr(completed_with_clean_gitleaks_contract, "_nico_previous", current)
    secret._completed = completed_with_clean_gitleaks_contract
    return {
        "status": "installed",
        "version": SCANNER_OUTPUT_TRUTH_COMPAT_VERSION,
        "clean_gitleaks_exit_zero_explicit_empty_json": True,
        "nonzero_empty_gitleaks_treated_as_clean": False,
        "timeout_treated_as_clean": False,
        "truncated_output_treated_as_clean": False,
        "human_review_required": True,
        "client_delivery_allowed": False,
    }


__all__ = [
    "SCANNER_OUTPUT_TRUTH_COMPAT_VERSION",
    "install_scanner_output_truth_compat",
]
