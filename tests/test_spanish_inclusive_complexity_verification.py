from copy import deepcopy

import pytest

from nico.comprehensive_current_report_truth_parity_v1 import strict_spanish_presentation_v1
from nico.comprehensive_same_run_locale_report_v1 import build_same_run_locale_markdown_projection
from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
from tests.test_v2_premium_report_renderer import _package


def test_current_inclusive_complexity_verification_translates_and_preserves_anchor():
    source = ('The exact-SHA rerun no longer reports cyclomatic complexity of 30 or greater at '
              'apps/web/app/AssessmentRecoveryActions.tsx:61')
    translated = strict_spanish_presentation_v1(source, 'verification')
    assert 'igual o superior a 30' in translated
    assert 'apps/web/app/AssessmentRecoveryActions.tsx:61' in translated
    assert 'no longer reports' not in translated


def test_unknown_complexity_verification_remains_fail_closed():
    with pytest.raises(ValueError, match='missing Spanish presentation translation'):
        strict_spanish_presentation_v1(
            'The exact-SHA rerun no longer reports cognitive complexity of 30 or greater at '
            'apps/web/app/AssessmentRecoveryActions.tsx:61', 'verification')


def test_inclusive_verification_survives_real_bounded_locale_projection():
    package = _package('en')
    item = package['json']['canonical_findings'][0]
    item['verification'] = [
        'The exact-SHA rerun no longer reports cyclomatic complexity of 30 or greater at '
        'apps/web/app/page.tsx:100'
    ]
    source = rebuild_client_artifacts(package)
    source['report_id'] = 'comprehensive_report_inclusive_complexity'
    identity = source['json']['identity']
    status = {key: identity[key] for key in ('run_id', 'repository', 'commit_sha', 'evidence_ledger_id')}
    status.update(terminal=True, report_language='en', reports=source)
    before = deepcopy(status)
    english = build_same_run_locale_markdown_projection(status, 'en')
    spanish = build_same_run_locale_markdown_projection(status, 'es-MX')
    assert status == before
    assert spanish['canonical_truth_sha256'] == english['canonical_truth_sha256']
    assert spanish['client_delivery_allowed'] is False
    assert spanish['human_review_required'] is True
