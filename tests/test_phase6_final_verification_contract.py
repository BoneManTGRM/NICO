from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _load_builder():
    path = ROOT / "scripts" / "build_phase6_verification_package.py"
    spec = importlib.util.spec_from_file_location("phase6_verification_builder", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_verification_builder_uses_innermost_repository_root() -> None:
    module = _load_builder()
    assert module._repository_path("/home/runner/work/NICO/NICO/nico/comprehensive_run_store.py") == "nico/comprehensive_run_store.py"
    assert module._repository_path("C:/work/NICO/apps/web/app/page.tsx") == "apps/web/app/page.tsx"


def test_scanner_authority_order_matches_phase6_contract() -> None:
    source = (ROOT / "nico" / "phase6_final_remediation_v1.py").read_text(encoding="utf-8")
    block = source.split("items.sort(", 1)[1].split("reverse=True", 1)[0]
    tokens = [
        "exact_commit_match",
        "raw_artifact_retention_complete",
        "verified_artifact_hash",
        "execution_complete",
        "observed_at",
    ]
    positions = [block.index(token) for token in tokens]
    assert positions == sorted(positions)
    assert "current_run" not in block


def test_frozen_sha_proof_runs_for_final_phase6_branch_commits() -> None:
    source = (ROOT / ".github" / "workflows" / "frozen-sha-scanner-proof.yml").read_text(encoding="utf-8")

    assert "push:" in source
    assert "phase-6/report-deduplication-security-remediation" in source
    assert "github.event_name == 'push' && github.sha" in source
    assert "Two clean scanner runs and final report proof on exact SHA" in source
    assert "phase6-final-comprehensive-${{ env.TARGET_SHA }}" in source


def test_final_verification_blocks_internal_phase_and_tier_comparisons() -> None:
    source = (ROOT / "scripts" / "build_phase6_verification_package.py").read_text(encoding="utf-8")

    for forbidden in (
        "Verified Change Since Phase 5 Baseline",
        "Phase 5 Verified Before/After Delta",
        "Why this is broader than Express",
    ):
        assert forbidden in source
    assert "forbidden_customer_sections" in source
    assert "phase5_package_exports_remain" in source
    assert "express_comparison_section_present" in source


def test_final_verification_requires_exact_scanner_ci_format_and_language_truth() -> None:
    workflow = (ROOT / ".github" / "workflows" / "frozen-sha-scanner-proof.yml").read_text(encoding="utf-8")

    required_assertions = (
        'summary["two_consecutive_scanner_runs"] is True',
        'summary["report_incomplete_scanners"] == []',
        'summary["finding_ids_unique"] is True',
        'summary["canonical_locations_present"] is True',
        'summary["duplicate_mapping_records"] == []',
        'summary["assessed_commit_ci"]["green"] is True',
        'summary["cross_format_truth_status"] == "valid"',
        'summary["english_spanish_factual_parity"]["equivalent"] is True',
        'summary["english_filename_token_counts"]["FINAL-PENDING-APPROVAL"] == 1',
    )
    for assertion in required_assertions:
        assert assertion in workflow
