"""Pending-source review artifacts only; never grants source or delivery approval."""
from nico.review_pdf_preparation_jobs_v1 import PreparationConflict

SOURCE = 'pending-source-frozen'
LOCALIZED = 'pending-source-localized-draft'
VERSION = 'pending-source-review-artifact.v1'


def artifact_mode(status, language):
    from nico.comprehensive_same_run_locale_report_v1 import (
        _source_lifecycle_projection, _validate_status_canonical_identity,
        _frozen_source_pdf_response,
    )
    reports = status.get('reports') or {}
    canonical = reports.get('json') or {}
    lifecycle = _source_lifecycle_projection(status, reports, canonical)
    source_state = str(status.get('status') or (status.get('record') or {}).get('status') or '').strip().casefold()
    if (source_state in {'approved', 'rejected', 'declined'} or status.get('terminal') is not True or language not in {'en', 'es-MX'}
            or lifecycle['approval_status'] != 'pending_human_approval'
            or lifecycle['client_delivery_allowed'] is not False):
        raise PreparationConflict('pending_review_draft_required')
    source_language = _validate_status_canonical_identity(status, canonical)['report_language']
    # Existing presentation/integrity wrappers can also reproject the same locale.
    # Reuse their frozen-source decision; never infer approval policy from locale alone.
    if language == source_language and _frozen_source_pdf_response(status, language) is not None:
        return SOURCE
    return LOCALIZED


def validate_headers(headers, mode):
    if (any(value for key, value in headers.items() if key.startswith('x-nico-accepted-'))
            or headers.get('x-nico-human-review-completed') == 'true'
            or headers.get('x-nico-human-reviewed') == 'true'):
        raise ValueError('review_pdf_accepted_authority_forbidden')
    expected = {'x-nico-review-pdf-artifact-mode': mode}
    if mode == LOCALIZED:
        expected.update({
            'x-nico-localized-artifact-requires-new-approval': 'true',
            'x-nico-localized-artifact-approval-invalidated': 'true',
            'x-nico-artifact-finality': 'automated_draft',
        })
        if headers.get('x-nico-frozen-source-artifact') not in (None, 'false'):
            raise ValueError('review_pdf_derivative_cannot_be_frozen_source')
    elif mode == SOURCE:
        expected.update({
            'x-nico-frozen-source-artifact': 'true',
            'x-nico-localized-artifact-requires-new-approval': 'false',
            'x-nico-localized-artifact-approval-invalidated': 'false',
        })
    else:
        raise ValueError('review_pdf_artifact_mode_invalid')
    if any(headers.get(key) != value for key, value in expected.items()):
        raise ValueError('review_pdf_artifact_policy_invalid')
