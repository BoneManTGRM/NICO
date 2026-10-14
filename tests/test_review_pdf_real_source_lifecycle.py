"""Local real-source/child smoke; PostgreSQL restart/retrieval belongs to CI."""
import sqlite3
from threading import BoundedSemaphore

from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import ReviewPdfPreparationJobs
from nico.review_pdf_preparation_service_v1 import RetainedSourceAuthority, ReviewPdfPreparationService


def test_real_owned_record_restores_and_child_publishes_without_an_assessment(tmp_path, monkeypatch):
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record, controller_for
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime, runtime_policy
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'e'*40)
    path = tmp_path/'owned.sqlite'
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path))
    store.ensure_schema()  # Only this disposable local unit-test database.
    record = store.create(build_owned_record())
    source = RetainedSourceAuthority(store, controller_for(store), runtime_policy)
    service = ReviewPdfPreparationService(ReviewPdfPreparationJobs(SQLiteRuntimeAdapter(path)),
                                          source, capacity=BoundedSemaphore(1))
    runtime = PreparationRuntime(service)
    status = source.controller._status_artifact_from_record(store.load(record['identity']['run_id']))
    binding = dict(commit_sha=status['commit_sha'], canonical_truth_sha256=status['reports']['canonical_truth_sha256'])
    projected = runtime.prepare(status['run_id'], 'es-MX', binding)
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
    renderer, policy = runtime_policy()
    ident = record['identity']
    identity = PreparationIdentity(ident['customer_id'], ident['project_id'], ident['run_id'], ident['repository'],
        ident['commit_sha'], record['revision'], record['integrity_sha256'], binding['canonical_truth_sha256'],
        status['reports']['pdf_sha256'], renderer, policy, 'es-MX')
    assert projected['job_id'] == identity.job_id
    before = source.capture(identity)
    ready = service.run_once(identity)
    assert ready['status'] == 'ready' and ready['validated_page_count'] > 0
    assert ready['human_review_required'] is True and ready['client_delivery_allowed'] is False
    assert source.capture(identity) == before
    assert store.load(identity.run_id) == record
    runtime.close()
