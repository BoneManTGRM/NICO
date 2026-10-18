from copy import deepcopy
import io
import pytest
from pypdf import PdfReader
from nico import comprehensive_release_provenance_v1 as provenance
from nico import comprehensive_client_ready_projection_v1 as compact


def pdf_text(data):
    return '\n'.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(data)).pages)


def register():
    return {'code_findings': [{'finding_id': 'NICO-FINDING-ABC123', 'title': 'Reduce complexity in render',
        'location': 'src/report.py:138', 'priority': 'P1', 'verification': [
        'The exact-SHA rerun no longer reports the condition.',
        'Targeted characterization tests pass on the remediation commit.',
        "The repository's complete required-check suite passes on the remediation commit.",
        'No new material regression or cross-format report-truth mismatch is introduced.'],
        'acceptance_criteria': ['The required-check suite passes.']}]}


@pytest.mark.parametrize('scope', ['report_generation_runtime; assessed repository identity is separate', None])
def test_provenance_scope_is_local_and_preserves_state(scope):
    source = {'frontend_backend_source_alignment': 'aligned', 'exact_release_readiness': 'verified'}
    if scope:
        source['release_identity_scope'] = scope
    before = deepcopy(source)
    rows = dict(provenance._provenance_lines(source))
    assert rows['Report-generation runtime identity readiness' if scope else 'Recorded readiness status (scope unknown)'] == 'verified'
    assert rows['Readiness scope'] == ('Report-generation runtime only' if scope else 'unknown')
    assert 'This provenance alone' in rows['Readiness interpretation']
    assert source == before


def test_complete_distinct_acceptance_and_verification():
    source = register(); before = deepcopy(source)
    markdown = compact.compact_finding_register_markdown(source, spanish=False)
    text = pdf_text(compact.render_compact_finding_register_pdf(source, spanish=False))
    for criterion in source['code_findings'][0]['verification'] + source['code_findings'][0]['acceptance_criteria']:
        assert criterion in markdown
        assert criterion in ' '.join(text.split())
    assert source == before


def test_long_criteria_never_clip():
    source = register()
    criterion = 'Retained condition. ' * 500 + 'FINAL_REQUIRED_CONDITION'
    source['code_findings'][0]['verification'] = [criterion]
    markdown = compact.compact_finding_register_markdown(source, spanish=False)
    text = pdf_text(compact.render_compact_finding_register_pdf(source, spanish=False))
    assert criterion in markdown
    assert 'FINAL_REQUIRED_CONDITION' in text
    assert text.count('Retained condition.') == 500
    assert compact.MAX_CLIENT_PDF_PAGES == 60


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('total', [0, 1, 7, 17, 56])
def test_roadmap_labels_count_actual_packages_and_partial_rows(spanish, total):
    from nico.report_preview_labels_v1 import stage_preview_labels
    packages = [{'package_id': f'NICO-WORK-{i:016X}'} for i in range(total)]
    evidence = [item['package_id'] + ' | detail ' + str(j) for item in packages for j in range(6)]
    stage = {'stage_id': 'six_month_roadmap', 'evidence': evidence}
    context = {'roadmap': packages}; before = deepcopy((stage, context))
    label = stage_preview_labels(stage, context, evidence_limit=100, spanish=spanish)[0]
    count = min(total, 17)
    assert (f'{count} de {total}' if spanish else f'{count} of {total}') in label
    assert ('parcialmente' if spanish else 'partially') in label if total > 16 else ('parcialmente' if spanish else 'partially') not in label
    full = stage_preview_labels(stage, context, spanish=spanish)[0]
    assert (f'{total} de {total}' if spanish else f'{total} of {total}') in full
    assert (stage, context) == before


@pytest.mark.parametrize('total', [0, 49, 50, 51, 100, 101, 1536])
@pytest.mark.parametrize('spanish', [False, True])
def test_candidate_counts_use_retained_records_and_actual_format_limit(total, spanish):
    from nico.report_preview_labels_v1 import stage_preview_labels
    source = {'review_candidate_register': [{'candidate_id': str(i)} for i in range(total)] + [None],
              'review_candidate_summary': {'raw_total': 9999}}
    stage = {'stage_id': 'review_required_candidate_register', 'findings': [f'candidate-{i}' for i in range(min(total, 100))]}
    before = deepcopy((source, stage))
    for limit in (12, 50, None):
        shown = min(total, limit or 100)
        label = stage_preview_labels(stage, source, findings_limit=limit, spanish=spanish)[0]
        assert (f'{shown} de {total}' if spanish else f'{shown} of {total}') in label
        assert '9999' not in label
    assert (source, stage) == before


def preview_fixture():
    from nico.comprehensive_finding_roadmap_v1 import _roadmap_presentation
    packages = [{'package_id': f'NICO-WORK-{i:016X}', 'finding_id': f'NICO-FINDING-{i}',
        'action': 'Review finding', 'retained_correction': 'Check code', 'retained_rationale': 'Retained evidence',
        'verification': 'Verify outcome', 'retained_verification': 'Run required checks',
        'suggested_role_type': 'architecture_engineering', 'dependencies': []} for i in range(56)]
    roadmap = {'stage_id': 'six_month_roadmap', 'title': 'Six-Month Roadmap', 'summary': 'Review required', 'status': 'review_required',
               'evidence': _roadmap_presentation(packages, False)['roadmap'], 'findings': [], 'unavailable': []}
    candidates = {'stage_id': 'review_required_candidate_register', 'title': 'Candidate Register', 'summary': 'Review required',
                  'status': 'review_required', 'evidence': [], 'findings': [f'candidate-{i}' for i in range(100)], 'unavailable': []}
    assessment = {'roadmap': packages, 'review_candidate_register': [{'candidate_id': str(i)} for i in range(1536)]}
    identity = {'repository': 'fixture/repository', 'commit_sha': 'a'*40, 'run_id': 'fixture-preview', 'project_id': 'fixture', 'tenant_id': 'fixture'}
    return identity, assessment, [roadmap, candidates]


def test_preview_labels_in_pdf_markdown_and_html():
    import base64
    from nico.comprehensive_report_package import _pdf, _markdown, _semantic_html
    identity, assessment, stages = preview_fixture(); before = deepcopy((identity, assessment, stages))
    md = _markdown(identity, assessment, stages, '2026-10-17T00:00:00Z')
    assert '56 of 56 work packages' in md
    assert 'candidate-99' in md
    assert '100 of 1536 retained records' in md
    assert '100 of 1536 retained records' in _semantic_html(md, 'Fixture')
    encoded, error, _ = _pdf(identity, assessment, stages, '2026-10-17T00:00:00Z')
    assert not error
    text = ' '.join(pdf_text(base64.b64decode(encoded)).split())
    assert '17 of 56 work packages' in text
    assert 'Some packages are partially shown.' in text
    assert '50 of 1536 retained records' in text
    assert (identity, assessment, stages) == before


@pytest.mark.parametrize('spanish', [False, True])
def test_long_localized_conditions_preserved_in_all_register_formats(spanish):
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    from nico.client_ready_html_v1 import render_client_html
    install_spanish_publication_preflight_v93()
    source = register()
    sentence = 'Condición conservada para revisión. ' if spanish else 'Retained condition for review. '
    criterion = sentence * 350 + 'FINAL_REQUIRED_CONDITION'
    source['code_findings'][0]['verification'] = [criterion]
    source['code_findings'][0]['acceptance_criteria'] = [criterion]
    before = deepcopy(source)
    md = compact.compact_finding_register_markdown(source, spanish=spanish)
    assert md.count('FINAL_REQUIRED_CONDITION') == 1
    assert criterion in md
    rendered = render_client_html(md, 'Fixture', spanish=spanish)
    assert 'FINAL_REQUIRED_CONDITION' in rendered
    text = pdf_text(compact.render_compact_finding_register_pdf(source, spanish=spanish))
    assert text.count(sentence.split()[0]) == 350
    assert 'FINAL_REQUIRED_CONDITION' in text
    assert source == before


@pytest.mark.parametrize('spanish', [False, True])
def test_executive_preview_is_explicit_and_does_not_change_producer(spanish):
    from nico.report_preview_labels_v1 import stage_preview_labels
    from nico.comprehensive_finding_roadmap_v1 import _roadmap_presentation
    _, assessment, _ = preview_fixture()
    stage = {'stage_id': 'risk_reduction_and_executive_briefing', 'evidence': _roadmap_presentation(assessment['roadmap'], False)['executive']}
    before = deepcopy(stage)
    label = stage_preview_labels(stage, assessment, spanish=spanish)[0]
    assert ('7 de 56' if spanish else '7 of 56') in label
    assert ('identificadores' if spanish else 'ID preview') in label
    assert stage == before


def test_spanish_formats_label_all_available_rows():
    from nico.comprehensive_report_spanish_artifacts_v51 import _spanish_pdf
    from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown
    identity, assessment, stages = preview_fixture()
    canonical = {'identity': identity, 'assessment': assessment, 'stage_summaries': stages, **assessment}
    before = deepcopy(canonical)
    markdown = _spanish_markdown(canonical)
    data, _ = _spanish_pdf(canonical)
    text = ' '.join(pdf_text(data).split())
    for output in (markdown, text):
        assert '56 de 56 paquetes' in output
        assert '100 de 1536 registros' in output
        assert '50 de 1536' not in output
    assert canonical == before


@pytest.mark.parametrize('status', ['verified', 'blocked', 'unverified'])
@pytest.mark.parametrize('scope', [None, 'different_scope', 'report_generation_runtime; assessed repository identity is separate'])
def test_readiness_never_infers_unrecorded_scope_or_changes_status(status, scope):
    source = {'frontend_backend_source_alignment': 'aligned', 'exact_release_readiness': status, 'release_identity_scope': scope}
    rows = dict(provenance._provenance_lines(source))
    assert rows['Report-generation runtime identity readiness' if scope and scope.startswith('report_generation_runtime;') else 'Recorded readiness status (scope unknown)'] == status
    assert rows['Readiness scope'] == ('Report-generation runtime only' if scope and scope.startswith('report_generation_runtime;') else 'unknown')
    localize = provenance._presentation_localizer(lambda value: 'Procedencia de la versión de NICO' if value == 'NICO Release Provenance' else value)
    assert localize('Readiness scope') == 'Alcance del estado de preparación'
    assert localize(rows['Readiness interpretation']) != rows['Readiness interpretation']
    assert 'assessed repository is not ready' not in rows['Readiness interpretation']


def test_exit_criteria_and_empty_missing_preview_populations():
    from nico.report_preview_labels_v1 import stage_preview_labels
    source = register()
    source['code_findings'][0]['exit_criteria'] = ['Final independent acceptance remains required.']
    md = compact.compact_finding_register_markdown(source, spanish=False)
    text = ' '.join(pdf_text(compact.render_compact_finding_register_pdf(source, spanish=False)).split())
    assert 'Final independent acceptance remains required.' in md
    assert 'Final independent acceptance remains required.' in text
    stage = {'stage_id': 'review_required_candidate_register', 'findings': ['one', 'two']}
    assert '2 of unknown' in stage_preview_labels(stage, {})[0]
    context = {'review_candidate_register': [{'candidate_id': 'same'}, {'candidate_id': 'same'}, None]}
    stage['findings'] = ['one retained rendered row']
    assert '1 of 2' in stage_preview_labels(stage, context)[0]


def test_roadmap_variable_lines_and_hidden_executive_preview():
    from nico.report_preview_labels_v1 import stage_preview_labels
    context = {'roadmap': [{'package_id': 'first'}, {'package_id': 'second'}]}
    stage = {'stage_id': 'six_month_roadmap', 'evidence': ['first | a', 'second | a', 'second | b']}
    assert 'partially' in stage_preview_labels(stage, context, evidence_limit=2)[0]
    assert 'partially' not in stage_preview_labels(stage, context)[0]
    stage = {'stage_id': 'risk_reduction_and_executive_briefing', 'evidence': ['Other retained evidence', 'Proposed work packages (summary) (1/2): first']}
    assert stage_preview_labels(stage, context, evidence_limit=1) == []
    assert '1 of 2' in stage_preview_labels(stage, context)[0]


def test_spanish_complete_generated_conditions_preserve_threshold_and_suite():
    from nico.comprehensive_decision_content_restoration_v66 import _synthesized_complexity_findings
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    install_spanish_publication_preflight_v93()
    source = {'code_findings': _synthesized_complexity_findings([{'path':'src/report.py','line':138,'name':'render','cyclomatic_complexity':40}], 'a'*40)}
    before = deepcopy(source)
    md = compact.compact_finding_register_markdown(source, spanish=True)
    text = ' '.join(pdf_text(compact.render_compact_finding_register_pdf(source, spanish=True)).split())
    for value in ('igual o superior a 30', 'conjunto completo de verificaciones requeridas', 'regresión material', 'entre formatos'):
        assert value in md
        assert value in text
    assert source == before


def test_page_cap_still_rejects_overflow_without_dropping_conditions():
    from pypdf import PdfWriter
    def blank_pdf(count):
        writer = PdfWriter()
        for _ in range(count):
            writer.add_blank_page(width=612, height=792)
        result = io.BytesIO(); writer.write(result); return result.getvalue()
    with pytest.raises(ValueError, match='exceeds the 60-page boundary'):
        compact.compose_compact_client_pdf(blank_pdf(59), blank_pdf(1), blank_pdf(1))


def test_full_canonical_preview_context_is_read_only_and_authoritative():
    from nico.report_preview_labels_v1 import stage_preview_labels
    canonical = {'review_candidate_register': [{'candidate_id':str(i)} for i in range(75)]}
    context = {'_preview_context': canonical, 'review_candidate_summary': {'raw_total':999}}
    stage = {'stage_id':'review_required_candidate_register', 'findings':['one']}
    before = deepcopy((canonical, context, stage))
    assert '1 of 75' in stage_preview_labels(stage, context)[0]
    assert (canonical, context, stage) == before


def test_spanish_composite_exit_criterion_uses_its_original_field_contract():
    from nico.client_finding_remediation_register_v2 import _GENERIC_EXIT_CRITERION
    from nico.comprehensive_spanish_publication_preflight_v93 import install_spanish_publication_preflight_v93
    install_spanish_publication_preflight_v93()
    source = register()
    source['code_findings'][0]['verification'] = []
    source['code_findings'][0]['acceptance_criteria'] = []
    source['code_findings'][0]['exit_criteria'] = [_GENERIC_EXIT_CRITERION]
    before = deepcopy(source)
    for output in (compact.compact_finding_register_markdown(source, spanish=True),
                   pdf_text(compact.render_compact_finding_register_pdf(source, spanish=True))):
        assert 'riesgo material sin resolver' in ' '.join(output.split())
        assert 'regresión material' in ' '.join(output.split())
        assert 'All listed' not in output
    assert source == before


@pytest.mark.parametrize('format_name', ['en-pdf', 'es-localized-pdf', 'es-pdf', 'en-markdown', 'es-markdown'])
def test_long_roadmap_row_discloses_actual_format_truncation(format_name):
    import base64
    from nico.comprehensive_report_package import _pdf, _markdown
    from nico.comprehensive_report_spanish_artifacts_v51 import _spanish_pdf
    from nico.comprehensive_report_spanish_text_v51 import _spanish_markdown, _es
    identity, assessment, stages = preview_fixture()
    assessment['roadmap'] = assessment['roadmap'][:1]
    stage = stages[0]
    stage['evidence'] = [assessment['roadmap'][0]['package_id'] + ' | ' + 'Detalle conservado. ' * 80 + 'ROADMAP_REQUIRED_TAIL']
    stages = [stage]
    canonical = {'identity': identity, 'assessment': assessment, 'stage_summaries': stages, 'roadmap': assessment['roadmap']}
    before = deepcopy(canonical)
    if format_name in ('en-pdf', 'es-localized-pdf'):
        encoded, error, _ = _pdf(identity, assessment, stages, '2026-10-18T00:00:00Z',
                                localize_presentation=_es if format_name.startswith('es') else None)
        assert not error
        output = pdf_text(base64.b64decode(encoded))
    elif format_name == 'es-pdf':
        data, _ = _spanish_pdf(canonical)
        output = pdf_text(data)
    elif format_name == 'en-markdown':
        output = _markdown(identity, assessment, stages, '2026-10-18T00:00:00Z')
    else:
        output = _spanish_markdown(canonical)
    output = ' '.join(output.split())
    partial = 'Algunos paquetes se muestran parcialmente.' if format_name.startswith('es') else 'Some packages are partially shown.'
    assert ('1 de 1 paquetes' if format_name.startswith('es') else '1 of 1 work packages') in output
    if format_name in ('en-pdf', 'es-localized-pdf'):
        assert 'ROADMAP_REQUIRED_TAIL' not in output
        assert partial in output
    else:
        assert 'ROADMAP_REQUIRED_TAIL' in output
        assert partial not in output
    assert canonical == before
    assert compact.MAX_CLIENT_PDF_PAGES == 60


@pytest.mark.parametrize('length', [999, 1000, 1001])
def test_roadmap_text_limit_uses_normalized_length_and_only_shown_rows(length):
    from nico.report_preview_labels_v1 import stage_preview_labels
    prefix = 'NICO-WORK-0000000000000001 | '
    row = prefix + 'x' * (length - len(prefix))
    source = {'roadmap': [{'package_id': 'NICO-WORK-0000000000000001'}]}
    stage = {'stage_id': 'six_month_roadmap', 'evidence': [row]}
    label = stage_preview_labels(stage, source, evidence_text_limit=1000)[0]
    assert ('partially' in label) == (length > 1000)
    # Raw extra whitespace does not count as omitted substantive content.
    stage['evidence'] = [row.replace(' | ', '   |   ') + '   ']
    label = stage_preview_labels(stage, source, evidence_text_limit=1000)[0]
    assert ('partially' in label) == (length > 1000)
    assert 'partially' not in stage_preview_labels(stage, source, evidence_limit=0, evidence_text_limit=1000)[0]
