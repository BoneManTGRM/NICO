"""Scanner summaries are localized as complete sentences before PDF layout."""
from copy import deepcopy

import pytest

from nico.comprehensive_human_review_package_cleanup_v1 import build_scanner_execution_stage
from nico.comprehensive_spanish_current_copy_worker_v98 import localize_current_report_copy_v98
from nico.comprehensive_spanish_canonical_report_v87 import _SCANNER_STATUS_ES


class StageRenderer:
    @staticmethod
    def _stage(stage_id, title, summary, **kwargs):
        return dict(stage_id=stage_id, title=title, summary=summary, **kwargs)


def canonical(state, language='es-MX'):
    return {'report_language': language, 'scanner_execution_records': [
        {'scanner_name': 'bandit', 'state': state, 'status': state,
         'completed': state in {'complete', 'completed', 'completed_clean', 'completed_with_findings'},
         'exact_commit_match': True, 'artifact_hash': 'b' * 64, 'findings': []}
    ]}


def summary(state):
    return (f'bandit: {state}; exact commit=yes; artifact=retained; '
            'confirmed material finding count=0; raw finding payload embedded=no.')


@pytest.mark.parametrize('state', sorted(_SCANNER_STATUS_ES))
def test_producer_localizes_entire_sentence_without_erasing_machine_identifiers(state):
    value = canonical(state)
    before = deepcopy(value)
    stage = build_scanner_execution_stage(value, StageRenderer)
    generated = next(s for s in stage['evidence'] if s.startswith('bandit:'))
    line = localize_current_report_copy_v98(generated)
    assert 'commit exacto=sí; artefacto=conservado' in line
    assert 'carga de hallazgos sin procesar incluida=no.' in line
    assert 'exact commit=' not in line
    assert 'raw finding payload' not in line
    if '_' in state:
        assert f'{state} ({_SCANNER_STATUS_ES[state]})' in line
    elif state == 'completed':
        assert line.startswith('bandit: ejecución completada;')
    assert localize_current_report_copy_v98(line) == line
    assert value == before


@pytest.mark.parametrize('state', sorted(_SCANNER_STATUS_ES))
def test_full_sentence_translator_accepts_all_registered_scanner_states(state):
    line = localize_current_report_copy_v98(summary(state))
    assert '; commit exacto=sí; artefacto=conservado;' in line
    assert '; carga de hallazgos sin procesar incluida=no.' in line
    assert 'raw finding payload' not in line
    if '_' in state:
        assert f'{state} ({_SCANNER_STATUS_ES[state]})' in line


def test_english_producer_and_canonical_evidence_are_unchanged():
    value = canonical('completed_with_findings', 'en')
    before = deepcopy(value)
    stage = build_scanner_execution_stage(value, StageRenderer)
    assert summary('completed_with_findings') in stage['evidence']
    assert value == before


def test_unregistered_status_does_not_silently_claim_a_spanish_translation():
    with pytest.raises(ValueError, match='missing Spanish scanner status translation'):
        localize_current_report_copy_v98(summary('invented_state'))


def test_unknown_unstructured_prose_remains_unmodified():
    assert localize_current_report_copy_v98('An unregistered sentence.') == 'An unregistered sentence.'


def test_review_required_identifier_remains_exact_with_its_display_label():
    line = localize_current_report_copy_v98(summary('review_required'))
    assert 'review_required (revisión requerida)' in line
    assert 'raw finding payload' not in line


@pytest.mark.parametrize('state', ['not applicable', 'not assessed', 'execution completed', 'not_assessed'])
def test_existing_multiword_and_underscore_aliases_remain_supported(state):
    line = localize_current_report_copy_v98(summary(state))
    assert '; commit exacto=sí; artefacto=conservado;' in line
    assert '; carga de hallazgos sin procesar incluida=no.' in line
