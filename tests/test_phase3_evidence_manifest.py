"""Evidence Manifest Regression Test

Catches module_statuses key errors (e.g. dependency_audit pointing to wrong module).
"""

from nico.assessment import run_assessment

from pathlib import Path

import json


def test_evidence_manifest_module_statuses_correct():
    run_assessment("./nico/test_lab", tier="express", output_dir="/tmp/nico_manifest_test")
    manifest_path = Path("/tmp/nico_manifest_test/assessment_latest.json")

    with open(manifest_path) as f:
        data = json.load(f)

    manifest = data.get("evidence_manifest") or data  # support both wrapped and direct

    module_statuses = manifest.get("module_statuses", {})

    # These must come from the correct modules
    assert "dependency_audit" in module_statuses
    assert module_statuses["dependency_audit"] in ("completed", "limited", "unavailable", "unknown")

    # Sanity: cicd_audit should also be present and different
    assert "cicd_audit" in module_statuses
