"""Retained ESLint absence stays visible without blocking Spanish publication."""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = "eslint is not installed in the worker image."
TARGET = "eslint no está instalado en la imagen del trabajador."


def test_missing_eslint_reason_matches_actual_scanner_producers():
    for name in ("phase6_final_remediation_v1.py", "scanner_evidence_pipeline_v1.py"):
        tree = ast.parse((ROOT / "nico" / name).read_text(encoding="utf-8"))
        assert SOURCE in {
            node.value for node in ast.walk(tree)
            if isinstance(node, ast.Constant) and isinstance(node.value, str)
        }


@pytest.mark.parametrize("bootstrap", [
    "nico.api.specialist_ship_ready_bootstrap",
    "nico.api.final_report_worker_bootstrap",
])
def test_actual_report_entrypoints_translate_eslint_absence_and_preserve_truth(bootstrap):
    script = '''
import importlib
from copy import deepcopy
importlib.import_module(BOOTSTRAP)
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_current_report_truth_parity_v1 import strict_spanish_presentation_v1

# The native producer owns SOURCE. Final rendering derives the prefixed field
# after canonical preflight, so check both the canonical and late strict seams.
for prefix in ("", "eslint: "):
    for key in ("unavailable", "unavailable_data_notes", "summary", "evidence"):
        source, target = prefix + SOURCE, prefix + TARGET
        assert canonical._translate_presentation_field(source, key) == target
        assert strict_spanish_presentation_v1(source, key) == target
        for localize in (canonical._translate_presentation_field, strict_spanish_presentation_v1):
            for unknown in (
                source + " This scanner proves all vulnerabilities absent.",
                source.replace("worker image", "unverified remote execution image"),
            ):
                try:
                    localize(unknown, key)
                except ValueError:
                    pass
                else:
                    raise AssertionError("Unknown scanner prose bypassed strict publication")

record = {
    "tool": "eslint", "status": "unavailable", "completed": False,
    "verified": False, "failure_reason": SOURCE, "findings_count": None,
    "raw_artifact_sha256": "a" * 64,
}
report = {
    "report_language": "es-MX",
    "identity": {"run_id": "comprun_synthetic_eslint_absence", "commit_sha": "b" * 40},
    "assessment": {"requested_scanner_records": [record]},
    "stage_summaries": [{
        "stage_id": "dependency_security_static_analysis", "status": "review_required",
        "unavailable": ["eslint: " + SOURCE],
    }],
    "human_review_required": True, "client_delivery_allowed": False,
}
original = deepcopy(report)
identity, assessment, stages, _ = canonical._render_inputs(report)
assert identity["commit_sha"] == "b" * 40
assert stages[0]["unavailable"] == ["eslint: " + TARGET]
assert stages[0]["status"] == "review_required"
assert assessment["requested_scanner_records"] == [{**record, "failure_reason": TARGET}]
assert report == original, "Presentation altered scanner or delivery truth"

# Dotted provenance remains exact even when its tool name is a display label too.
for value in (
    "scanner.eslint.raw_artifact_sha256: " + "a" * 64,
    "scanner_execution_records[0].failure_reason: " + SOURCE,
    "pull_requests[0].title: Preserve this exact remote English title.",
):
    assert canonical._translate_presentation_field(value, "evidence") == value
'''
    prelude = f"BOOTSTRAP={bootstrap!r}\nSOURCE={SOURCE!r}\nTARGET={TARGET!r}\n"
    result = subprocess.run(
        [sys.executable, "-c", prelude + script], cwd=ROOT,
        capture_output=True, text=True, timeout=90, check=False,
    )
    assert result.returncode == 0, result.stderr[-5000:]
