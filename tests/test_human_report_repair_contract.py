"""Behavior at the final-publication boundary, not the legacy report builder."""
import io
from copy import deepcopy

import pytest
from pypdf import PdfReader
from reportlab.pdfgen import canvas

from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
from nico.comprehensive_client_review_companion_v2 import review_sections
from nico.comprehensive_operator_presentation_v1 import _render_source
from nico.comprehensive_report_content_render_v66 import _ci_operational_stage
from nico.comprehensive_report_package import _stage_summary
from nico import v2_premium_report_renderer as renderer
from nico.strategic_human_evidence_v1 import normalize_strategic_human_evidence
from tests.test_comprehensive_human_evidence_report_v1 import _context


def test_actual_canonical_source_retains_exact_modules_and_provenance():
    context = _context()
    context['prior_stage_results'] = {'authorization_and_scope': {
        'status': 'complete', 'authorization_confirmed': True,
    }}
    original = deepcopy(context)
    result = build_canonical_report_source(context)
    assert result['status'] == 'complete'
    canonical = result['canonical_report']
    assert canonical['supplied_human_evidence'] == context['human_evidence']
    stages = renderer._canonical_stages(canonical)
    for module_id, module in context['human_evidence']['modules'].items():
        section = '\n'.join(line for s in stages
                            if s['stage_id'].startswith('client_human_evidence_' + module_id)
                            for line in s['evidence'])
        for field in ('reviewer', 'observed_at', 'source_reference'):
            assert module[field] in section
        for values in module['evidence'].values():
            for value in values:
                assert value in section or value in str(canonical['identity'])
        assert 'supplied_unverified' in section
    assert context == original


@pytest.mark.parametrize('value, expected', [(0, '0'), (None, 'Unavailable'), (False, 'Unavailable')])
def test_metric_absence_is_distinct_from_measured_zero(value, expected):
    stage = _ci_operational_stage({'ci_operational_context': {'successful_runs': value}}, renderer)
    assert f'Successful workflow runs: {expected}.' in stage['evidence']
    assert all(': .' not in line for line in stage['evidence'])


def test_roadmap_companion_formats_records_with_stable_references():
    from nico.comprehensive_client_review_companion_v5 import _values
    records = [{
        'finding_id': 'TEST-F-1', 'title': 'Review authorization handling',
        'finding_aliases': ['TEST-LEGACY-F-1'],
        'location': 'src/auth.py:10', 'column': None,
        'recommendation': 'Check the retained access-control evidence.',
    }]
    text = '\n'.join(_values(records))
    assert 'TEST-F-1' in text and 'Review authorization handling' in text
    assert 'src/auth.py:10' in text
    assert 'TEST-LEGACY-F-1' in text
    assert 'TEST-LEGACY-F-1' in '\n'.join(_values([{'window': 'Month 1', 'work_packages': records}]))
    assert "{'" not in text and 'None' not in text and '...' not in text


def test_finished_processing_does_not_claim_assessment_coverage():
    dimensions = {'execution_status': 'complete', 'substantive_coverage': 'not_assessed',
                  'human_review_status': 'required', 'full_coverage_claim': False}
    result = _stage_summary('requirements_traceability', {
        'status': 'complete', 'assessment_dimensions': dimensions,
        'summary': 'Not assessed: requirements were not supplied.',
    })
    assert result['status'] == 'not_assessed'
    assert result['assessment_dimensions'] == dimensions


def test_tampered_module_payload_cannot_be_exported_as_retained_evidence():
    context = _context()
    context['human_evidence']['modules']['functional_qa']['reviewer'] = 'tampered'
    context['prior_stage_results'] = {'authorization_and_scope': {'status': 'complete'}}
    canonical = build_canonical_report_source(context)['canonical_report']
    assert canonical['supplied_human_evidence'] == {}
    assert 'tampered' not in str(canonical)


def test_long_multiline_input_is_exact_or_explicitly_rejected():
    value = '  TEST long\n<script>not executable</script>\n' + ('line of evidence\n' * 180) + '  END  '
    package = normalize_strategic_human_evidence({'functional_qa': {'evidence': {'test_cases': [value]}}})
    assert package['modules']['functional_qa']['evidence']['test_cases'] == [value]
    with pytest.raises(ValueError, match='exceeds_4000'):
        normalize_strategic_human_evidence({'functional_qa': {'evidence': {'test_cases': ['x' * 4001]}}})


def test_operator_formats_preserve_supplied_values_and_unfinished_review():
    from nico.comprehensive_operator_report_formats import project_operator_report_formats
    # A small legitimate review-truth projection, not a fabricated approval record.
    truth = {'authorized_human_disposition_pending': 2, 'final_human_approval_status': 'pending',
             'client_delivery_authorization_status': 'blocked', 'client_delivery_allowed': False}
    literal = {'evidence': {'text': 'Final human approval: PENDING; Client-delivery authorization: BLOCKED'}}
    reports = {'json': {'human_report_export_schema': 'nico.human_report_export.v1',
                       'supplied_human_evidence': literal, 'human_review_truth': truth,
                       'human_review_completed': False},
               'markdown': '<!-- NICO_PHASE2_REVIEW_TRUTH_START -->\nFinal human approval: PENDING\nClient-delivery authorization: BLOCKED\n<!-- NICO_PHASE2_REVIEW_TRUTH_END -->',
               'html': ''}
    original = deepcopy(literal)
    project_operator_report_formats(reports, authorized=True)
    assert reports['json']['supplied_human_evidence'] == original
    assert reports['json']['human_review_completed'] is False
    assert reports['json']['human_review_truth']['authorized_human_disposition_pending'] == 2
    assert 'PENDING' not in reports['markdown'] and 'BLOCKED' not in reports['markdown']


@pytest.mark.parametrize('spanish', [False, True])
def test_readable_literal_html_and_authorized_banners(spanish):
    from nico.client_ready_html_v1 import render_client_html
    from nico.comprehensive_engagement_metadata_v1 import markdown_literal_markup
    from nico.comprehensive_client_ready_projection_v1 import EN_BOUNDARY, ES_BOUNDARY
    from nico.comprehensive_operator_report_formats import project_operator_report_formats
    boundary = ES_BOUNDARY if spanish else EN_BOUNDARY
    literal = 'CLIENT DELIVERY BLOCKED <script>alert(1)</script>\nSecond supplied line'
    markup = markdown_literal_markup(literal, 4000)
    md = '**' + boundary + '**\n- ' + markup
    rendered = render_client_html(md, 'Synthetic fixture', spanish=spanish)
    assert markup in rendered
    assert '<script>' not in rendered
    reports = {'json': {'human_report_export_schema': 'nico.human_report_export.v1'},
               'markdown': md, 'html': rendered}
    project_operator_report_formats(reports, authorized=True)
    for key in ('markdown', 'html'):
        assert markup in reports[key]
        assert boundary not in reports[key]


def test_evidence_csv_has_typed_module_rows_and_exact_source_mapping():
    import csv, json
    from nico.comprehensive_artifact_manifest_approval_v1 import _build_structured_exports
    package = _context()['human_evidence']
    exports = _build_structured_exports({'supplied_human_evidence': package})
    rows = list(csv.DictReader(io.StringIO(exports['evidence_csv'].decode())))
    assert len(rows) == 10
    for row in rows:
        module = package['modules'][row['module_id']]
        assert row['record_type'] == 'supplied_human_evidence'
        assert row['canonical_pointer'] == '/supplied_human_evidence/modules/' + row['module_id']
        assert json.loads(row['evidence']) == module['evidence']
        assert row['evidence_digest_sha256'] == module['module_sha256']
        assert row['supplier_identity'] == module['reviewer']
        assert row['observation_time'] == module['observed_at']
        assert row['source_reference'] == module['source_reference']
        assert row['evidence_status'] == 'supplied_unverified'


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_full_finalizer_keeps_modules_in_all_applicable_exports(language):
    import base64, csv, html, json
    from tests.test_phase9_comprehensive_report_integration_v1 import _result
    from nico.phase9_comprehensive_report_integration_v1 import finalize_report_package
    context = _context(language)
    from tests.test_comprehensive_human_evidence_report_v1 import _human_input
    inputs = _human_input()
    inputs['functional_qa']['evidence']['test_cases'].append(
        'TEST-LONG-START\nQuoted source: AUTOMATED FINAL; artifact_schema; stage_execution.\n' + '\n'.join(f'Observation {i}: synthetic and unverified.' for i in range(70)) + '\nTEST-LONG-END')
    context['human_evidence'] = normalize_strategic_human_evidence(inputs)
    context['prior_stage_results'] = {'authorization_and_scope': {'status': 'complete', 'authorization_confirmed': True}}
    canonical = build_canonical_report_source(context)['canonical_report']
    fixture = _result()
    target = fixture['report_package']['json']
    for key in ('human_report_export_schema', 'supplied_human_evidence', 'engagement_metadata',
                'stage_summaries', 'report_language', 'locale'):
        target[key] = canonical[key]
    for key in ('customer_name', 'project_name', 'primary_technical_contact', 'access_method',
                'authorized_scope', 'report_language'):
        target['identity'][key] = canonical['identity'][key]
    report = finalize_report_package(fixture)['report_package']
    assert report['json']['supplied_human_evidence'] == context['human_evidence']
    assert json.loads(report['canonical_json'])['supplied_human_evidence'] == context['human_evidence']
    pdf = base64.b64decode(report['pdf_base64'])
    text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(pdf)).pages)
    import re
    # Join flowed evidence across physical page headers/footers, retaining all
    # substantive text and order for the full-value comparison.
    evidence_text = re.sub(r'(?m)^(?:Document page \d+ of \d+|Página del documento \d+ de \d+|Supplied Human Evidence \| supplied_unverified|Evidencia humana aportada \| supplied_unverified)\s*$', '', text)
    rows = list(csv.DictReader(io.StringIO(report['evidence_csv'])))
    human_rows = {row['module_id']: row for row in rows if row.get('record_type') == 'supplied_human_evidence'}
    for module_id, module in context['human_evidence']['modules'].items():
        assert json.loads(human_rows[module_id]['evidence']) == module['evidence']
        for field in ('reviewer', 'observed_at', 'source_reference'):
            for surface in (text, html.unescape(report['markdown']), html.unescape(report['html'])):
                assert module[field] in surface
        for values in module['evidence'].values():
            for value in values:
                assert ' '.join(value.split()) in ' '.join(evidence_text.split())
    revised, changes = _render_source(pdf, client_delivery_authorized=True, repair_current_truth=True)
    revised_text = '\n'.join(page.extract_text() for page in PdfReader(io.BytesIO(revised)).pages)
    for module_id in context['human_evidence']['modules']:
        assert 'reviewer::' + module_id in revised_text


@pytest.mark.parametrize('authorized', [False, True])
def test_approval_appendix_updates_only_lifecycle_cells(authorized):
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer)
    for i, line in enumerate(['Supplied Human Evidence | supplied_unverified',
                             'Human Review and Approval Truth',
                             'Final human approval', 'PENDING',
                             'Client-delivery authorization', 'BLOCKED',
                             'Authorized human disposition pending', '626',
                             'Quality control', '0/9']):
        pdf.drawString(40, 750-i*25, line)
    pdf.save()
    revised, _ = _render_source(buffer.getvalue(), client_delivery_authorized=authorized, repair_current_truth=True)
    text = PdfReader(io.BytesIO(revised)).pages[0].extract_text()
    assert 'Final human approval\nAPPROVED' in text
    assert 'Client-delivery authorization\n' + ('AUTHORIZED' if authorized else 'BLOCKED') in text
    assert 'Authorized human disposition pending\n626' in text
    assert 'Quality control\n0/9' in text


def test_new_source_lifecycle_preserves_reviewed_bytes_and_validates_fresh_state(tmp_path):
    import base64, hashlib, sqlite3
    from tests.test_comprehensive_operator_approval_v1 import fixture_record, payload
    from nico.comprehensive_operator_approval_v1 import approve_operator_report, presented_operator_identity
    from nico.comprehensive_operator_delivery_v1 import authorize_operator_delivery, validated_operator_delivery
    from nico.comprehensive_review_decision_v1 import report_package_from_record
    from nico.comprehensive_run_record import _record_hash
    from nico.comprehensive_run_service import ComprehensiveRunService
    from nico.comprehensive_run_store import ComprehensiveRunStore
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    record = deepcopy(fixture_record())
    canonical = report_package_from_record(record)['json']
    canonical['human_report_export_schema'] = 'nico.human_report_export.v1'
    canonical['supplied_human_evidence'] = _context()['human_evidence']
    record['stage_results']['final_comprehensive_report_generation']['report_package'] = rebuild_client_artifacts({'json': canonical})
    record['integrity_sha256'] = _record_hash(record)
    store = ComprehensiveRunStore(lambda: sqlite3.connect(tmp_path / 'new-source.db'), dialect='sqlite')
    store.ensure_schema(); store.create(record)
    service = ComprehensiveRunService(store, {})
    run = record['identity']['run_id']
    original = deepcopy(report_package_from_record(record))
    approved = approve_operator_report(service, run, payload(record))
    assert approved['client_delivery_allowed'] is False
    request = dict(delivery_kind='operator_report', delivery_authorized=True, authorization_confirmed=True,
                   expected_artifact_identity=presented_operator_identity(approved, approved['operator_approved_edition']))
    authorized = authorize_operator_delivery(service, run, request)
    fresh = service.load_read_only(run)
    edition = validated_operator_delivery(fresh)
    assert edition is not None and fresh['client_delivery_allowed'] is True
    assert fresh['human_review_completed'] is False
    assert report_package_from_record(fresh) == original
    for key in ('markdown', 'html'):
        assert 'CLIENT DELIVERY BLOCKED' not in edition['reports'][key]
    assert edition['reports']['json']['supplied_human_evidence'] == canonical['supplied_human_evidence']
    assert edition['reports']['json']['report_lifecycle']['transmission_performed'] is False
    pdf = base64.b64decode(edition['reports']['pdf_base64'])
    assert hashlib.sha256(pdf).hexdigest() == edition['artifact_digests']['pdf']['sha256']
    assert authorized['revision'] == approved['revision'] + 1
