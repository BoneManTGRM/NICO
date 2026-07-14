from __future__ import annotations

from pathlib import Path
from typing import Any

from nico.cli_entrypoint import main
from nico.local_governance_service import decide_action
from nico.local_memory_service import memory_summary as _memory_summary
from nico.local_reporting_service import (
    analyze_memory,
    generate_reports as _generate_reports,
    report_text as _report_text,
)
from nico.local_runtime_config import (
    DB_PATH,
    DRIFT_REPO,
    NICO_HOME,
    PROJECT_ROOT,
    REPORT_DIR,
    SAMPLE_REPO,
    TEST_LAB,
)
from nico.local_scan_engine import (
    APPSEC_PATTERNS,
    OPTIONAL_TOOLS,
    SAFE_SCAN_PART_RE,
    SECRET_PATTERNS,
    SEVERITY_POINTS,
    SKIP_SCAN_DIRS,
    allowed_scan_bases,
    detect_drift,
    fingerprint,
    make_baseline,
    mask,
    mask_text,
    new_id,
    normalized_finding,
    now,
    resolve_scan_root_under_base,
    risk_score,
    safe_scan_file,
    safe_scan_files,
    safe_scan_root,
    safe_target_parts_for_base,
    scan_repo,
    scan_text,
    scanner_availability,
)
from nico.local_scan_service import ensure_test_lab, run_scan, scan_drift_demo, scan_test_lab
from nico.local_scoring_repair_service import (
    REPAIR_LIBRARY,
    apply_rye as _apply_rye,
    repairs_for as _repairs_for,
    rye_score as _rye_score,
)
from nico.local_store import DEFAULT_POLICY, LocalStore
from nico.local_verification_service import (
    verify_latest as _verify_latest,
    verify_repair_by_id as _verify_repair_by_id,
)


class Store(LocalStore):
    """Legacy constructor-compatible alias for the extracted local SQLite store."""

    def __init__(self, path: Path = DB_PATH) -> None:
        super().__init__(path)


fp = fingerprint
_allowed_scan_bases = allowed_scan_bases
_safe_target_parts_for_base = safe_target_parts_for_base
_resolve_scan_root_under_base = resolve_scan_root_under_base
_safe_scan_root = safe_scan_root
_safe_scan_file = safe_scan_file
_safe_scan_files = safe_scan_files


def rye_score(
    finding: dict[str, Any],
    memory: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return _rye_score(finding, memory)


def apply_rye(
    findings: list[dict[str, Any]],
    memory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _apply_rye(findings, memory)


def repairs_for(
    findings: list[dict[str, Any]],
    memory: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    return _repairs_for(findings, memory, id_factory=new_id, clock=now)


def generate_reports() -> list[dict[str, str]]:
    return _generate_reports(store=Store(), report_dir=REPORT_DIR)


def report_text(kind: str) -> str:
    return _report_text(kind, store=Store(), report_dir=REPORT_DIR)


def verify_latest() -> dict[str, Any]:
    return _verify_latest(store=Store(), id_factory=new_id, clock=now)


def verify_repair_by_id(repair_id: str) -> dict[str, Any]:
    return _verify_repair_by_id(
        repair_id,
        store=Store(),
        id_factory=new_id,
        clock=now,
    )


def memory_summary() -> dict[str, Any]:
    return _memory_summary(store=Store())


__all__ = [
    "PROJECT_ROOT",
    "NICO_HOME",
    "DB_PATH",
    "REPORT_DIR",
    "TEST_LAB",
    "SAMPLE_REPO",
    "DRIFT_REPO",
    "SECRET_PATTERNS",
    "SEVERITY_POINTS",
    "DEFAULT_POLICY",
    "OPTIONAL_TOOLS",
    "APPSEC_PATTERNS",
    "REPAIR_LIBRARY",
    "SKIP_SCAN_DIRS",
    "SAFE_SCAN_PART_RE",
    "now",
    "new_id",
    "fp",
    "fingerprint",
    "mask",
    "mask_text",
    "scanner_availability",
    "decide_action",
    "Store",
    "LocalStore",
    "normalized_finding",
    "scan_text",
    "allowed_scan_bases",
    "safe_target_parts_for_base",
    "resolve_scan_root_under_base",
    "safe_scan_root",
    "safe_scan_file",
    "safe_scan_files",
    "scan_repo",
    "risk_score",
    "make_baseline",
    "detect_drift",
    "rye_score",
    "apply_rye",
    "repairs_for",
    "analyze_memory",
    "ensure_test_lab",
    "generate_reports",
    "report_text",
    "run_scan",
    "scan_test_lab",
    "scan_drift_demo",
    "verify_latest",
    "verify_repair_by_id",
    "memory_summary",
    "main",
]


if __name__ == "__main__":
    main()
