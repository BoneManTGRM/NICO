"""Mock driver contract tests, NOT PostgreSQL concurrency/restart qualification."""
from copy import deepcopy
from dataclasses import replace
from unittest.mock import Mock

import pytest

from nico.review_pdf_preparation_jobs_v1 import (
    PostgresReviewPdfPreparationJobs, PreparationConflict,
)
from nico.storage import PostgresAdapter
from tests.test_review_pdf_preparation_jobs_v1 import identity


class MockConnection:
    def __init__(self, database):
        self.database = database
        self.events = []
        self.row = None
        self.before = deepcopy(database['row'])

    def execute(self, sql, params=()):
        self.events.append((sql, params))
        if sql.startswith('SELECT customer_id'):
            self.row = deepcopy(self.database['row'])
        elif 'clock_timestamp()' in sql:
            self.row = {'epoch': self.database['now']}
        elif sql.startswith('INSERT'):
            self.database['row'] = dict(customer_id=params[1], project_id=params[2],
                                        status=params[3], payload=deepcopy(params[4]))
        return self

    def fetchone(self):
        return self.row

    def commit(self):
        self.events.append(('COMMIT', ()))

    def rollback(self):
        self.database['row'] = self.before
        self.events.append(('ROLLBACK', ()))

    def close(self):
        self.events.append(('CLOSE', ()))


@pytest.fixture
def ledger():
    database = {'row': None, 'now': 1000., 'connections': []}
    # Bypass production constructor: it initializes schema and is forbidden here.
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter._jsonb = deepcopy
    def connect():
        con = MockConnection(database)
        database['connections'].append(con)
        return con
    adapter._connect = connect
    return PostgresReviewPdfPreparationJobs(adapter), database


def test_constructor_never_connects_or_initializes_schema():
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter._connect = Mock(side_effect=AssertionError('unexpected connection'))
    adapter._init_schema = Mock(side_effect=AssertionError('unexpected DDL'))
    PostgresReviewPdfPreparationJobs(adapter)
    adapter._connect.assert_not_called()
    adapter._init_schema.assert_not_called()
    with pytest.raises(TypeError):
        PostgresReviewPdfPreparationJobs(object())


def test_mock_enqueue_dedup_and_sql_contract(ledger):
    jobs, db = ledger
    first = jobs.enqueue(identity(), preparation_authorized=True)
    assert jobs.enqueue(identity(), preparation_authorized=True) == first
    for con in db['connections']:
        statements = [sql for sql, _ in con.events]
        assert statements[:4] == ['SET TRANSACTION ISOLATION LEVEL READ COMMITTED',
            "SET LOCAL lock_timeout = '5s'", "SET LOCAL statement_timeout = '5s'", 'SELECT pg_advisory_xact_lock(%s)']
        assert statements[-2:] == ['COMMIT', 'CLOSE']
        assert not any('CREATE ' in s or 'ALTER ' in s for s in statements)
    assert sum(sql.startswith('INSERT') for con in db['connections'] for sql, _ in con.events) == 1
    assert 'clock_timestamp()' in db['connections'][0].events[5][0]


def test_mock_expired_owner_fenced_after_reclaim(ledger):
    jobs, db = ledger
    jobs.enqueue(identity(), preparation_authorized=True)
    first = jobs.claim(identity())
    assert jobs.claim(identity()) is None
    db['now'] += 31
    second = jobs.claim(identity())
    assert second['lease_id'] != first['lease_id']
    for action in (lambda: jobs.heartbeat(identity(), first['lease_id']),
                   lambda: jobs.fail(identity(), first['lease_id']),
                   lambda: jobs.record_rendered(identity(), first['lease_id'],
                       observed_source=identity(), pdf_sha256='a' * 64)):
        with pytest.raises(PreparationConflict):
            action()
        assert db['connections'][-1].events[-2:] == [('ROLLBACK', ()), ('CLOSE', ())]
    result = jobs.record_rendered(identity(), second['lease_id'],
                                  observed_source=identity(), pdf_sha256='a' * 64)
    assert result['status'] == 'rendered_unverified'
    assert result['client_delivery_allowed'] is False
    assert result['human_review_required'] is True


def test_mock_source_and_scope_conflicts(ledger):
    jobs, db = ledger
    jobs.enqueue(identity(), preparation_authorized=True)
    owner = jobs.claim(identity())
    with pytest.raises(PreparationConflict):
        jobs.record_rendered(identity(), owner['lease_id'],
            observed_source=replace(identity(), source_revision=67), pdf_sha256='a' * 64)
    db['row']['customer_id'] = 'different tenant'
    with pytest.raises(PreparationConflict):
        jobs.heartbeat(identity(), owner['lease_id'])


@pytest.mark.parametrize('expiry', ['lease', 'absolute'])
def test_mock_bounded_claims_and_deadline(ledger, expiry):
    jobs, db = ledger
    jobs.enqueue(identity(), preparation_authorized=True)
    jobs.claim(identity())
    db['now'] += 31
    jobs.claim(identity())
    db['now'] += 31 if expiry == 'lease' else 1000
    assert jobs.claim(identity()) is None
    assert jobs.get(identity())['status'] == 'budget_exhausted'


def test_lock_failure_rolls_back_and_closes_without_reads(ledger):
    jobs, db = ledger
    con = MockConnection(db)
    original = con.execute
    def execute(sql, params=()):
        if 'pg_advisory_xact_lock' in sql:
            raise TimeoutError('synthetic lock timeout')
        return original(sql, params)
    con.execute = execute
    jobs.adapter._connect = lambda: con
    with pytest.raises(TimeoutError):
        jobs.enqueue(identity(), preparation_authorized=True)
    assert db['row'] is None
    assert con.events[-2:] == [('ROLLBACK', ()), ('CLOSE', ())]
    assert not any(sql.startswith('SELECT customer_id') for sql, _ in con.events)
