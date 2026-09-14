"""Evidence contracts for the six contradictions in authorized revision 67."""
from copy import deepcopy

import pytest

from nico.comprehensive_client_review_companion_v5 import substantive_review_sections
from nico.comprehensive_four_phase_model_v1 import build_four_phase_program
from tests.test_runtime_acceptance_report_truth_v1 import canonical_with_observations


@pytest.mark.parametrize('state', ['review_required', 'complete', 'completed'])
def test_run_completion_is_not_broader_specialist_completion(state):
    report = {'assessment_state': state, 'human_review_completed': False}
    phase = build_four_phase_program(report)['phases'][2]
    assert phase['status'] not in {'complete', 'complete_with_disclosed_limitations'}


@pytest.mark.parametrize('text', [
    'PASS', '0', 'Runtime behavior NOT VERIFIED',
    'Desktop mobile English es-MX NOT TESTED; no observation asserted.',
    'Synthetic PASS; quoted "verified" is not execution evidence.',
])
@pytest.mark.parametrize('spanish', [False, True])
def test_supplied_text_does_not_establish_observed_or_verified_execution(text, spanish):
    report = canonical_with_observations()
    report['stage_summaries'][2]['evidence'][0] = 'Client-supplied data · Observed results: ' + text
    report['stage_summaries'][3]['evidence'] = ['Client-supplied data · Matrix: ' + text]
    report['production_acceptance'] = {'status': 'verified', 'desktop': {'status': 'verified'}}
    original = deepcopy(report)
    sections = {s['id']: s for s in substantive_review_sections(report, spanish=spanish)}
    qa, parity = sections['functional_qa'], sections['platform_parity']
    assert qa['evidence_state'] == 'supplied_unverified'
    assert qa['runtime_observation_established'] is False
    assert parity['runtime_observation_established'] is False
    assert parity['independently_verified'] is False
    assert report == original


@pytest.mark.parametrize('value', ['Hypothetical one reviewer and two engineering days; no commitment.', 0])
def test_supplied_capacity_is_not_reported_absent(value):
    from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence
    report = {'supplied_human_evidence': normalize_strategic_human_evidence({
        'budget_staffing': {'evidence': {'constraints': [value]}}
    })}
    section = next(s for s in substantive_review_sections(report, spanish=False) if s['id'] == 'staffing_sequencing_and_cost')
    assert 'capacity' not in section['summary'].split('were not supplied')[0] or 'were not supplied' not in section['summary']
    assert section['resource_evidence_state'] == 'supplied_unverified'
    assert section['resource_commitment_established'] is False


def test_future_specialist_work_is_not_undone_operator_authorization():
    sections = substantive_review_sections({}, spanish=False)
    assert 'before authorizing client delivery' not in str(sections)


def test_current_authorization_projection_is_not_labelled_historical():
    from nico.comprehensive_operator_report_formats import project_operator_report_formats
    reports = {'json': {'human_report_export_schema': 'v1',
                       'report_truth_schema': 'nico.report_truth.v2',
                       'four_phase_program': {'phases': [{'id': 'approval_and_client_delivery',
                                                        'status': 'blocked_pending_authorized_human_approval'}]}}}
    project_operator_report_formats(reports, authorized=True)
    canonical = reports['json']
    assert canonical['four_phase_program']['phases'][0]['status'] == 'authorized'
    assert '/four_phase_program' not in canonical['reviewed_source_lifecycle']['historical_contract_paths']


def test_final_pdf_contents_distinguish_report_and_physical_numbering():
    import io
    from pypdf import PdfReader
    from nico.comprehensive_pdf_layout_polish_v1 import _render_polished_toc_pdf
    pdf = _render_polished_toc_pdf([{'title': 'Functional QA', 'source_page_index': 1}], total_pages=3, toc_page_count=1, spanish=False)
    text = PdfReader(io.BytesIO(pdf)).pages[0].extract_text()
    assert '3 report pages (certificate excluded)' in text
    assert 'physical pages' not in text


@pytest.mark.parametrize('field,value', [
    ('kind', 'synthetic'), ('performed', False), ('commit_sha', 'b' * 40),
    ('retained_results', []), ('evidence_reference', ''), ('observed_at', ''),
])
def test_execution_metadata_cannot_substitute_for_retained_exact_source_results(field, value):
    from nico.comprehensive_observation_truth import observation_truth
    from tests.test_runtime_acceptance_report_truth_v1 import with_retained_executions
    report = with_retained_executions(canonical_with_observations(), verified=True)
    report['retained_runtime_executions']['functional_qa'][field] = value
    assert observation_truth(report, 'functional_qa')['observed'] is False


def test_changed_execution_invalidates_review_but_preserves_actual_observation():
    from nico.comprehensive_observation_truth import observation_truth
    from tests.test_runtime_acceptance_report_truth_v1 import with_retained_executions
    report = with_retained_executions(canonical_with_observations(), verified=True)
    report['retained_runtime_executions']['functional_qa']['result'] = 'fail'
    result = observation_truth(report, 'functional_qa')
    assert result['observed'] is True and result['verified'] is False
    assert result['result'] == 'fail'


def test_verification_requires_an_identified_observer_for_independence():
    from hashlib import sha256
    import json
    from nico.comprehensive_observation_truth import observation_truth
    from tests.test_runtime_acceptance_report_truth_v1 import with_retained_executions
    report = with_retained_executions(canonical_with_observations(), verified=True)
    execution = report['retained_runtime_executions']['functional_qa']
    execution.pop('observer', None)
    review = report['production_acceptance']['functional_qa']['independent_review']
    review['execution_sha256'] = sha256(json.dumps(execution, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
    result = observation_truth(report, 'functional_qa')
    assert result['observed'] is True
    assert result['verified'] is False


def test_certificate_counts_composed_pages_and_keeps_bookmark_destination():
    import io
    from pypdf import PdfReader, PdfWriter
    from nico.comprehensive_certificate_pagination import annotate_composed_pagination
    writer = PdfWriter()
    for _ in range(4):
        writer.add_blank_page(width=612, height=792)
    writer.add_outline_item('Supplied Human Evidence', 3)
    annotate_composed_pagination(writer)
    output = io.BytesIO(); writer.write(output)
    reader = PdfReader(io.BytesIO(output.getvalue()))
    assert f'{len(reader.pages)} physical pages' in reader.pages[0].extract_text()
    assert 'add 1' in reader.pages[0].extract_text()
    assert reader.get_destination_page_number(reader.outline[0]) == 3


@pytest.mark.parametrize('spanish', [False, True])
def test_remediation_register_labels_criteria_as_future_unverified_work(spanish):
    import io
    from pypdf import PdfReader
    from nico.comprehensive_client_ready_projection_v1 import compact_finding_register_markdown, render_compact_finding_register_pdf
    register = {'code_findings': [{'finding_id': 'F-1', 'title': 'Reduce complexity in main',
                  'path': 'src/main.py', 'line': 1,
                  'verification': ['Targeted characterization tests pass on the remediation commit.']}]}
    md = compact_finding_register_markdown(register, spanish=spanish)
    assert ('resultado no verificado' if spanish else 'outcome not verified') in md
    pdf = render_compact_finding_register_pdf(register, spanish=spanish)
    text = '\n'.join(p.extract_text() for p in PdfReader(io.BytesIO(pdf)).pages)
    assert ('Resultado: no verificado' if spanish else 'Outcome: not verified') in text
