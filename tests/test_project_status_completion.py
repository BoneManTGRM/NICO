from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "docs" / "PROJECT_STATUS.md"
MASTER_PLAN = ROOT / "MASTER_PLAN.md"
TRANSFORMATION_STATUS = ROOT / "STATUS.md"
DECISIONS = ROOT / "DECISIONS.md"
METRICS = ROOT / "METRICS.md"
RUNBOOK = ROOT / "RUNBOOK.md"
MANIFEST = ROOT / "tests" / "fixtures" / "golden" / "manifest.json"
DEMONSTRATION_WORKFLOW = ROOT / ".github" / "workflows" / "recorded-golden-demonstration.yml"
POSTGRES_RESTART_WORKFLOW = ROOT / ".github" / "workflows" / "postgres-restart-proof.yml"
RESILIENCE_WORKFLOW = ROOT / ".github" / "workflows" / "resilience-proof.yml"
CLI_ENTRYPOINT = ROOT / "nico" / "cli_entrypoint.py"
CLI_FACADE = ROOT / "nico" / "cli.py"
LOCAL_RUNTIME_CONFIG = ROOT / "nico" / "local_runtime_config.py"
LOCAL_SCAN_SERVICE = ROOT / "nico" / "local_scan_service.py"
LOCAL_STORE = ROOT / "nico" / "local_store.py"


def _source(path: Path = STATUS) -> str:
    return path.read_text(encoding="utf-8")


def test_transformation_control_documents_exist_and_are_authoritative() -> None:
    for path in (MASTER_PLAN, TRANSFORMATION_STATUS, DECISIONS, METRICS, RUNBOOK):
        assert path.is_file(), path

    project_status = _source()
    assert "This document is authoritative for maturity state." in project_status
    assert "`MASTER_PLAN.md` defines the dependency order" in project_status
    assert "`STATUS.md` records verified progress" in project_status
    assert "`METRICS.md` defines how target claims are measured" in project_status


def test_project_status_contains_every_dependency_ordered_transformation_phase() -> None:
    source = _source()

    expected = (
        "0. Truth, governance, and measurement",
        "1. Production stability",
        "2. Single-product consolidation",
        "3. Canonical evidence platform",
        "4. Comprehensive analysis and remediation intelligence",
        "5. Decision-grade delivery",
        "6. Lean company operations",
        "7. Controlled remediation",
        "8. Continuing assurance",
        "9. Security, recovery, and scale",
        "10. Maturity proof",
    )
    for heading in expected:
        assert heading in source

    assert "Completed major workstreams" not in source
    assert "three consecutive target-level runs" in source
    assert "A feature is not production-proven merely because code or unit tests exist." in source


def test_benchmark_contract_preserves_existing_golden_and_failure_fixtures() -> None:
    metrics = _source(METRICS)

    assert MANIFEST.is_file()
    assert DEMONSTRATION_WORKFLOW.is_file()
    assert "## Benchmark corpus contract" in metrics
    assert "clean repository" in metrics
    assert "required scanner failure" in metrics
    assert "conflicting scanner conclusions" in metrics
    assert "cross-tenant access attempts" in metrics
    assert "three consecutive complete runs" in metrics


def test_recovery_contract_references_real_restart_and_resilience_proofs() -> None:
    runbook = _source(RUNBOOK)

    assert POSTGRES_RESTART_WORKFLOW.is_file()
    assert RESILIENCE_WORKFLOW.is_file()
    assert "## Production backup, restore, and recovery" in runbook
    assert "Restore into an isolated non-production target." in runbook
    assert "Do not describe CI restart tests as a completed production restore drill." in runbook
    assert "## Workflow and queue recovery" in runbook


def test_cli_modularization_files_remain_present_without_becoming_a_second_product() -> None:
    source = _source()

    for path in (
        CLI_ENTRYPOINT,
        CLI_FACADE,
        LOCAL_RUNTIME_CONFIG,
        LOCAL_SCAN_SERVICE,
        LOCAL_STORE,
    ):
        assert path.is_file(), path

    assert "CLI and local service architecture | Stable" in source
    assert "compatibility facade must not duplicate implementations" in source
    assert "not a separate product" in source


def test_next_execution_order_contains_only_unfinished_transformation_work() -> None:
    source = _source()
    remaining = source.split("## Next execution order", 1)[1]

    assert "Merge and verify the single-product transformation baseline." in remaining
    assert "Consolidate runtime product identity" in remaining
    assert "Complete canonical evidence and finding schemas." in remaining
    assert "Implement Company Queue" in remaining
    assert "Implement controlled remediation and continuing assurance." in remaining
    assert "production recovery, tenancy, scale, external-pilot, and repeated benchmark proof" in remaining
    assert "unified Express, Mid, and Full" not in remaining
