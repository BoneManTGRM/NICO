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
    current = {'id':'scan_A','created_at':'2026-01-01','findings':[], 'files_scanned':[]}
    store.save_scan(current, 'synthetic')
    ns.build_report('local','synthetic',None,{'scan':current,'repairs':[]},None,'Synthetic authorization')
    return store


@pytest.mark.parametrize('row_id,payload_id', [('scan_B','scan_A'), (None,'scan_A'), ('','scan_A'), ('scan_A',None), ('scan_A',''), ('scan_A','MISSING')])
def test_no_server_rejects_row_payload_identity_disagreement(state, row_id, payload_id):
    with state.db() as db:
        payload=json.loads(db.execute('SELECT payload FROM scans').fetchone()[0])
        if payload_id=='MISSING':
            payload.pop('id')
        else:
            payload['id']=payload_id
        payload['_row_identity_valid']=True
        db.execute('UPDATE scans SET id=?,payload=?',(row_id,json.dumps(payload)))
    result=ns.verify_latest_assessment()
    assert result['status']=='verification_failed'
    assert result['nico_verification']['scan_id']==row_id
    assert result['nico_verification']['passed'] is False
    assert 'scan_row_identity_mismatch' in result['nico_verification']['checks']


def test_canonical_identity_success_and_shared_default_compatibility(state):
    assert ns.verify_latest_assessment()['status']=='verified'
    with state.db() as db:
        db.execute("UPDATE scans SET id='scan_B'")
    # Shared default preserves the historical payload-overrides-row behavior.
    assert state.latest_scan()['id']=='scan_A'
    assert cli.verify_latest()['scan_id']=='scan_A'
    assert ns.verify_latest_assessment()['status']=='verification_failed'


def test_new_scan_after_selection_is_point_in_time_not_false_identity(state, monkeypatch):
    original=state.latest_scan
    observed=[]
    def advance(**kwargs):
        selected=original(**kwargs)
        if not observed:
            state.save_scan({'id':'scan_B','created_at':'2026-01-02','findings':[]},'synthetic')
            observed.append(selected['id'])
        return selected
    monkeypatch.setattr(state,'latest_scan',advance)
    first=ns.verify_latest_assessment()
    second=ns.verify_latest_assessment()
    print(json.dumps({'scenario':'scan advances after read','selected':observed,'first':first,'second':second},sort_keys=True))
    assert first['status']=='verified' and first['nico_verification']['scan_id']=='scan_A'
    assert second['status']=='verification_failed' and second['nico_verification']['scan_id']=='scan_B'


def test_selected_payload_changed_after_read_is_observed_next_time(state, monkeypatch):
    original=state.latest_scan
    changed=[]
    def mutate(**kwargs):
        selected=original(**kwargs)
        if not changed:
            altered={**selected, 'findings':[{'id':'finding_new','masked_evidence':'FAKE_TEST_ONLY_SECRET_123456'}]}
            with state.db() as db:
                db.execute('UPDATE scans SET payload=? WHERE id=?',(json.dumps(altered),'scan_A'))
            changed.append(True)
        return selected
    monkeypatch.setattr(state,'latest_scan',mutate)
    first=ns.verify_latest_assessment(); second=ns.verify_latest_assessment()
    print(json.dumps({'scenario':'payload changes after read','first':first,'second':second},sort_keys=True))
    assert first['status']=='verified'
    assert second['status']=='verification_failed'
    assert 'masking_failure' in second['nico_verification']['checks']


def test_repair_added_between_reads_changes_metadata_not_pass_criterion(state, monkeypatch):
    with state.db() as db:
        payload=json.loads(db.execute('SELECT payload FROM scans').fetchone()[0])
        payload['findings']=[{'id':'finding_A','masked_evidence':'masked'}]
        db.execute('UPDATE scans SET payload=?',(json.dumps(payload),))
    # Publish the same pre-race snapshot; only repair metadata changes during verification.
    ns.build_report('local','synthetic',None,{'scan':payload,'repairs':[]},None,'Synthetic authorization')
    original=state.payloads
    def add_repair(table):
        if table=='repairs':
            state.save_repairs([{'id':'repair_A','finding_id':'finding_A'}])
        return original(table)
    monkeypatch.setattr(state,'payloads',add_repair)
    result=ns.verify_latest_assessment()
    print(json.dumps({'scenario':'repair mutation between scan and repair reads','result':result},sort_keys=True))
    assert result['status']=='verified'
    assert result['nico_verification']['repair_count']==1


@pytest.mark.parametrize('payload', [None, [], 'not a mapping'])
def test_non_mapping_payload_fails_closed_with_canonical_row_id(state, payload):
    with state.db() as db:
        db.execute('UPDATE scans SET payload=?',(json.dumps(payload),))
    result=ns.verify_latest_assessment()
    assert result['status']=='verification_failed'
    assert result['nico_verification']['scan_id']=='scan_A'
    assert result['nico_verification']['passed'] is False
    assert 'scan_row_identity_mismatch' in result['nico_verification']['checks']


def test_malformed_json_is_sanitized_cli_failure(state, capsys):
    with state.db() as db:
        db.execute('UPDATE scans SET payload=?',('{',))
    with pytest.raises(SystemExit) as caught:
        ns.main(['verify','latest'])
    assert caught.value.code==1
    assert json.loads(capsys.readouterr().out)=={'status':'error','error':'Assessment failed.','error_type':'JSONDecodeError'}


def test_concurrent_thread_scan_insert_after_selection(state, monkeypatch):
    import threading

    selected=threading.Event(); committed=threading.Event(); failures=[]
    original=state.latest_scan
    def writer():
        try:
            assert selected.wait(5)
            other=LocalStore(state.path)
            other.save_scan({'id':'scan_B','created_at':'2026-01-02','findings':[]},'synthetic')
        except BaseException as exc:
            failures.append(exc)
        finally:
            committed.set()
    def read(**kwargs):
        snapshot=original(**kwargs)
        selected.set()
        assert committed.wait(5)
        return snapshot
    monkeypatch.setattr(state,'latest_scan',read)
    thread=threading.Thread(target=writer)
    thread.start()
    try:
        result=ns.verify_latest_assessment()
    finally:
        thread.join(5)
    assert not thread.is_alive() and not failures
    assert original(preserve_row_identity=True)['id']=='scan_B'
    assert result['status']=='verified'
    assert result['nico_verification']['scan_id']=='scan_A'
    print(json.dumps({'scenario':'real concurrent writer, barrier after scan read','result':result,'database_latest':'scan_B'},sort_keys=True))
