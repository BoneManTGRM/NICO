from copy import deepcopy
import pytest
from nico import comprehensive_spanish_canonical_report_v87 as spanish
from nico.comprehensive_same_run_locale_report_v1 import _localized_draft_view
from nico.phase17_canonical_artifact_rebuild_v1 import build_localized_markdown_projection
from tests.test_v2_premium_report_renderer import _package

NODE = 'npm-audit: not applicable; No supported JavaScript package manifest, lockfile, or source tree exists at the assessed commit; npm-audit is not applicable to this repository snapshot.'
LOCK = 'typescript: ./package-lock.json is required for deterministic project-tool preparation.'

@pytest.mark.parametrize('text', [NODE, LOCK, LOCK.replace('./', 'apps/web/'), *spanish._NODE_APPLICABILITY_ES])
def test_known_scanner_limitation_preserves_meaning_in_spanish(text):
    result = spanish._translate_presentation_field(text, 'evidence')
    assert result != text
    assert 'not applicable' not in result
    assert 'is required for deterministic' not in result
    if 'package-lock.json' in text:
        assert text.split(' ')[1] in result

@pytest.mark.parametrize('text', [NODE, LOCK])
def test_unknown_appended_prose_still_blocks_publication(text):
    with pytest.raises(ValueError):
        spanish._translate_presentation_field(text + ' This unknown production behavior remains unverified and requires professional review.', 'evidence')


def test_bounded_markdown_localizes_actual_private_scanner_limitation_shapes():
    source = _package('en')['json']
    source['report_id'] = 'synthetic-private-scanner-spanish'
    source['stage_summaries'] = [{
        'stage_id': 'private_scanner_evidence_test',
        'title': 'Dependency, Security, and Static Analysis', 'status': 'review_required',
        'summary': 'Scanner execution evidence is incomplete.',
        'evidence': [NODE], 'unavailable_data_notes': [LOCK], 'unavailable': [LOCK], 'findings': [],
    }]
    before = deepcopy(source)
    result = build_localized_markdown_projection({'json': _localized_draft_view(source, 'es-MX')})
    assert 'npm-audit: no aplicable' in result['markdown']
    assert 'para preparar las herramientas del proyecto de forma determinista' in result['markdown']
    assert source == before
