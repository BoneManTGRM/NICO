"""Exercise legacy compatibility tests without leaking their process-wide bindings."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize("reverse", [False, True])
def test_legacy_report_tests_restore_bindings_in_both_orders(reverse):
    script = r'''
import sys
import pytest
from nico import v2_automated_draft_quality_compat_v1 as legacy
from nico import v2_localized_report_quality_repairs as localized
from nico import v2_report_quality_repairs as quality
from nico import v2_report_quality_runtime_compat as runtime
bindings = (
    (legacy, ("_contains_legacy_bare_draft", "_PDF_REPLACEMENTS", "_TEXT_REPLACEMENTS")),
    (quality, ("_FINAL_PDF_REPLACEMENTS", "_FINAL_TEXT_REPLACEMENTS", "_final_status_overlay", "_normalize_final_text", "_validate_final_pdf")),
    (localized, ("_replace_pdf_text", "_normalize_final_text", "_validate_final_pdf")),
    (runtime, ("_validate_final_pdf",)),
)
before = [(module, name, getattr(module, name)) for module, names in bindings for name in names]
# Exercise restoration of absence as well as existing object identity.
vars(legacy._validate_review_pdf).pop("_nico_previous", None)
attributes = dict(vars(legacy._validate_review_pdf))
nodes = [
    "tests/test_v2_report_quality_runtime_compat.py::test_repairs_canonical_scorecard_title",
    "tests/test_v2_report_quality_repairs.py::test_rendered_scorecard_wraps_rows_and_preserves_automated_draft_semantics",
    "tests/test_v2_automated_draft_quality_compat_v1.py::test_quality_gate_accepts_required_automated_draft_boundary",
    "tests/test_scorecard_extraction_validation_v1.py::test_final_installer_binds_both_english_runtime_validation_paths",
]
if sys.argv[1] == "reverse":
    nodes.reverse()
result = pytest.main(["-q", *nodes])
assert result == 0
for module, name, original in before:
    assert getattr(module, name) is original, (module.__name__, name)
assert vars(legacy._validate_review_pdf) == attributes
assert "_nico_previous" not in vars(legacy._validate_review_pdf)
'''
    completed = subprocess.run(
        [sys.executable, "-c", script, "reverse" if reverse else "forward"],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True, text=True, timeout=30,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
