"""Bounded durable fixtures measure reads, not machine-dependent elapsed time."""
import copy
import gzip
import hashlib
import json

import pytest
from test_retained_ci_report_consumers import (
    api, retained, project, display_value, persisted_case, verified_checkout,
)
from test_retained_typescript_status_coverage_v1 import evaluate
from nico import comprehensive_scanner_inventory_v1 as inventory
from nico import scanner_raw_artifact_storage_v1 as storage
from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.report_execution_provenance_e6 import scanner_execution_evidence

REAL_RAW_METADATA = inventory._raw_metadata


def durable_population(case, monkeypatch):
    canonical, _ = evaluate(case, monkeypatch)
    scan = inventory.get_scan(case.binding['scan_id'])
    for row in scan['scanner_results']:
        if row['scanner_name'] == 'typescript':
            continue
        binding = {**case.binding, 'scanner_name': row['scanner_name']}
        raw = (row['scanner_name'] + ':owned-bounded-fixture\n').encode() * 1024
        compressed = gzip.compress(raw, mtime=0)
        digest = hashlib.sha256(raw).hexdigest()
        artifact_id = case.store.put(binding, compressed, digest)
        row.update(raw_artifact_sha256=digest, raw_artifact={
            'storage_backend': 'postgres', 'artifact_id': artifact_id,
            'sha256': digest, 'gzip_sha256': hashlib.sha256(compressed).hexdigest(),
            'retained_bytes': len(raw), 'gzip_bytes': len(compressed), 'redacted': True,
        })
    monkeypatch.setattr(inventory, '_raw_metadata', REAL_RAW_METADATA)
    reads = []
    original = storage.ScannerArtifactStore.get
    def counted(self, artifact_id, **kwargs):
        reads.append(artifact_id)
        return original(self, artifact_id, **kwargs)
    monkeypatch.setattr(storage.ScannerArtifactStore, 'get', counted)
    return canonical, scan, reads


@pytest.mark.parametrize('outcome', ['clean', 'errors'])
@pytest.mark.parametrize('passes', [2, 3])
def test_truth_reconciliation_reads_only_selected_durable_artifact(persisted_case, monkeypatch, passes):
    canonical, scan, reads = durable_population(persisted_case, monkeypatch)
    package = {'json': canonical}
    for _ in range(passes):
        package = reconcile_production_report_truth(package)
    row = next(r for r in package['json']['scanner_execution_records'] if r['scanner_name'] == 'typescript')
    assert row['retained_ci_evidence_verified'] is True
    assert row['verified_complete'] is False
    assert reads == [persisted_case.record['raw_artifact']['artifact_id']] * passes
    # The owner inventory and provenance still inspect every scanner.
    reads.clear()
    full = scanner_execution_evidence(canonical['identity'], {
        'dependency_security_static_analysis': {'scan_id': scan['scan_id']},
    })
    assert len(reads) == len(scan['scanner_results']) == 9
    assert len(full['scanner_records']) == 9
    assert 'selected_scanner' not in full


@pytest.mark.parametrize('outcome', ['clean'])
@pytest.mark.parametrize('damage', ['duplicate_other', 'unknown_record', 'unknown_requested', 'missing_typescript', 'wrong_run', 'wrong_sha', 'tampered_after_success'])
def test_selection_preserves_population_identity_and_fresh_byte_checks(persisted_case, monkeypatch, damage):
    canonical, scan, reads = durable_population(persisted_case, monkeypatch)
    assert reconcile_production_report_truth({'json': canonical})['json']['scanner_execution_records']
    if damage == 'duplicate_other': scan['scanner_results'].append(copy.deepcopy(scan['scanner_results'][0]))
    elif damage == 'unknown_record': scan['scanner_results'].append({'scanner_name': 'unknown'})
    elif damage == 'unknown_requested': scan['tools_requested'].append('unknown')
    elif damage == 'missing_typescript': scan['scanner_results'] = [r for r in scan['scanner_results'] if r['scanner_name'] != 'typescript']
    elif damage == 'wrong_run': scan['run_id'] = 'comprun_other'
    elif damage == 'wrong_sha': scan['actual_commit_sha'] = 'c' * 40
    elif damage == 'tampered_after_success':
        with persisted_case.store.connect() as connection:
            connection.execute('UPDATE scanner_raw_artifacts SET gzip_blob=? WHERE artifact_id=?',
                               (b'changed', persisted_case.record['raw_artifact']['artifact_id']))
            connection.commit()
    report = reconcile_production_report_truth({'json': canonical})['json']
    row = next(r for r in report['scanner_execution_records'] if r['scanner_name'] == 'typescript')
    assert row.get('retained_ci_evidence_verified') is not True


@pytest.mark.parametrize('outcome', ['clean'])
def test_selected_inventory_does_not_claim_full_verification(persisted_case, monkeypatch):
    canonical, scan, _ = durable_population(persisted_case, monkeypatch)
    stages = {'dependency_security_static_analysis': {'scan_id': scan['scan_id']}}
    selected = scanner_execution_evidence(canonical['identity'], stages, scanner_name='typescript')
    assert selected['selected_scanner'] == 'typescript'
    assert selected['verification_status'] == 'selected_scanner_verified'
    assert selected['inventory_status'] == 'selected_scanner_complete'
    assert selected['scanner_record_count'] == 9
    assert len(selected['scanner_records']) == 1
    denied = inventory.inventory_for_record({'identity': canonical['identity'], 'stage_results': stages},
                                           run_id=canonical['identity']['run_id'], scanner_name='unknown')
    assert denied.status_code == 409
