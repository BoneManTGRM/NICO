from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "unified_production_acceptance.py"
WORKFLOW = ROOT / ".github" / "workflows" / "two-service-production-acceptance.yml"


def _module():
    spec = importlib.util.spec_from_file_location("unified_production_acceptance_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPT.parent))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module


def test_report_identity_accepts_legacy_and_polished_titles() -> None:
    module = _module()

    assert module.has_comprehensive_report_identity(
        "NICO Comprehensive Technical Assessment"
    )
    assert module.has_comprehensive_report_identity(
        "NICO COMPREHENSIVE\nDecision-Grade Technical Assessment"
    )


def test_report_identity_requires_complete_semantic_identity() -> None:
    module = _module()

    assert not module.has_comprehensive_report_identity("NICO Comprehensive")
    assert not module.has_comprehensive_report_identity("Decision-Grade Technical Assessment")
    assert not module.has_comprehensive_report_identity("NICO Express Technical Assessment")


def test_workflow_uses_semantic_identity_runner_and_requires_proof() -> None:
    source = WORKFLOW.read_text(encoding="utf-8")

    assert "scripts/unified_production_acceptance.py" in source
    assert "python scripts/unified_production_acceptance.py" in source
    assert 'canonical_report_identity_verified' in source
    assert "--passes 2" in source
    assert "Wait for exact frontend and backend deployments" in source


def test_runner_patches_validation_before_unified_execution() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    assert "acceptance.validate_report = validate_report" in source
    assert "return unified.main(argv)" in source
    assert '"human_review_required": True' not in source
    assert '"client_delivery_allowed": True' not in source
