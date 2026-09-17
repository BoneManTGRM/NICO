"""R3 minimal unit controls: different populations and message/file availability."""
from copy import deepcopy
import pytest

from nico.comprehensive_coverage_reconciliation_v1 import (
    ACQUISITION_NOTE, ARCHITECTURE_DEFINITION, COPY_ES, POPULATION_NOTE,
    PROVIDER_ARCHITECTURE_DEFINITION, UNKNOWN_ARCHITECTURE,
    reconcile_report_coverage, coverage_reconciliation_table,
)
from nico.comprehensive_report_package import _source_tables, _source_markdown


def canonical(*, notes=None, paths=None, provider='GitHub'):
    profile = {'version': 'nico.repository_profile_coverage.v1', 'inventory_complete': True,
               'observed_source_files': 5, 'eligible_source_files': 3,
               'unavailable_item_notes': [ACQUISITION_NOTE] if notes is None else notes,
               'unavailable_paths': [] if paths is None else paths, 'unavailable_profile_files': 0}
    warning = f"{len(profile['unavailable_item_notes'])} captured-commit profile item(s) were unavailable; complexity coverage is limited to readable sampled files."
    stages=[{'stage_id':'architecture_and_data_flow','profile_coverage':profile,'unavailable':[warning]},
            {'stage_id':'repository_and_delivery_evidence','profile_coverage':deepcopy(profile),
             'evidence':[f'Provider: {provider}.'],'unavailable':[ACQUISITION_NOTE,'Genuine retained limit.']}]
    return {'identity':{'commit_sha':'a'*40},'report_finality':'automated_draft',
            'assessment':{'sections':[{'id':'architecture_debt','score':78,'evidence':['Source files: 2.']}],
                          'unavailable_data_notes':[ACQUISITION_NOTE,'Genuine retained limit.'], 'unavailable_note_count':2,
                          'stage_summaries':deepcopy(stages)},'stage_summaries':stages}


def test_successful_acquisition_is_not_an_unavailable_item_and_raw_records_survive():
    value=canonical(); before=deepcopy(value); result=reconcile_report_coverage(value)
    assert value==before
    stages=result['stage_summaries']; record=stages[0]['coverage_reconciliation']
    assert record['profile_note_entry_count']==1 and record['unavailable_file_path_count']==0
    assert stages[0]['unavailable']==[]
    assert stages[1]['unavailable']==['Genuine retained limit.']
    assert stages[0]['profile_coverage']==before['stage_summaries'][0]['profile_coverage']
    assert result['assessment']['sections'][0]['score']==78
    assert result['assessment']['sections'][0]['evidence']==['Architecture footprint source files: 2.',POPULATION_NOTE]
    assert result['assessment']['unavailable_note_count']==1
    assert result['assessment']['stage_summaries']==stages
    assert ACQUISITION_NOTE in str(coverage_reconciliation_table(stages[0]))


def test_duplicate_note_entries_are_not_deduplicated_file_paths():
    result=reconcile_report_coverage(canonical(notes=['File unavailable','File unavailable'], paths=['a.py','a.py']))
    stage=result['stage_summaries'][0]; record=stage['coverage_reconciliation']
    assert record['profile_note_entry_count']==2
    assert record['unavailable_file_path_count']==1
    assert stage['unavailable']  # No claim that an unknown failure message was informational.


def test_missing_availability_is_unknown_not_zero():
    value=canonical()
    for stage in value['stage_summaries']:
        stage['profile_coverage'].pop('unavailable_paths'); stage['profile_coverage'].pop('unavailable_item_notes')
    result=reconcile_report_coverage(value)['stage_summaries'][0]
    assert result['coverage_reconciliation']['unavailable_file_path_count'] is None
    assert result['coverage_reconciliation']['profile_note_entry_count'] is None
    assert result['unavailable']


def test_explicit_empty_availability_is_distinct_from_missing():
    result=reconcile_report_coverage(canonical(notes=[],paths=[]))['stage_summaries'][0]
    assert result['coverage_reconciliation']['unavailable_file_path_count']==0
    assert result['coverage_reconciliation']['profile_note_entry_count']==0


def test_conflicting_profile_records_do_not_silently_reconcile():
    value=canonical(); value['stage_summaries'][1]['profile_coverage']['unavailable_paths']=['b.py']
    result=reconcile_report_coverage(value)
    assert result['stage_summaries'][0]['unavailable']==value['stage_summaries'][0]['unavailable']
    assert result['stage_summaries'][0]['coverage_reconciliation']['profile_records_agree'] is False
    assert result['stage_summaries'][0]['coverage_reconciliation']['informational_acquisition_note'] is None


def test_stage_order_and_repeated_projection_are_stable():
    value=canonical(); result=reconcile_report_coverage(value)
    assert reconcile_report_coverage(result)==result
    value['stage_summaries'].reverse()
    reordered=reconcile_report_coverage(value)
    assert {s['stage_id']:s for s in result['stage_summaries']}=={s['stage_id']:s for s in reordered['stage_summaries']}


@pytest.mark.parametrize('provider,definition',[('GitLab',PROVIDER_ARCHITECTURE_DEFINITION),('Unknown',UNKNOWN_ARCHITECTURE)])
def test_provider_definition_is_not_assumed_to_be_github(provider,definition):
    result=reconcile_report_coverage(canonical(provider=provider))['stage_summaries'][0]
    assert result['coverage_reconciliation']['architecture_definition']==definition
    assert result['coverage_reconciliation']['informational_acquisition_note'] is None
    assert result['unavailable']


def test_approved_artifacts_are_not_reprojected():
    value=canonical(); value['client_delivery_allowed']=True
    assert reconcile_report_coverage(value)==value


def test_bilingual_tables_and_population_value_preservation():
    result=reconcile_report_coverage(canonical()); stage=result['stage_summaries'][0]
    tables=_source_tables(stage)
    coverage=tables[0]; assert ['Observed source files',5] in coverage['rows']; assert ['Eligible source files',3] in coverage['rows']
    assert result['assessment']['sections'][0]['evidence'][0]=='Architecture footprint source files: 2.'
    for spanish in (False,True):
        text='\n'.join(_source_markdown(stage,spanish=spanish))
        assert (COPY_ES[ARCHITECTURE_DEFINITION] if spanish else ARCHITECTURE_DEFINITION) in text
        assert ('Notas de adquisición inexistentes' not in text)
    from nico.comprehensive_spanish_canonical_report_v87 import _localize_tree
    assert _localize_tree(stage['coverage_reconciliation'],path=('coverage_reconciliation',))==stage['coverage_reconciliation']


def test_localized_provider_metadata_keeps_identical_coverage_attribution():
    from nico.comprehensive_same_run_locale_report_v1 import _localized_draft_view
    original = canonical()
    localized = _localized_draft_view(original, "es-MX")
    result = reconcile_report_coverage(localized)
    record = result["stage_summaries"][0]["coverage_reconciliation"]
    assert record["architecture_definition"] == ARCHITECTURE_DEFINITION
    assert record["informational_acquisition_note"] == ACQUISITION_NOTE
    assert result["stage_summaries"][0]["unavailable"] == []


def test_conflicting_availability_is_visibly_not_claimed_reconciled():
    value = canonical()
    value["stage_summaries"][1]["profile_coverage"]["unavailable_paths"] = ["b.py"]
    stage = reconcile_report_coverage(value)["stage_summaries"][0]
    text = "\n".join(_source_markdown(stage, spanish=False))
    assert "Profile availability records disagree; availability is not reconciled." in text


@pytest.mark.parametrize('missing', [False, True])
def test_existing_coverage_table_uses_retained_path_population_not_stale_zero(missing):
    value = canonical(paths=['a.py', 'a.py'])
    if missing:
        for stage in value['stage_summaries']:
            stage['profile_coverage'].pop('unavailable_paths')
    result = reconcile_report_coverage(value)
    table = next(t for t in _source_tables(result['stage_summaries'][0]) if t['title'] == 'Bounded profile coverage')
    assert dict(table['rows'])['Unavailable profile files'] == (None if missing else 1)
    assert result['stage_summaries'][0]['profile_coverage']['unavailable_profile_files'] == 0


def test_note_order_does_not_create_a_false_population_disagreement():
    value = canonical(notes=['First retained note', 'Second retained note'])
    value['stage_summaries'][1]['profile_coverage']['unavailable_item_notes'].reverse()
    result = reconcile_report_coverage(value)
    assert result['stage_summaries'][0]['coverage_reconciliation']['profile_records_agree'] is True
