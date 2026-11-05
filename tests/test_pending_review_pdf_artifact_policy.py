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
    result = artifact()
    i = replace(identity(), language='en', artifact_mode='pending-source-frozen',
                source_artifact_sha256=result['headers']['x-nico-pdf-sha256'])
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


def frozen_fixture():
    """A real source PDF, and a different valid PDF with self-consistent hashes."""
    import base64
    import hashlib
    import io
    from copy import deepcopy
    from dataclasses import asdict
    from pypdf import PdfReader, PdfWriter
    original = artifact()
    source_sha = original['headers']['x-nico-pdf-sha256']
    i = replace(identity(), language='en', artifact_mode='pending-source-frozen',
                source_artifact_sha256=source_sha)
    original['identity'] = asdict(i)
    original['headers'].update({
        'x-nico-report-language': 'en',
        'x-nico-review-pdf-artifact-mode': i.artifact_mode,
        'x-nico-frozen-source-artifact': 'true',
        'x-nico-localized-artifact-requires-new-approval': 'false',
        'x-nico-localized-artifact-approval-invalidated': 'false',
    })
    different = deepcopy(original)
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    stream = io.BytesIO()
    writer.write(stream)
    data = stream.getvalue()
    digest = hashlib.sha256(data).hexdigest()
    assert digest != source_sha
    assert len(PdfReader(io.BytesIO(data), strict=True).pages) == 1
    different['pdf_base64'] = base64.b64encode(data).decode()
    different['headers'].update({'x-nico-pdf-sha256': digest, 'x-nico-artifact-sha256': digest})
    return i, original, different


@pytest.mark.parametrize('boundary', ['worker', 'publication', 'retrieval'])
def test_different_valid_frozen_pdf_rejected_at_each_boundary(seam, monkeypatch, boundary):
    from nico.review_pdf_preparation_api_v1 import PreparationRuntime
    i, original, different = frozen_fixture()
    # The positive fixture binds the actual source digest, not an unrelated constant.
    assert validate_result(original, i)[1] == i.source_artifact_sha256
    if boundary == 'worker':
        with pytest.raises(ValueError, match='frozen_source_checksum'):
            validate_result(different, i)
        return
    service, jobs, _, _, worker, _, _ = seam
    jobs.enqueue(i, preparation_authorized=True)
    if boundary == 'publication':
        worker.return_value = different
        with pytest.raises(ValueError, match='frozen_source_checksum'):
            service.run_once(i)
        assert jobs.get(i)['status'] != 'ready'
        assert 'pdf_base64' not in jobs.get(i)
    else:
        worker.return_value = original
        service.run_once(i)
        runtime = PreparationRuntime(service)
        monkeypatch.setattr(runtime, '_job', lambda *args, **kw: (i, jobs.get(i)))
        binding = {'commit_sha': i.commit_sha, 'canonical_truth_sha256': i.canonical_truth_sha256}
        assert runtime.retrieve(i.run_id, i.language, i.job_id, binding).headers['x-nico-pdf-sha256'] == i.source_artifact_sha256
        with jobs._transaction(i) as con:
            job = jobs._read(con, i)
            job.update(pdf_base64=different['pdf_base64'], result_headers=different['headers'],
                       pdf_sha256=different['headers']['x-nico-pdf-sha256'])
            jobs._write(con, i, job)
        with pytest.raises(ValueError, match='frozen_source_checksum'):
            runtime.retrieve(i.run_id, i.language, i.job_id, binding)


def test_localized_draft_is_allowed_to_have_new_pdf_bytes():
    result = artifact()
    assert result['headers']['x-nico-pdf-sha256'] != identity().source_artifact_sha256
    assert validate_result(result, identity())[0].startswith(b'%PDF')
