"""Phase 2 Assessment Reporting Tests (Narrow Fix)

Tests local-path Express findings_count fix.
"""

import os
from pathlib import Path

from nico.assessment import run_assessment


def test_local_path_express_findings_count():
    # Ensure test lab exists
    test_lab = "./nico/test_lab"
    assert Path(test_lab).exists(), "nico/test_lab must exist"

    result = run_assessment(
        target=test_lab,
        tier="express",
        output_dir="/tmp/nico_local_test"
    )

    assert result["status"] == "completed", f"Expected completed, got {result.get('status')}"
    assert result.get("used_local_scan") is True
    assert result.get("findings_count", 0) > 0, "findings_count should be > 0 for test_lab"
    assert result.get("repairs_count", 0) >= 0


def test_missing_local_path():
    result = run_assessment(
        target="./does-not-exist-12345",
        tier="express",
        output_dir="/tmp/nico_local_test"
    )
    assert result["status"] != "completed"
    assert any("does not exist" in lim or "error" in lim.lower() for lim in result.get("limitations", []))
