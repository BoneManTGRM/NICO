import json

import pytest

import nico.cli as cli
import nico.no_server_assessment as ns
from nico.local_store import LocalStore


@pytest.fixture
def state(tmp_path, monkeypatch):
    store = LocalStore(tmp_path / 'state.sqlite3')
    monkeypatch.setattr(ns, 'Store', lambda: store)
    monkeypatch.setattr(cli, 'Store', lambda: store)
    monkeypatch.setattr(ns, 'REPORT_DIR', tmp_path / 'reports')
    return store


def scan(store, name, date, raw=False):
    findings = [{'id': 'finding_' + name, 'severity':'high', 'category':'synthetic', 'masked_evidence': 'FAKE_TEST_ONLY_SECRET_123456' if raw else 'masked'}] if raw else []
    result = {'id':name, 'created_at':date, 'findings':findings, 'files_scanned':[]}
    store.save_scan(result, 'synthetic')
    return result


def publish(result):
    return ns.build_report('local', 'synthetic', None, {'scan': result, 'repairs': []}, None, 'Synthetic authorized fixture')


def test_old_findings_and_repairs_do_not_contaminate_current_assessment(state):
    scan(state, 'old', '2026-01-01', raw=True)
    state.save_repairs([{'id':'repair_old','finding_id':'finding_old'}])
    current = scan(state, 'new', '2026-01-02')
    publish(current)
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verified'
    assert result['nico_verification']['finding_count'] == 0
    assert result['nico_verification']['repair_count'] == 0


def test_no_server_persists_final_failure_without_successful_nested_record(state):
    publish(scan(state, 'new', '2026-01-02'))
    (ns.REPORT_DIR / 'no_server_latest.html').write_bytes(b'corrupt')
    before = state.payloads('verification')
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verification_failed'
    assert result['nico_verification']['passed'] is True
    assert state.payloads('verification') == before
    audit = [json.loads(row['detail']) for row in state.rows('audit_log') if row['action'] == 'assessment.no_server.verification']
    assert audit[0] == ns.sanitize_output(result)


def test_current_findings_fail_closed_and_only_linked_repairs_count(state):
    scan(state, 'old', '2026-01-01', raw=True)
    state.save_repairs([{'id':'repair_old', 'finding_id':'finding_old'}])
    current = scan(state, 'new', '2026-01-02', raw=True)
    state.save_repairs([{'id':'repair_new', 'finding_id':'finding_new'}])
    publish(current)
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verification_failed'
    assert result['nico_verification']['finding_count'] == 1
    assert result['nico_verification']['repair_count'] == 1
    assert 'masking_failure' in result['nico_verification']['checks']


@pytest.mark.parametrize('findings', [None, {}, [None], [{'id':''}], [{'id':'duplicate'}, {'id':'duplicate'}]])
def test_invalid_scan_snapshot_cannot_verify(state, findings):
    current = scan(state, 'new', '2026-01-02')
    publish(current)
    malformed = {**current, 'findings': findings}
    with state.db() as db:
        db.execute('UPDATE scans SET payload=? WHERE id=?', (json.dumps(malformed), current['id']))
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verification_failed'
    assert 'scan_findings_invalid' in result['nico_verification']['checks']


def test_shared_default_preserves_legacy_scope_and_persistence(state):
    from nico.local_verification_service import verify_latest

    scan(state, 'old', '2026-01-01', raw=True)
    scan(state, 'new', '2026-01-02')
    result = verify_latest(store=state)
    assert result['passed'] is False
    assert result['finding_count'] == 1
    assert state.latest_verification() == result
    assert any(row['action'] == 'verification.latest' for row in state.rows('audit_log'))


def test_final_success_is_audited_without_mutating_shared_history(state):
    publish(scan(state, 'new', '2026-01-02'))
    before_memory = state.payloads('memory')
    result = ns.verify_latest_assessment()
    assert result['status'] == 'verified'
    assert state.payloads('verification') == []
    assert state.payloads('memory') == before_memory
    rows = [json.loads(row['detail']) for row in state.rows('audit_log') if row['action']=='assessment.no_server.verification']
    assert rows == [ns.sanitize_output(result)]


def test_audit_failure_cannot_print_success(state, monkeypatch, capsys):
    publish(scan(state, 'new', '2026-01-02'))
    def fail(*args):
        raise OSError('synthetic audit failure')
    monkeypatch.setattr(state, 'audit', fail)
    with pytest.raises(SystemExit) as caught:
        ns.main(['verify','latest'])
    assert caught.value.code == 1
    assert json.loads(capsys.readouterr().out)['status'] == 'error'
    assert state.payloads('verification') == []
