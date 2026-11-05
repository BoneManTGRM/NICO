from copy import deepcopy

import pytest

from nico.comprehensive_report_review_integrity_v1 import _client_summary_truth_evidence
from nico.comprehensive_finding_roadmap_v1 import _roadmap_presentation


def triage(completed=1407, pending=0):
    return {'status': 'complete', 'workload_metrics': {
        'technical_triage_completed': completed, 'technical_triage_pending': pending}}


def canonical():
    return {'identity': {'commit_sha': 'a'*40}, 'assessment': {},
            'review_candidate_summary': {'raw_total': 1407, 'review_required_total': 1407},
            'technical_triage': triage(0, 1407),
            'stage_summaries': [{'technical_triage': triage(0, 1407)}],
            'human_review_required': True, 'client_delivery_allowed': False}


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('owner', ['canonical', 'assessment'])
def test_final_register_overrides_stale_stage_and_preserves_human_pending(spanish, owner):
    value = canonical()
    target = value if owner == 'canonical' else value['assessment']
    target['canonical_scanner_finding_register'] = {'technical_triage': triage()}
    before = deepcopy(value)
    lines = _client_summary_truth_evidence(value, spanish=spanish, technical_text="90/100", adjusted_text="82/100")
    assert ('Estado del triaje técnico: completado; completados=1407; pendientes=0' if spanish
            else 'Technical-triage status: complete; completed=1407; pending=0') in lines
    assert any(('disposiciones canónicas pendientes=1407' if spanish else 'canonical dispositions pending=1407') in line for line in lines)
    assert value == before


@pytest.mark.parametrize('spanish', [False, True])
def test_partial_final_triage_never_borrows_human_pending(spanish):
    value = canonical()
    value['canonical_scanner_finding_register'] = {'technical_triage': {
        'status': 'review_required', 'workload_metrics': {'technical_triage_completed': 12}}}
    before = deepcopy(value)
    lines = _client_summary_truth_evidence(value, spanish=spanish, technical_text="90/100", adjusted_text="82/100")
    assert any(('completados=12; pendientes=no suministrado' if spanish else 'completed=12; pending=not supplied') in line for line in lines)
    assert value == before


@pytest.mark.parametrize('spanish', [False, True])
def test_missing_technical_triage_does_not_relabel_human_dispositions(spanish):
    value = canonical(); value.pop('technical_triage'); value['stage_summaries'] = []
    lines = _client_summary_truth_evidence(value, spanish=spanish, technical_text="90/100", adjusted_text="82/100")
    assert any(('completados=no suministrado; pendientes=no suministrado' if spanish else
                'completed=not supplied; pending=not supplied') in line for line in lines)


@pytest.mark.parametrize('spanish', [False, True])
def test_executive_work_package_list_is_explicit_bounded_summary(spanish):
    packages = [{'package_id': 'work-package-'+str(index).zfill(32), 'finding_id': f'F-{index}',
                 'action': '', 'verification': '', 'suggested_role_type': 'cybersecurity_specialist',
                 'dependencies': []} for index in range(49)]
    before = deepcopy(packages)
    result = _roadmap_presentation(packages, spanish)
    line = result['executive'][0]
    assert ('resumen' if spanish else 'summary') in line
    assert '7/49' in line
    assert len(line) < 900 and '...' not in line
    assert all(item['package_id'] in '\n'.join(result['roadmap']) for item in packages)
    assert packages == before


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('count', [None, 'invalid', False, -1, 1.5, 0])
def test_unavailable_counts_do_not_become_zero_but_numeric_zero_is_preserved(spanish, count):
    value = canonical()
    value['canonical_scanner_finding_register'] = {'technical_triage': triage(count, count)}
    lines = _client_summary_truth_evidence(value, spanish=spanish, technical_text='90/100', adjusted_text='82/100')
    expected = '0' if type(count) is int and count == 0 else 'no suministrado' if spanish else 'not supplied'
    assert any((f'completados={expected}; pendientes={expected}' if spanish else
                f'completed={expected}; pending={expected}') in line for line in lines)


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('prior_spanish', [False, True])
def test_retained_legacy_package_line_is_reprojected_exactly_without_client_prose_changes(spanish, prior_spanish):
    from nico.comprehensive_finding_roadmap_v1 import bind_final_finding_roadmap, localize_retained_roadmap
    from tests.test_comprehensive_finding_roadmap_v1 import _canonical
    value = bind_final_finding_roadmap(_canonical(), raw_stages={})
    packages = deepcopy(value['roadmap'])
    legacy = ('Paquetes de trabajo propuestos' if prior_spanish else 'Proposed work packages')+': '+', '.join(item['package_id'] for item in packages)
    custom = legacy+' — client-owned additional planning prose.'
    value['stage_summaries'].append({'stage_id': 'risk_reduction_and_executive_briefing', 'evidence': [legacy, custom]})
    before = deepcopy(value)
    result = localize_retained_roadmap(value, spanish=spanish)
    lines = result['stage_summaries'][-1]['evidence']
    assert ('Paquetes de trabajo propuestos (resumen)' if spanish else 'Proposed work packages (summary)') in lines[0]
    assert lines[1] == custom
    assert value == before
    assert [item['package_id'] for item in result['roadmap']] == [item['package_id'] for item in packages]
