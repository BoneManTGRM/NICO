"""Exercise renderer-owned OSV prose through both actual process entry points."""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
NO_SOURCES = (
    "No declared package source exists in the completely inspected snapshot; "
    "OSV dependency matching is not applicable to the supplied evidence. "
    "Undeclared dependencies were not assessed."
)
NO_SOURCES_ES = (
    "No existe ninguna fuente de paquetes declarada en la instantánea inspeccionada "
    "por completo; la comparación de dependencias de OSV no es aplicable a la "
    "evidencia proporcionada. Las dependencias no declaradas no se evaluaron."
)
UNVERIFIED = (
    "OSV reported no package sources (exit 128), but dependency declarations "
    "exist or the snapshot inventory is incomplete; dependency coverage remains unverified."
)
UNVERIFIED_ES = (
    "OSV informó que no hay fuentes de paquetes (código de salida 128), pero existen "
    "declaraciones de dependencias o el inventario de la instantánea está incompleto; "
    "la cobertura de dependencias sigue sin verificarse."
)


def test_tested_literals_are_the_actual_scanner_producer_contracts():
    tree = ast.parse((ROOT / 'nico/scanner_evidence_pipeline_v1.py').read_text())
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    assert {NO_SOURCES, UNVERIFIED} <= literals


@pytest.mark.parametrize('bootstrap', [
    'nico.api.specialist_ship_ready_bootstrap',
    'nico.api.final_report_worker_bootstrap',
])
@pytest.mark.parametrize('source,target', [(NO_SOURCES, NO_SOURCES_ES), (UNVERIFIED, UNVERIFIED_ES)])
def test_real_bootstrap_localizes_late_scanner_reason_without_changing_truth(bootstrap, source, target):
    script = '''
import importlib, json
from copy import deepcopy
importlib.import_module(BOOTSTRAP)
from nico import comprehensive_spanish_canonical_report_v87 as canonical
from nico.comprehensive_spanish_publication_preflight_v93 import inspect_spanish_canonical_publication_preflight

# The availability line is derived after the earlier canonical preflight. Test
# that late presentation projection, not just a directly called translation helper.
for prefix in ('', 'osv-scanner: '):
    for key in ('unavailable', 'summary', 'evidence'):
        assert canonical._translate_presentation_field(prefix + SOURCE, key) == prefix + TARGET

machine_record = {
    'tool': 'osv-scanner', 'status': 'not_applicable', 'applicable': False,
    'completed': False, 'verified': False, 'no_vulnerabilities_claimed': False,
    'native_json_output': False, 'applicability_reason': SOURCE,
    'raw_artifact_sha256': 'a' * 64,
}
report = {
    'report_language': 'es-MX', 'identity': {'run_id': 'comprun_synthetic_locale', 'commit_sha': 'b' * 40},
    'assessment': {'requested_scanner_records': [machine_record]},
    'stage_summaries': [{'stage_id': 'dependency_security_static_analysis',
                         'status': 'complete', 'unavailable': ['osv-scanner: ' + SOURCE]}],
    'human_review_required': True, 'client_delivery_allowed': False,
}
original = deepcopy(report)
preflight = inspect_spanish_canonical_publication_preflight(report)
assert preflight['status'] == 'complete' and preflight['failure_count'] == 0
identity, _, stages, _ = canonical._render_inputs(report)
assert stages[0]['unavailable'] == ['osv-scanner: ' + TARGET]
assert identity['commit_sha'] == 'b' * 40
assert report == original, 'Spanish rendering changed canonical scanner truth'
assert report['assessment']['requested_scanner_records'][0]['completed'] is False
assert report['human_review_required'] is True and report['client_delivery_allowed'] is False

# Known OSV copy must not turn unrelated/unknown English into publishable output.
try:
    canonical._translate_presentation_field(SOURCE + ' The scanner silently proves all vulnerabilities absent.', 'unavailable')
except ValueError:
    pass
else:
    raise AssertionError('Unknown English suffix bypassed strict publication')
'''
    prelude = f'BOOTSTRAP={bootstrap!r}\nSOURCE={source!r}\nTARGET={target!r}\n'
    result = subprocess.run([sys.executable, '-c', prelude + script], cwd=ROOT,
                            capture_output=True, text=True, timeout=90, check=False)
    assert result.returncode == 0, result.stderr[-5000:]
