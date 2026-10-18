from dataclasses import replace

import pytest

from tests.test_review_pdf_preparation_jobs_v1 import identity
from tests.test_review_pdf_preparation_service_v1 import artifact
from nico.review_pdf_preparation_worker_v1 import validate_result


@pytest.mark.parametrize('header,value', [
    ('x-nico-localized-artifact-requires-new-approval', None),
    ('x-nico-localized-artifact-requires-new-approval', 'false'),
    ('x-nico-localized-artifact-approval-invalidated', None),
    ('x-nico-localized-artifact-approval-invalidated', 'false'),
    ('x-nico-frozen-source-artifact', 'true'),
    ('x-nico-accepted-edition-language', 'en'),
    ('x-nico-human-review-completed', 'true'),
])
def test_localized_draft_rejects_missing_or_inherited_approval(header, value):
    result = artifact()
    result['headers'].update({
        'x-nico-localized-artifact-requires-new-approval': 'true',
        'x-nico-localized-artifact-approval-invalidated': 'true',
        'x-nico-artifact-finality': 'automated_draft',
        'x-nico-review-pdf-artifact-mode': 'pending-source-localized-draft',
    })
    if value is None:
        result['headers'].pop(header, None)
    else:
        result['headers'][header] = value
    with pytest.raises(ValueError):
        validate_result(result, identity())

@pytest.mark.parametrize('change', ['approved', 'rejected', 'locale', 'source'])
def test_authoritative_pending_source_policy_rejects_changes(change):
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico.review_pdf_artifact_policy_v1 import artifact_mode
    status = _fixed_status('en')
    assert artifact_mode(status, 'en') in {'pending-source-frozen', 'pending-source-localized-draft'}
    assert artifact_mode(status, 'es-MX') == 'pending-source-localized-draft'
    if change == 'approved':
        status.update(status='approved', human_review_completed=True)
    elif change == 'rejected':
        status.update(status='rejected', human_review_completed=True,
                      response_projection={'rejection_review_integrity_valid': True})
    elif change == 'locale':
        status['report_language'] = 'es-MX'
    else:
        status['commit_sha'] = '0' * 40
    with pytest.raises((ValueError, RuntimeError)):
        artifact_mode(status, 'es-MX')


@pytest.mark.parametrize('phase', ['publication', 'retrieval'])
@pytest.mark.parametrize('header', ['x-nico-localized-artifact-requires-new-approval',
                                    'x-nico-localized-artifact-approval-invalidated',
                                    'x-nico-review-pdf-artifact-mode'])
def test_durable_boundary_rejects_missing_mode_headers(seam, monkeypatch, phase, header):
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime
    service, jobs, source, _, worker, _, _ = seam
    i = identity()
    if phase == 'publication':
        result = artifact()
        result['headers'].pop(header)
        worker.return_value = result
        with pytest.raises(ValueError):
            service.run_once(i)
        assert jobs.get(i)['status'] != 'ready'
    else:
        service.run_once(i)
        runtime = PreparationRuntime(service)
        monkeypatch.setattr(runtime, '_job', lambda *args, **kw: (i, jobs.get(i)))
        with jobs._transaction(i) as connection:
            job = jobs._read(connection, i)
            job['result_headers'].pop(header)
            jobs._write(connection, i, job)
        with pytest.raises(ValueError):
            runtime.retrieve(i.run_id, i.language, i.job_id,
                {'commit_sha': i.commit_sha, 'canonical_truth_sha256': i.canonical_truth_sha256})


from tests.test_review_pdf_preparation_service_v1 import seam


def test_same_locale_frozen_source_requires_explicit_non_derivative_headers():
    from dataclasses import asdict
    i = replace(identity(), language='en', artifact_mode='pending-source-frozen')
    result = artifact()
    result['identity'] = asdict(i)
    result['headers'].update({
        'x-nico-report-language': 'en',
        'x-nico-review-pdf-artifact-mode': 'pending-source-frozen',
        'x-nico-frozen-source-artifact': 'true',
        'x-nico-localized-artifact-requires-new-approval': 'false',
        'x-nico-localized-artifact-approval-invalidated': 'false',
    })
    assert validate_result(result, i)[0].startswith(b'%PDF')
    result['headers']['x-nico-localized-artifact-approval-invalidated'] = 'true'
    with pytest.raises(ValueError):
        validate_result(result, i)


def test_mode_and_policy_are_independent_job_identity_bindings():
    i = identity()
    assert replace(i, artifact_mode='pending-source-frozen').job_id != i.job_id
    assert replace(i, policy_sha256='0'*64).job_id != i.job_id
    assert replace(i, language='en').job_id != i.job_id


def test_missing_persisted_mode_is_not_upgraded_to_a_qualified_job():
    from dataclasses import asdict
    from nico.review_pdf_preparation_jobs_v1 import PreparationIdentity
    historical = asdict(identity())
    historical.pop('artifact_mode')
    with pytest.raises(TypeError):
        PreparationIdentity(**historical)
