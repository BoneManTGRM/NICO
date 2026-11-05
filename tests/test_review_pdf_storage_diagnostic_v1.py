from copy import deepcopy
from types import SimpleNamespace
from threading import Event
from unittest.mock import Mock
import json
import time

import pytest

from nico import review_pdf_storage_diagnostic_v1 as diagnostic
from nico.review_pdf_preparation_deadline_v1 import DeadlineGuard
from nico.specialist_access_v1 import issue_specialist_session
from tests.test_review_pdf_preparation_api_v1 import client, path


class Connection:
    def __init__(self, missing=None, fail=False):
        self.info = SimpleNamespace(transaction_status=0)
        self.commands = []
        self.missing = missing
        self.fail = fail
        self.rolled_back = self.closed = False

    def execute(self, sql, params=None):
        self.commands.append((sql, params))
        if self.fail:
            raise RuntimeError('postgres://private-password/customer-record')
        self.last_params = params
        return self

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def fetchone(self):
        if self.last_params is None:
            return (True,)
        table = self.last_params[0]
        return None if table == self.missing else (True, True, list(diagnostic.EXPECTED[table]))

    def rollback(self):
        self.rolled_back = True

    def close(self):
        self.closed = True


def fixture(connection=None):
    connection = connection or Connection()
    factory = Mock(return_value=connection)
    state = dict(configured=True, persistence_adapter='postgres',
                 survives_container_replacement_verified=True)
    app = SimpleNamespace(state=SimpleNamespace(
        comprehensive_runtime=state,
        comprehensive_api_controller=SimpleNamespace(_service=SimpleNamespace(
            _store=SimpleNamespace(_dialect='postgres', _connection_factory=factory)))))
    return app, connection, factory


def probe(app):
    return diagnostic.inspect_existing_runtime(app, DeadlineGuard(10, Event()))


def test_catalog_only_read_only_bounded_and_nonmutating():
    app, con, factory = fixture()
    before = deepcopy(app.state.comprehensive_runtime)
    result = probe(app)
    assert result['probe_complete'] and result['schema_read_compatible']
    assert result['read_only_transaction'] and result['canonical_postgres']
    assert result['lifecycle_qualified'] is False
    assert app.state.comprehensive_runtime == before
    factory.assert_called_once_with()
    assert con.rolled_back and con.closed
    assert con.commands[0] == ('BEGIN READ ONLY', None)
    assert len(con.commands) == 8
    for sql, params in con.commands:
        assert sql.startswith(('BEGIN READ ONLY', 'SET LOCAL', 'SELECT'))
        if params:
            assert 'FROM pg_catalog.pg_class' in sql
            assert params[0] in diagnostic.EXPECTED
    assert len(json.dumps(result)) < 1500
    assert 'customer-record' not in json.dumps(result)


@pytest.mark.parametrize('field,value', [('configured',False),('persistence_adapter','sqlite'),
                                        ('survives_container_replacement_verified',False)])
def test_unqualified_runtime_does_not_connect(field,value):
    app, con, factory = fixture()
    app.state.comprehensive_runtime[field] = value
    result = probe(app)
    factory.assert_not_called()
    assert result['schema_read_compatible'] is None and not result['probe_complete']


def test_absent_runtime_is_unknown_not_false():
    result = probe(SimpleNamespace(state=SimpleNamespace()))
    assert result['canonical_postgres'] is None
    assert result['schema_read_compatible'] is None
    assert set(result['tables'].values()) == {None}


@pytest.mark.parametrize('table', diagnostic.EXPECTED)
def test_missing_table_is_incompatible(table):
    app, _, _ = fixture(Connection(missing=table))
    result = probe(app)
    assert result['probe_complete'] and result['tables'][table] is False
    assert result['schema_read_compatible'] is False


def test_failure_redacted_and_connection_closed():
    app, con, _ = fixture(Connection(fail=True))
    result = probe(app)
    assert not result['probe_complete']
    assert con.closed and con.rolled_back
    assert 'private-password' not in json.dumps(result)


def test_existing_transaction_never_rolled_back_or_used():
    app, con, _ = fixture()
    con.info.transaction_status = 2
    assert not probe(app)['probe_complete']
    assert not con.commands and not con.rolled_back and con.closed


def test_timeout_quarantines_slot_and_late_connect_only_closes(monkeypatch):
    app, con, factory = fixture()
    entered, finish = Event(), Event()
    def connect():
        entered.set()
        assert finish.wait(3)
        return con
    factory.side_effect = connect
    monkeypatch.setattr(diagnostic, 'DEADLINE_SECONDS', .04)
    try:
        result = diagnostic.diagnose_storage(app)
        assert entered.is_set() and result['status'] == 'unavailable'
        assert diagnostic.diagnose_storage(app)['status'] == 'busy'
        assert factory.call_count == 1
    finally:
        finish.set()
    for _ in range(100):
        if con.closed:
            break
        time.sleep(.01)
    assert con.closed and con.rolled_back and not con.commands
    time.sleep(.05)


def test_authenticated_diagnostic_independent_of_activation(client, monkeypatch):
    http, runtime, app = client
    app.state.review_pdf_runtime = None
    inspect = Mock(return_value={'probe_complete':False, 'lifecycle_qualified':False})
    monkeypatch.setattr(diagnostic, 'diagnose_storage', inspect)
    url = path() + '?storage_compatibility=true'
    assert http.get(url).status_code == 401
    assert http.get(url, headers={'x-nico-admin-token':'bad'}).status_code == 403
    inspect.assert_not_called()
    token, _ = issue_specialist_session({'authority':'nico_admin'})
    response = http.get(url, headers={'x-nico-operator-session':token})
    assert response.status_code == 200 and 'no-store' in response.headers['cache-control']
    inspect.assert_called_once_with(app)
    assert runtime.mock_calls == []


@pytest.mark.parametrize('suffix,query', [('/pdf','storage_compatibility=true'),
    ('','storage_compatibility=false'), ('','storage_compatibility=true&extra=1'),
    ('','storage_compatibility=true&storage_compatibility=true')])
def test_diagnostic_rejects_extra_inputs(client,monkeypatch,suffix,query):
    http, runtime, app = client
    inspect=Mock()
    monkeypatch.setattr(diagnostic,'diagnose_storage',inspect)
    assert http.get(path(suffix)+'?'+query,headers={'x-nico-admin-token':'synthetic-admin-token'}).status_code==422
    inspect.assert_not_called()
    assert runtime.mock_calls == []


def test_proof_authority_cannot_probe(client,monkeypatch):
    http, runtime, app = client
    inspect=Mock()
    monkeypatch.setattr(diagnostic,'diagnose_storage',inspect)
    token,_=issue_specialist_session({'authority':'nico_admin'},scope='nico_production_proof',
        retained_claims={k:'synthetic' for k in ('repository','ref','sha','workflow_ref','run_id','run_attempt')})
    response=http.get(path()+'?storage_compatibility=true',headers={'x-nico-operator-session':token})
    assert response.status_code==403
    inspect.assert_not_called()


@pytest.mark.parametrize('field', ['configured','survives_container_replacement_verified','persistence_adapter'])
@pytest.mark.parametrize('value', [None, [], 1])
def test_missing_or_malformed_runtime_evidence_is_unknown(field,value):
    app, con, factory = fixture()
    app.state.comprehensive_runtime[field] = value
    result = probe(app)
    key = {'configured':'runtime_configured', 'persistence_adapter':'canonical_postgres',
           'survives_container_replacement_verified':'runtime_durability_claim'}[field]
    assert result[key] is None
    assert result['schema_read_compatible'] is None
    factory.assert_not_called()


def test_bad_connection_metadata_closes_factory_connection():
    app, con, _ = fixture()
    con.info = None
    assert not probe(app)['probe_complete']
    assert con.closed and not con.commands


@pytest.mark.parametrize('row', [(False,True,[]),(True,False,[]),(True,True,['job_id'])])
def test_non_table_permission_or_columns_do_not_pass(row):
    app, con, _ = fixture()
    original = con.fetchone
    con.fetchone = lambda: row if con.last_params else original()
    result = probe(app)
    assert result['probe_complete'] and result['schema_read_compatible'] is False
    assert not any(result['tables'].values())


def test_readonly_not_confirmed_never_checks_catalogs():
    app, con, _ = fixture()
    con.fetchone = lambda: (False,)
    result = probe(app)
    assert result['read_only_transaction'] is False and not result['probe_complete']
    assert all(params is None for sql,params in con.commands)
    assert con.closed and con.rolled_back


def test_post_diagnostic_never_prepares(client,monkeypatch):
    http,runtime,app=client
    inspect=Mock()
    monkeypatch.setattr(diagnostic,'diagnose_storage',inspect)
    response=http.post(path()+'?storage_compatibility=true',
        headers={'x-nico-admin-token':'synthetic-admin-token'},
        json={'prepare':True,'commit_sha':'a'*40,'canonical_truth_sha256':'b'*64})
    assert response.status_code==422
    inspect.assert_not_called()
    assert runtime.mock_calls==[]
