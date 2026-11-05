"""Local real-source/child smoke; PostgreSQL restart/retrieval belongs to CI."""
import sqlite3
import pytest
from dataclasses import replace
from threading import BoundedSemaphore

from nico.comprehensive_run_store import ComprehensiveRunStore
from nico.durable_runtime_storage import SQLiteRuntimeAdapter
from nico.review_pdf_preparation_jobs_v1 import ReviewPdfPreparationJobs
from nico.review_pdf_preparation_service_v1 import RetainedSourceAuthority, ReviewPdfPreparationService


@pytest.mark.parametrize('source_language', ['en', 'es-MX'])
def test_real_owned_record_restores_and_child_publishes_without_an_assessment(tmp_path, monkeypatch, source_language):
    language = 'en'
    from scripts.postgres_review_pdf_lifecycle_proof import build_owned_record, controller_for
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime, runtime_policy
    monkeypatch.setenv('RAILWAY_GIT_COMMIT_SHA', 'e'*40)
    path = tmp_path/'owned.sqlite'
    store = ComprehensiveRunStore(lambda: sqlite3.connect(path))
    store.ensure_schema()  # Only this disposable local unit-test database.
    record = store.create(build_owned_record(source_language))
    source = RetainedSourceAuthority(store, controller_for(store), runtime_policy)
    service = ReviewPdfPreparationService(ReviewPdfPreparationJobs(SQLiteRuntimeAdapter(path)),
                                          source, capacity=BoundedSemaphore(1))
    runtime = PreparationRuntime(service)
    status = source.controller._status_artifact_from_record(store.load(record['identity']['run_id']))
    binding = dict(commit_sha=status['commit_sha'], canonical_truth_sha256=status['reports']['canonical_truth_sha256'])
    qualified = runtime.qualify(status['run_id'], language, binding)
    mode = qualified['artifact_mode']
    assert qualified['state'] == 'eligible'
    assert mode in {'pending-source-frozen', 'pending-source-localized-draft'}
    if source_language != language:
        assert mode == 'pending-source-localized-draft'
    projected = runtime.prepare(status['run_id'], language, binding)
    assert projected['job_id'] == qualified['job_id']
    assert runtime.prepare(status['run_id'], language, binding) == projected
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
    renderer, policy = runtime_policy()
    ident = record['identity']
    identity = PreparationIdentity(ident['customer_id'], ident['project_id'], ident['run_id'], ident['repository'],
        ident['commit_sha'], record['revision'], record['integrity_sha256'], binding['canonical_truth_sha256'],
        status['reports']['pdf_sha256'], renderer, policy, language, mode)
    assert projected['job_id'] == identity.job_id
    from nico.review_pdf_preparation_jobs_v1 import PreparationConflict
    with pytest.raises(PreparationConflict, match='artifact_mode_changed'):
        source.capture(replace(identity, artifact_mode='pending-source-frozen'
            if mode == 'pending-source-localized-draft' else 'pending-source-localized-draft'))
    before = source.capture(identity)
    ready = service.run_once(identity)
    assert ready['status'] == 'ready' and ready['validated_page_count'] > 0
    assert ready['human_review_required'] is True and ready['client_delivery_allowed'] is False
    assert ready['result_headers']['x-nico-review-pdf-artifact-mode'] == mode
    assert ready['result_headers']['x-nico-localized-artifact-requires-new-approval'] == ('true' if mode == 'pending-source-localized-draft' else 'false')
    assert ready['result_headers']['x-nico-localized-artifact-approval-invalidated'] == ('true' if mode == 'pending-source-localized-draft' else 'false')
    assert source.capture(identity) == before
    assert store.load(identity.run_id) == record
    runtime.close()
