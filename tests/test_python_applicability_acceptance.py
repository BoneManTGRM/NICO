"""Missing Python inputs must not earn an unsupported clean coverage result."""
from copy import deepcopy

import pytest

from nico.complete_assessment_gate_v1 import require_complete_assessment, scanner_execution_summary
from nico.scanner_applicability_v1 import normalize_scanner_applicability_canonical
from tests.test_scanner_completion_gate import good, SHA, RUN


@pytest.mark.parametrize("python_path", [None, "src/application.py", "requirements-prod.txt", "setup.py"])
def test_missing_python_preparation_cannot_be_reclassified_as_inapplicable(python_path):
    # Production run65d had this reason and no retained inventory/observation.
    value = good()
    if python_path:
        value["file_evidence"] = {"sampled_paths": [python_path]}
    record = next(r for r in value["requested_scanner_records"] if r["scanner_name"] == "pip-audit")
    record.update(state="unavailable", status="unavailable", completed=False,
                  verified=False, verified_complete=False,
                  raw_artifact_retention_complete=False, raw_artifact_sha256="",
                  failure_reason="No supported Python dependency manifest was found.")
    normalized = normalize_scanner_applicability_canonical(value)
    result = next(r for r in normalized["requested_scanner_records"] if r["scanner_name"] == "pip-audit")
    assert result["state"] == "unavailable"
    assert result["applicable"] is True
    with pytest.raises(RuntimeError, match="pip-audit"):
        require_complete_assessment(normalized, expected_commit=SHA, expected_run=RUN)
    summary = scanner_execution_summary(normalized, expected_commit=SHA, expected_run=RUN)
    assert summary["completed_count"] == 8
    assert "pip-audit" in summary["incomplete_tools"]
    assert "pip-audit" not in summary["not_applicable_tools"]


def test_historical_python_inapplicability_without_observation_fails_actual_acceptance():
    value = good()
    record = next(r for r in value["requested_scanner_records"] if r["scanner_name"] == "pip-audit")
    record.update(state="not_applicable", status="not_applicable", applicable=False,
                  completed=False, verified=False, verified_complete=False,
                  raw_state="unavailable", raw_artifact_retention_complete=False,
                  raw_artifact_sha256="", applicability_reason="No supported Python dependency manifest or source tree exists at the assessed commit.")
    original = deepcopy(value)
    with pytest.raises(RuntimeError, match="pip-audit"):
        require_complete_assessment(value, expected_commit=SHA, expected_run=RUN)
    assert value == original
