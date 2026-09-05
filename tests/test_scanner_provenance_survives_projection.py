"""The report projection must retain the scanner producer's evidence identity."""
from copy import deepcopy
import hashlib

import pytest

from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS, complete_assessment_evidence
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
from nico.v2_assessment_pipeline import build_canonical_assessment
from nico.v2_scanner_reconciliation import normalize_record

SHA = 'b' * 40
RUN = 'comprun_projection_contract_fixture'
NO_SOURCES = ('No declared package source exists in the completely inspected snapshot; '
              'OSV dependency matching is not applicable to the supplied evidence. '
              'Undeclared dependencies were not assessed.')

def source_records():
    records = []
    for tool in REQUIRED_TOOLS:
        record = {
            'tool': tool, 'status': 'completed', 'commit_sha': SHA,
            'exact_commit_match': True, 'returncode': 0, 'returncode_valid': True,
            'completed': True, 'verified': True, 'verified_complete': True,
            'verified_for_this_report': True, 'current_run': True,
            'execution_observed_for_this_report': True,
            'raw_artifact_capture_complete': True, 'raw_artifact_retention_complete': True,
            'output_capture_complete': True, 'timed_out': False,
            'raw_artifact_sha256': hashlib.sha256((tool + '-native-output').encode()).hexdigest(),
            'artifact_hash': hashlib.sha256((tool + '-normalized-record').encode()).hexdigest(),
            'findings': [], 'applicable': True,
        }
        if tool == 'osv-scanner':
            record.update(status='not_applicable', applicable=False,
                completed=False, verified=False, verified_complete=False,
                verified_for_this_report=False, returncode=128, returncode_valid=False,
                applicability_reason=NO_SOURCES, reason=NO_SOURCES,
                applicability_evidence={
                    'schema': 'nico.osv-package-inventory.v1', 'inventory_complete': True,
                    'no_declared_package_sources': True, 'package_source_paths': [],
                    'inventory_sha256': 'c' * 64,
                }, native_json_output=False, no_vulnerabilities_claimed=False)
        records.append(record)
    return records


def test_compaction_keeps_raw_digest_distinct_from_record_hash():
    raw = source_records()
    before = deepcopy(raw)
    compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw}, commit_sha=SHA)
    by_name = {r['tool']: r for r in compact}
    for source in raw:
        assert by_name[source['tool']].get('raw_artifact_sha256') == source['raw_artifact_sha256']
        assert by_name[source['tool']]['artifact_hash'] != source['raw_artifact_sha256']
    assert raw == before


def test_normalization_preserves_observed_osv_non_applicability_without_scan_credit():
    raw = next(r for r in source_records() if r['tool'] == 'osv-scanner')
    normalized = normalize_record(raw, SHA)
    assert normalized['status'] == 'not_applicable'
    assert normalized['applicability_evidence'] == raw['applicability_evidence']
    assert normalized['exact_commit_match'] is True
    assert normalized['completed'] is False and normalized['verified_complete'] is False


def test_full_projection_passes_unchanged_gate_only_with_original_raw_evidence():
    raw = source_records()
    compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw}, commit_sha=SHA)
    report = {'identity':{'commit_sha':SHA,'run_id':RUN}, 'scanner_execution_records':compact}
    canonical = build_canonical_assessment(report)
    verdict = complete_assessment_evidence(canonical, expected_commit=SHA, expected_run=RUN)
    assert verdict['passed'], verdict['failures']
    assert verdict['not_applicable_tools'] == ['osv-scanner']
    assert len(verdict['completed_tools']) == 8
    assert verdict['client_delivery_allowed'] is False
    assert report['scanner_execution_records'] == compact


def test_missing_native_artifact_cannot_be_replaced_by_record_fingerprint():
    raw = source_records()
    del raw[0]['raw_artifact_sha256']
    compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw}, commit_sha=SHA)
    canonical = build_canonical_assessment({'identity':{'commit_sha':SHA,'run_id':RUN},'scanner_execution_records':compact})
    verdict = complete_assessment_evidence(canonical, expected_commit=SHA, expected_run=RUN)
    assert not verdict['passed']
    assert raw[0]['tool'] + ':raw_scanner_evidence_missing' in verdict['failures']

@pytest.mark.parametrize('defect', ['missing_inventory', 'wrong_commit', 'timed_out', 'capture_incomplete', 'not_retained'])
def test_provenance_preservation_does_not_authorize_bad_evidence(defect):
    raw = source_records()
    if defect == 'missing_inventory':
        next(r for r in raw if r['tool'] == 'osv-scanner').pop('applicability_evidence')
    elif defect == 'wrong_commit':
        raw[0]['commit_sha'] = 'd' * 40
    elif defect == 'timed_out':
        raw[0]['timed_out'] = True
    elif defect == 'capture_incomplete':
        raw[0]['output_capture_complete'] = False
    else:
        raw[0]['raw_artifact_retention_complete'] = False
    compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw}, commit_sha=SHA)
    canonical = build_canonical_assessment({'identity':{'commit_sha':SHA,'run_id':RUN},'scanner_execution_records':compact})
    assert not complete_assessment_evidence(canonical, expected_commit=SHA, expected_run=RUN)['passed']


def test_requested_population_retains_inapplicable_source_identity():
    from nico.comprehensive_authoritative_scanner_truth_v62 import reconcile_authoritative_scanner_truth
    from nico.comprehensive_requested_scanner_projection_v62 import requested_scanner_population
    raw = source_records()
    absent = {
        'pip-audit': 'No supported Python dependency files were found.',
        'npm-audit': 'No package-lock.json with an adjacent package.json was found.',
        'typescript': 'Project dependencies were not prepared.',
    }
    for record in raw:
        if record['tool'] in absent:
            record.update(status='unavailable', completed=False, verified=False,
                verified_complete=False, verified_for_this_report=False,
                reason=absent[record['tool']], returncode=None)
            record.pop('applicable')
    compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw}, commit_sha=SHA)
    canonical = build_canonical_assessment({
        'identity':{'commit_sha':SHA,'run_id':RUN},
        'repository_evidence': {'file_evidence':{'sampled_paths':['README.md','sample.rb']}},
        'live_scanner_evidence': {'tools_requested':list(REQUIRED_TOOLS)},
        'scanner_execution_records': compact,
    })
    canonical = reconcile_authoritative_scanner_truth(canonical)
    records, _, _, _ = requested_scanner_population(canonical)
    by_name = {r['scanner_name']:r for r in records}
    for name in ('npm-audit','typescript','osv-scanner'):
        assert by_name[name]['status'] == 'not_applicable', by_name[name]
        assert by_name[name]['commit_sha'] == SHA
        assert by_name[name]['exact_commit_match'] is True
        assert by_name[name]['completed'] is False

@pytest.mark.parametrize('bootstrap', ['nico.api.specialist_ship_ready_bootstrap', 'nico.api.final_report_worker_bootstrap'])
@pytest.mark.parametrize('locale', ['en', 'es-MX'])
def test_actual_renderer_entrypoints_preserve_complete_assessment_contract(bootstrap, locale):
    import subprocess
    import sys
    from pathlib import Path
    source = r'''
import importlib, runpy
importlib.import_module(BOOTSTRAP)
test = runpy.run_path(TEST_FILE)
from nico import v2_pipeline_adapter as adapter
from nico.complete_assessment_gate_v1 import complete_assessment_evidence
from nico.comprehensive_retained_scanner_evidence_v1 import compact_scanner_records
raw = test['source_records']()
sha, run = test['SHA'], test['RUN']
compact = compact_scanner_records({'scan_id':'scan_projection_fixture','scanner_results':raw},commit_sha=sha)
result = adapter.apply_v2_pipeline({'status':'complete','report_package':{'json':{
 'identity':{'repository':'example/projection-fixture','commit_sha':sha,'run_id':run,
 'evidence_ledger_id':'ledger_projection_fixture','customer_id':'fixture','project_id':'fixture',
 'report_language':LOCALE,'generated_at':'2026-09-05T00:00:00Z'},
 'generated_at':'2026-09-05T00:00:00Z',
 'assessment':{'technical_score':80,'canonical_evidence_adjusted_score':80,'sections':[]},
 'scanner_execution_records':compact,
}}})
canonical = result['report_package']['json']
verdict = complete_assessment_evidence(canonical,expected_commit=sha,expected_run=run)
assert verdict['passed'],verdict['failures']
assert result['client_delivery_allowed'] is False
assert result['report_package']['pdf_base64']
'''
    root = Path(__file__).resolve().parents[1]
    prelude = f'BOOTSTRAP={bootstrap!r}\nLOCALE={locale!r}\nTEST_FILE={str(Path(__file__).resolve())!r}\n'
    result = subprocess.run([sys.executable,'-c',prelude + source],cwd=root,capture_output=True,text=True,timeout=45)
    assert result.returncode == 0, result.stderr[-6000:]
