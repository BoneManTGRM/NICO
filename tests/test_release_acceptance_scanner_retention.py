"""Exercise the actual Spanish and unified release entrypoints with isolated copies."""
from copy import deepcopy
import importlib
import json
import hashlib
from pathlib import Path
import sys

import pytest

from nico.complete_assessment_gate_v1 import REQUIRED_TOOLS
from scripts.comprehensive_production_run_handoff_v1 import canonical_json_sha256

SHA = 'a' * 40
RUN = 'comprun_retention_acceptance'
SCAN = 'scan_snapshot_acceptance'


def evidence():
    canonical = {'identity': {'run_id': RUN, 'commit_sha': SHA}, 'requested_scanner_records': []}
    receipt = {'schema': 'nico.scanner-retention-verification.v1', 'run_id': RUN,
               'commit_sha': SHA, 'scan_id': SCAN, 'run_revision': 7,
               'read_only': True, 'failures': [], 'scanner_records': []}
    for name in REQUIRED_TOOLS:
        canonical['requested_scanner_records'].append({
            'scanner_name': name, 'state': 'completed', 'completed': True, 'verified': True,
            'commit_sha': SHA, 'snapshot_commit_sha': SHA, 'run_id': RUN, 'scan_id': SCAN,
            'evidence_reference': 'scanner_runs/' + SCAN, 'exact_commit_match': True,
            'raw_artifact_retention_complete': True, 'raw_artifact_sha256': 'b' * 64})
        receipt['scanner_records'].append({
            'scanner_name': name, 'execution_status': 'completed', 'source_identity_verified': True,
            'commit_sha': SHA, 'output_capture_complete': True,
            'execution_observed': True, 'raw_artifact': {'availability': 'verified', 'sha256': 'b' * 64}})
    return canonical, {'run_id': RUN, 'commit_sha': SHA, 'revision': 7,
                       'scanner_evidence_verification': receipt}


class Response:
    def __init__(self, value):
        self.content = json.dumps(value).encode()
        self.headers = {'x-nico-canonical-truth-sha256': canonical_json_sha256(value)}
        self.status = self.status_code = 200
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def read(self): return self.content
    def json(self): return json.loads(self.content)


@pytest.mark.parametrize('entrypoint', ['spanish', 'unified'])
@pytest.mark.parametrize('control', [None, 'missing_receipt', 'missing_scanner', 'failed_scanner',
    'corrupt_bytes', 'wrong_hash', 'secondary_hash', 'wrong_run', 'wrong_scan',
    'wrong_reference', 'secondary_source', 'stale_receipt', 'prepared_input_changed',
    'unsupported_inapplicability', 'excluded', 'unexecuted', 'timed_out',
    'standalone_good', 'standalone_missing_observation', 'standalone_wrong_inventory'])
def test_actual_release_entrypoints_require_native_retention(monkeypatch, tmp_path, entrypoint, control):
    monkeypatch.syspath_prepend(str(Path('scripts').resolve()))
    canonical, status = evidence()
    original = deepcopy(canonical)
    records = canonical['requested_scanner_records']
    receipt = status['scanner_evidence_verification']
    if str(control).startswith('standalone_'):
        from nico.node_scanner_applicability_v1 import inspect_node_inputs, observation_bytes, SOURCE_REASONS
        from nico.scanner_package_inventory_v1 import inspect_package_sources
        (tmp_path / 'standalone.js').write_text('console.log(1)')
        for record in records:
            name = record['scanner_name']
            if name not in {'pip-audit', 'npm-audit', 'typescript', 'osv-scanner'}:
                continue
            inventory = inspect_package_sources(tmp_path, SHA) if name == 'osv-scanner' else inspect_node_inputs(tmp_path, SHA)
            raw = json.dumps({'inventory': inventory}).encode() if name == 'osv-scanner' else observation_bytes(inventory, name)
            digest = hashlib.sha256(raw).hexdigest()
            record.update(state='not_applicable', completed=False, verified=False, applicable=False,
                          applicability_reason=SOURCE_REASONS.get(name, 'Observed no package sources'),
                          applicability_evidence=inventory, raw_artifact_sha256=digest)
            observed = next(row for row in receipt['scanner_records'] if row['scanner_name'] == name)
            observed.update(execution_status='not_applicable', applicable=False,
                            applicability_inventory_sha256=inventory['inventory_sha256'],
                            applicability_observation_verified=True,
                            raw_artifact={'availability': 'verified', 'sha256': digest})
            if control == 'standalone_missing_observation': observed['applicability_observation_verified'] = False
            if control == 'standalone_wrong_inventory': inventory['inventory_sha256'] = 'c' * 64
    if control == 'missing_receipt': status.pop('scanner_evidence_verification')
    elif control == 'missing_scanner': receipt['scanner_records'].pop()
    elif control == 'failed_scanner': receipt['scanner_records'][0]['execution_status'] = 'failed'
    elif control == 'corrupt_bytes': receipt['scanner_records'][0]['raw_artifact']['availability'] = 'checksum_mismatch'
    elif control == 'wrong_hash': records[0]['raw_artifact_sha256'] = 'c' * 64
    elif control == 'secondary_hash': records[0]['raw_artifact'] = {'sha256': 'c' * 64}
    elif control == 'wrong_run': receipt['run_id'] = 'comprun_other'
    elif control == 'wrong_scan': records[0]['scan_id'] = 'scan_snapshot_other'
    elif control == 'wrong_reference': records[0]['evidence_reference'] = 'scanner_runs/scan_snapshot_other'
    elif control == 'secondary_source': records[0]['snapshot_commit_sha'] = 'c' * 40
    elif control == 'stale_receipt': receipt['run_revision'] = 6
    elif control == 'prepared_input_changed': receipt['scanner_records'][0]['source_checkout_verified'] = False
    elif control == 'unsupported_inapplicability':
        records[4].update(state='not_applicable', applicable=False, completed=False, verified=False, applicability_reason='not applicable')
    elif control == 'excluded': records[0].update(state='excluded', applicable=False)
    elif control == 'unexecuted': receipt['scanner_records'][0]['execution_observed'] = False
    elif control == 'timed_out': receipt['scanner_records'][0]['timed_out'] = True
    frozen = deepcopy(canonical)
    requests = []
    def fetch(request, **kwargs):
        url = request if isinstance(request, str) else request.full_url
        requests.append(url)
        return Response(canonical if url.endswith('/report/json') else status)
    if entrypoint == 'unified':
        module = importlib.import_module('completed_run_two_pass_acceptance_v1')
        action = lambda: module._read_final_canonical('https://app.nicoaudit.com', RUN, open_request=fetch, retention_output=tmp_path / 'retention-receipt.json')
    else:
        module = importlib.import_module('spanish_comprehensive_authenticated_live_acceptance_v1')
        monkeypatch.setattr(module, 'acquire_production_proof_session', lambda *a: ('synthetic-test-session', {}))
        monkeypatch.setattr(module, 'install_authenticated_httpx_client', lambda *a: None)
        monkeypatch.setattr(module.proof, 'install_spanish_terminal_boundary', lambda: None)
        monkeypatch.setattr(module.proof, '_fetch_canonical_json', lambda **kwargs: (canonical, '', ''))
        class Client:
            def __init__(self, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            get = staticmethod(fetch)
        monkeypatch.setattr(module.proof.httpx, 'Client', Client)
        monkeypatch.setattr(module.proof.telemetry, 'main', lambda argv: module.proof._fetch_canonical_json(frontend_origin='https://app.nicoaudit.com', run_id=RUN))
        action = lambda: module.main(['--frontend-url', 'https://app.nicoaudit.com'])
    if control not in {None, 'standalone_good'}:
        with pytest.raises(RuntimeError, match='evidence blocked') as caught:
            action()
        assert caught.value.evidence['passed'] is False
        if entrypoint == 'unified':
            assert json.loads((tmp_path / 'retention-receipt.json').read_text())['passed'] is False
    else:
        action()
        assert any(url.endswith('/' + RUN) for url in requests)
    assert canonical == frozen
    assert original['requested_scanner_records'][0]['state'] == 'completed'
