from copy import deepcopy
from pathlib import Path
import subprocess

from nico.hosted_provider_comprehensive_runtime_v1 import (
    _github_access_diagnostics, _github_access_report_snapshot,
)
from nico.snapshot_repository_evidence import collect_snapshot_repository_evidence
from tests.test_snapshot_repository_evidence import FakeSnapshotClient, _context, _snapshot


def test_contents_only_private_fixture_preserves_optional_access_limits():
    context = _context()
    snapshot = _snapshot(context)
    snapshot.update(provider_access_observed=True, access_mode='authenticated_read_only', credential_used=True)
    client = FakeSnapshotClient(credential_used=True, pull_error='403: Resource not accessible')
    client.files = {'README.md': '# Synthetic private access fixture\n'}
    client.get_workflow_runs = lambda *args: ([], '403: Resource not accessible')
    bundle, _ = collect_snapshot_repository_evidence(context, snapshot, client=client)
    assert _github_access_report_snapshot(snapshot, bundle) is not None
    states = {item['capability']: item['state'] for item in bundle['provider_capability_states']}
    assert states['change_requests'] != 'supported'
    assert states['ci_runs'] != 'supported'
    before = deepcopy(bundle)
    bundle['required_source_evidence_complete'] = False
    assert _github_access_report_snapshot(snapshot, bundle) is None
    diagnostic = _github_access_diagnostics(snapshot, bundle)
    assert diagnostic['required_source_evidence_complete'] is False
    assert diagnostic['provider_access_observed'] is True
    assert diagnostic['provider_access_binding_consistent'] is True
    assert diagnostic['retained_source_locator_count'] == 1
    assert all(isinstance(value, (bool, int)) for value in diagnostic.values())
    bundle['required_source_evidence_complete'] = True
    assert bundle == before


def test_recovery_transport_executes_real_components():
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(['node', '--test', 'tests/js/comprehensive-recovery-session.test.cjs'],
                            cwd=root, capture_output=True, text=True, timeout=90)
    assert result.returncode == 0, result.stdout + result.stderr
