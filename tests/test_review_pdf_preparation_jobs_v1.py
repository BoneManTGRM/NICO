from concurrent.futures import ThreadPoolExecutor
from dataclasses import fields, replace

import pytest

from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import (
    PreparationConflict, PreparationIdentity, ReviewPdfPreparationJobs,
)
from nico.storage import MemoryAdapter


def identity():
    return PreparationIdentity('tenant', 'project', 'comprun_fixture', 'repo', 'a' * 40,
                               66, 'b' * 64, 'c' * 64, 'd' * 64, 'e' * 40, 'f' * 64, 'es-MX')


@pytest.fixture
def jobs(tmp_path, monkeypatch):
    adapter = SQLiteRuntimeAdapter(tmp_path / 'existing.sqlite')
    ledger = ReviewPdfPreparationJobs(adapter)
    clock = [1000.0]
    monkeypatch.setattr(ledger, '_now', lambda connection: clock[0])
    return ledger, clock


@pytest.mark.parametrize('field', [field.name for field in fields(PreparationIdentity)])
def test_every_binding_dimension_changes_identity(field):
    before = identity()
    value = getattr(before, field)
    changed = 67 if field == 'source_revision' else 'en' if field == 'language' else '1' * len(value)
    assert replace(before, **{field: changed}).job_id != before.job_id


@pytest.mark.parametrize('changes', [
    {'source_revision': True}, {'source_revision': 0}, {'commit_sha': 'main'},
    {'policy_sha256': 'short'}, {'language': 'fr'}, {'customer_id': ''}, {'run_id': ' run'},
])
def test_invalid_identity_rejected(changes):
    with pytest.raises(ValueError):
        replace(identity(), **changes)


def test_no_memory_fallback_or_implicit_adapter_creation():
    with pytest.raises(TypeError):
        ReviewPdfPreparationJobs(MemoryAdapter())


def test_authorized_enqueue_deduplicates_and_leaves_source_bytes_and_schema(jobs):
    ledger, _ = jobs
    source = dict(status='review_required', revision=66, terminal=True,
                  canonical_truth_sha256='c' * 64, approval_status='pending_human_approval',
                  client_delivery_allowed=False, findings=[{'id': 'finding', 'detail': 'all evidence'}])
    ledger.adapter.put('assessment_runs', 'source', source)
    with ledger.adapter._connect() as con:
        original = con.execute("SELECT payload FROM nico_records WHERE item_id='source'").fetchone()[0]
        schema = list(con.execute('SELECT sql FROM sqlite_master ORDER BY name'))
    with pytest.raises(PermissionError):
        ledger.enqueue(identity())
    assert ledger.get(identity()) is None
    first = ledger.enqueue(identity(), preparation_authorized=True)
    assert first == ledger.enqueue(identity(), preparation_authorized=True)
    claim = ledger.claim(identity())
    ledger.record_rendered(identity(), claim['lease_id'], observed_source=identity(), pdf_sha256='a' * 64)
    with ledger.adapter._connect() as con:
        assert con.execute("SELECT payload FROM nico_records WHERE item_id='source'").fetchone()[0] == original
        assert [tuple(r) for r in con.execute('SELECT sql FROM sqlite_master ORDER BY name')] == [tuple(r) for r in schema]


def test_concurrent_enqueue_and_claim_have_one_owner(jobs):
    ledger, _ = jobs
    with ThreadPoolExecutor(max_workers=8) as pool:
        enqueued = list(pool.map(lambda _: ledger.enqueue(identity(), preparation_authorized=True), range(8)))
        claims = list(pool.map(lambda _: ledger.claim(identity()), range(8)))
    assert all(job == enqueued[0] for job in enqueued)
    assert sum(job is not None for job in claims) == 1
    assert ledger.get(identity())['attempts'] == 1


def test_restart_and_expired_owner_fencing(jobs):
    ledger, clock = jobs
    ledger.enqueue(identity(), preparation_authorized=True)
    first = ledger.claim(identity())
    reopened = ReviewPdfPreparationJobs(ledger.adapter)
    assert reopened.get(identity()) == ledger.get(identity())
    clock[0] += 31
    second = ledger.claim(identity())
    assert second['lease_id'] != first['lease_id']
    for operation in (ledger.heartbeat, ledger.fail):
        with pytest.raises(PreparationConflict):
            operation(identity(), first['lease_id'])
    with pytest.raises(PreparationConflict):
        ledger.record_rendered(identity(), first['lease_id'], observed_source=identity(), pdf_sha256='a' * 64)
    result = ledger.record_rendered(identity(), second['lease_id'], observed_source=identity(), pdf_sha256='a' * 64)
    assert result['status'] == 'rendered_unverified'
    assert result['client_delivery_allowed'] is False and result['human_review_required'] is True
    assert 'ready' not in result and 'download_url' not in result
    assert ledger.claim(identity()) is None


def test_source_change_and_wrong_tenant_cannot_publish(jobs):
    ledger, _ = jobs
    ledger.enqueue(identity(), preparation_authorized=True)
    claim = ledger.claim(identity())
    for changed in (replace(identity(), source_revision=67), replace(identity(), customer_id='other')):
        assert ledger.get(changed) is None
        with pytest.raises(PreparationConflict):
            ledger.record_rendered(identity(), claim['lease_id'], observed_source=changed, pdf_sha256='a' * 64)
    assert ledger.get(identity())['status'] == 'rendering'


def test_heartbeat_does_not_extend_absolute_budget(jobs):
    ledger, clock = jobs
    ledger.enqueue(identity(), preparation_authorized=True)
    claim = ledger.claim(identity())
    for _ in range(44):
        clock[0] += 20
        ledger.heartbeat(identity(), claim['lease_id'])
    assert ledger.get(identity())['lease_until_epoch'] == 1900
    clock[0] = 1900
    with pytest.raises(PreparationConflict):
        ledger.heartbeat(identity(), claim['lease_id'])
    assert ledger.claim(identity()) is None
    assert ledger.get(identity())['status'] == 'budget_exhausted'


def test_recovery_attempts_and_failure_are_bounded(jobs):
    ledger, clock = jobs
    ledger.enqueue(identity(), preparation_authorized=True)
    ledger.claim(identity())
    clock[0] += 31
    ledger.claim(identity())
    clock[0] += 31
    assert ledger.claim(identity()) is None
    assert ledger.get(identity())['status'] == 'budget_exhausted'
    other = replace(identity(), language='en')
    ledger.enqueue(other, preparation_authorized=True)
    claim = ledger.claim(other)
    ledger.fail(other, claim['lease_id'])
    assert ledger.claim(other) is None


def test_lease_and_tenant_corruption_fail_closed(jobs):
    ledger, _ = jobs
    ledger.enqueue(identity(), preparation_authorized=True)
    with ledger.adapter._connect() as con:
        con.execute("UPDATE nico_records SET customer_id='other' WHERE item_id=?", (identity().job_id,))
    with pytest.raises(PreparationConflict):
        ledger.claim(identity())
