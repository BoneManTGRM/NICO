"""Synthetic proof for the existing loopback CI database; no schema initialization."""
from __future__ import annotations
import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
import json
import os
from pathlib import Path
import subprocess
import sys
from urllib.parse import urlparse
from uuid import uuid4

# Standalone synthetic proof must not initialize the general runtime from an
# unrelated inherited production database variable, even before target validation.
for key in tuple(os.environ):
    if key.startswith('PG') or key in {'DATABASE_URL', 'DATABASE_PRIVATE_URL',
            'POSTGRES_URL', 'POSTGRES_PRIVATE_URL', 'RAILWAY_DATABASE_URL', 'RAILWAY_POSTGRES_URL'}:
        os.environ.pop(key)
os.environ['NICO_DISABLE_POSTGRES'] = 'true'
os.environ['NICO_ENABLE_SQLITE_DURABLE_STORAGE'] = 'false'

from nico.review_pdf_preparation_jobs_v1 import (
    PreparationIdentity, PreparationConflict, PostgresReviewPdfPreparationJobs,
)
from nico.storage import PostgresAdapter


def existing_adapter():
    import psycopg
    from psycopg.rows import dict_row
    from psycopg.types.json import Jsonb
    url = os.environ.get('NICO_TEST_DATABASE_URL', '')
    parsed = urlparse(url)
    if (parsed.scheme not in ('postgres', 'postgresql') or parsed.hostname != '127.0.0.1'
            or parsed.port != 5432 or parsed.path != '/nico' or parsed.query or parsed.fragment):
        raise ValueError('explicit_loopback_ci_database_required')
    adapter = PostgresAdapter.__new__(PostgresAdapter)
    adapter.database_url, adapter._psycopg = url, psycopg
    adapter._dict_row, adapter._jsonb = dict_row, Jsonb
    return adapter


def proof():
    adapter = existing_adapter()
    jobs = PostgresReviewPdfPreparationJobs(adapter)
    identity = PreparationIdentity('review-pdf-proof-' + uuid4().hex, 'synthetic-project',
        'synthetic-run', 'synthetic-repo', 'a' * 40, 66, 'b' * 64, 'c' * 64,
        'd' * 64, 'e' * 40, 'f' * 64, 'es-MX', 'pending-source-localized-draft')
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(lambda _: jobs.enqueue(identity, preparation_authorized=True), range(8)))
    assert all(row == rows[0] for row in rows)
    encoded = json.dumps(asdict(identity))
    # Independent interpreters use independent connections and module state.
    processes = [subprocess.Popen([sys.executable, __file__, '--claim', encoded],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(4)]
    results = []
    try:
        for process in processes:
            stdout, _ = process.communicate(timeout=30)
            assert process.returncode == 0, 'claim subprocess failed'
            results.append(json.loads(stdout))
    finally:
        for process in processes:
            if process.poll() is None:
                process.kill(); process.wait(timeout=5)
    owners = [row for row in results if row is not None]
    assert len(owners) == 1
    first = owners[0]
    jobs.heartbeat(identity, first['lease_id'])
    assert jobs.claim(identity) is None
    # Fixture-only expiry, scoped by unique synthetic tenant and job identity.
    with adapter._connect() as con:
        con.execute("UPDATE client_jobs SET payload=jsonb_set(payload,'{lease_until_epoch}','0'::jsonb) "
            'WHERE job_id=%s AND customer_id=%s', (identity.job_id, identity.customer_id))
    second = jobs.claim(identity)
    assert second and second['lease_id'] != first['lease_id']
    checks = {'concurrent_enqueue_deduplicated': True, 'cross_process_single_owner': True,
              'active_lease_preserved': True, 'expired_lease_reclaimed': True}
    for name, action in {
        'stale_heartbeat_rejected': lambda: jobs.heartbeat(identity, first['lease_id']),
        'stale_failure_rejected': lambda: jobs.fail(identity, first['lease_id']),
        'stale_result_rejected': lambda: jobs.record_rendered(identity, first['lease_id'],
            observed_source=identity, pdf_sha256='a' * 64),
    }.items():
        try:
            action()
        except PreparationConflict:
            checks[name] = True
        else:
            raise AssertionError(name)
    result = jobs.record_rendered(identity, second['lease_id'],
                                  observed_source=identity, pdf_sha256='a' * 64)
    assert result['status'] == 'rendered_unverified'
    reopened = PostgresReviewPdfPreparationJobs(existing_adapter()).get(identity)
    assert reopened == result and reopened['client_delivery_allowed'] is False
    assert jobs.claim(identity) is None
    checks.update(reconnect_preserved_result=True, delivery_remains_blocked=True,
                  terminal_not_reclaimed=True)
    return dict(status='passed', synthetic=True, live_production_claim=False,
        repository_executed=False, human_approval=False, client_delivery_allowed=False,
        commit_sha=subprocess.check_output(['git', 'rev-parse', 'HEAD'], text=True).strip(), checks=checks)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--claim')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.claim:
        print(json.dumps(PostgresReviewPdfPreparationJobs(existing_adapter()).claim(
            PreparationIdentity(**json.loads(args.claim)))))
    else:
        if args.output is None:
            parser.error('--output required')
        result = proof()
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
