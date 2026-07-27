from __future__ import annotations

import shutil
from typing import Any

from nico.evidence_pipeline_common_v1 import VERSION
from nico.evidence_pipeline_runner_v1 import _build_scanner_runner
from nico.evidence_pipeline_runtime_v1 import (
    _merge_repeatability_artifacts,
    _patch_exact_sha_checkout,
    _patch_fixed_sha_payload,
    _patch_repeatable_hosted_worker,
)

_PATCH_MARKER = "_nico_evidence_pipeline_repair_v1"


def install_evidence_pipeline_repair_v1() -> dict[str, Any]:
    from nico import hosted_scanner_worker
    from nico import scanner_tool_runners as runners
    from nico import scanner_worker_artifacts

    if getattr(runners, _PATCH_MARKER, False):
        return {"status": "already_installed", "version": VERSION}

    scanner_worker_artifacts.COMPLETED_STATUSES.add("not_applicable")
    run_scanner_tool, run_scanner_tools = _build_scanner_runner()
    runners.run_scanner_tool = run_scanner_tool
    runners.run_scanner_tools = run_scanner_tools
    hosted_scanner_worker.run_scanner_tools = run_scanner_tools
    _patch_exact_sha_checkout()
    _patch_fixed_sha_payload()
    _patch_repeatable_hosted_worker()
    setattr(runners, _PATCH_MARKER, True)
    return {
        "status": "installed",
        "version": VERSION,
        "fixed_sha_checkout": True,
        "two_run_repeatability_gate": True,
        "bandit_complete_output_limit_bytes": runners.MAX_SCANNER_PARSE_BYTES,
        "monorepo_node_project_discovery": True,
        "shared_lockfile_preparation": True,
        "eslint_without_configuration_not_applicable": True,
        "osv_full_exact_dependency_batches": True,
        "gitleaks_full_history_scope": True,
        "retrospective_self_assessment_supported": True,
        "raw_output_hash_manifest": True,
    }


__all__ = [
    "VERSION",
    "install_evidence_pipeline_repair_v1",
    "_merge_repeatability_artifacts",
    "shutil",
]
