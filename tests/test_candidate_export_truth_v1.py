from copy import deepcopy
import base64
import io

import pytest
from pypdf import PdfReader

from nico.report_preview_labels_v1 import stage_preview_labels
from nico.client_assessment_truth_v3 import _normalize_scanner_record
from nico.comprehensive_report_content_render_v66 import _scanner_count


@pytest.mark.parametrize('spanish', [False, True])
def test_complete_candidate_reference_uses_full_register_in_rendered_output(spanish):
    from nico.comprehensive_report_package import _pdf, _markdown
    assessment = {'canonical_scanner_finding_register': {'findings': [{'candidate_id': str(i)} for i in range(1675)]},
                  '_preview_context': {'review_candidate_register': [{}] * 250}}
    stage = {'stage_id': 'review_required_candidate_register', 'title': 'Candidate preview',
             'summary': 'Human review required', 'findings': ['candidate preview'] * 3, 'evidence': [], 'unavailable': [], 'status': 'review_required'}
    identity = {'run_id': 'synthetic', 'repository': 'example/repo', 'commit_sha': 'a' * 40}
    before = deepcopy(assessment)
    localize = (lambda text: text) if spanish else None
    md = _markdown(identity, assessment, [stage], '2026-10-28', localize_presentation=localize)
    pdf, error, _ = _pdf(identity, assessment, [stage], '2026-10-28', localize_presentation=localize)
    assert not error
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(pdf))).pages)
    for rendered in (md, text):
        assert '1675' in rendered
        assert 'assessment.canonical_scanner_finding_register.findings' in rendered
        assert 'Complete register: review_candidate_register' not in rendered
    assert assessment == before


def test_legacy_preview_does_not_claim_complete_population():
    labels = stage_preview_labels({'stage_id': 'review_required_candidate_register', 'findings': ['preview']}, {'review_candidate_register': [{}] * 250})
    assert 'Complete register: review_candidate_register' not in labels[0]
    assert 'unavailable' in labels[0]


@pytest.mark.parametrize('count', [0, 24, 1583, 11, 57])
def test_compact_empty_payload_preserves_retained_counts(count):
    record = {'scanner_name': 'bandit', 'compact_record': True, 'raw_findings_embedded': False,
              'findings': [], 'finding_count': 0, 'raw_finding_count': 0,
              'finding_summary': {'raw': count, 'review_required': count, 'material': 0}}
    before = deepcopy(record)
    normalized = _normalize_scanner_record(record)
    assert normalized['raw_finding_count'] == count
    assert normalized['finding_count'] == count
    assert normalized['client_actionable_finding_count'] is None
    assert _scanner_count(record, {})[0] == count
    assert record == before


@pytest.mark.parametrize('count', [None, -1, True, '24', []])
def test_missing_or_malformed_compact_count_never_becomes_verified_zero(count):
    normalized = _normalize_scanner_record({'scanner_name': 'bandit', 'compact_record': True,
        'raw_findings_embedded': False, 'findings': [], 'finding_summary': {'raw': count}})
    assert normalized['raw_finding_count'] is None
    assert _scanner_count(normalized, {})[0] is None


def test_embedded_findings_keep_existing_configuration_classification():
    record = {'scanner_name': 'bandit', 'findings': [{'title': 'source candidate'}]}
    normalized = _normalize_scanner_record(record)
    assert normalized['raw_finding_count'] == 1
    assert normalized['client_actionable_finding_count'] == 1


@pytest.mark.parametrize('spanish', [False, True])
def test_installed_stage_discloses_repeatability_without_execution_failure(spanish):
    from nico.comprehensive_report_content_render_v66 import install_comprehensive_report_content_render_v66
    from nico import v2_premium_report_renderer as renderer
    from nico.comprehensive_report_package import _pdf, _markdown
    install_comprehensive_report_content_render_v66()
    identity = {'run_id': 'synthetic', 'repository': 'example/repo', 'commit_sha': 'a' * 40}
    canonical = {'identity': identity, 'assessment': {}, 'scanner_execution_records': [
        {'scanner_name': 'bandit', 'completed': True, 'status': 'completed', 'finding_count': 0}],
        'analyzer_evidence_report': {'commit_sha': 'a' * 40, 'analyzers': [
            {'scanner': 'bandit', 'required': True, 'consecutive_successful_passes': 1,
             'consecutive_passes_required': 2, 'acceptance_ready': False}]}}
    before = deepcopy(canonical)
    stage = next(s for s in renderer._canonical_stages(canonical) if s['stage_id'] == 'dependency_security_static_analysis')
    assert stage['status'] == 'complete'
    localize = (lambda text: text) if spanish else None
    md = _markdown(identity, {}, [stage], '2026-10-28', localize_presentation=localize)
    pdf, error, _ = _pdf(identity, {}, [stage], '2026-10-28', localize_presentation=localize)
    assert not error
    text = ' '.join(p.extract_text() for p in PdfReader(io.BytesIO(base64.b64decode(pdf))).pages)
    for output in (md, text):
        assert '1/2' in output
        assert ('requisito no satisfecho' if spanish else 'requirement not met') in output
    assert canonical == before


def _installed_worker(language):
    from nico.api import final_report_worker_bootstrap
    from tests.test_roadmap_pdf_detail_completeness import _five_gap_package
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    package = _five_gap_package(language)
    c = package['json']
    full = [{'candidate_id': f'SYNTH-{i}', 'category': 'static', 'scanner': 'bandit', 'disposition': 'review_required', 'evidence_quality': 'exact_source', 'occurrence_count': 1} for i in range(1675)]
    totals = {'raw': 1675, 'review_required': 1675, 'material': 0, 'exact_source': 1675, 'source_path': 0, 'payload_without_source': 0, 'count_only': 0, 'approved_or_nonblocking': 0, 'excluded_test_only': 0}
    c['assessment']['canonical_scanner_finding_register'] = {'findings': full, 'candidate_record_count': len(full), 'totals': totals, 'summary_by_category': {'static': totals}, 'summary_by_tool': {'bandit': totals}}
    c['review_candidate_register'] = full[:250]
    c['review_candidate_summary'] = {'raw_total': 1675, 'review_required_total': 1675, 'verified_material_total': 0}
    c['scanner_execution_records'] = [{'scanner_name': 'bandit', 'scanner': 'bandit', 'completed': True, 'status': 'completed',
        'commit_sha': c['identity']['commit_sha'], 'artifact_sha256': 'b' * 64, 'capture_complete': True, 'run_sequence': 1,
        'compact_record': True, 'raw_findings_embedded': False, 'findings': [], 'finding_count': 0,
        'finding_summary': {'raw': 1675, 'material': 0, 'review_required': 1675}}]
    c['analyzer_evidence_report'] = {'commit_sha': c['identity']['commit_sha'], 'analyzers': [
        {'scanner': 'bandit', 'required': True, 'consecutive_successful_passes': 1,
         'consecutive_passes_required': 2, 'acceptance_ready': False}]}
    before = deepcopy(package)
    result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    text = ''.join(''.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    assert 'assessment.canonical_scanner_finding_register.findings' in text, text[-7000:]
    assert '1675' in text
    assert ('rawcandidatecount=1675' in text or 'recuentodecandidatosoriginales=1675' in text), text[-3000:]
    assert '1/2' in text
    assert ('requisitonosatisfecho' if language == 'es-MX' else 'requirementnotmet') in text
    assert package == before
    assert result['human_review_required'] is True
    assert result['client_delivery_allowed'] is False


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_installed_final_worker_candidate_population_and_repeatability(language, tmp_path):
    import os
    import subprocess
    import sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    code = 'from tests.test_candidate_export_truth_v1 import _installed_worker; import sys; _installed_worker(sys.argv[1])'
    result = subprocess.run([sys.executable, '-c', code, language], cwd=root,
        env=owned_worker_environment(root, tmp_path, os.environ), capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize('renderer', ['phase1', 'legacy'])
@pytest.mark.parametrize('spanish', [False, True])
def test_final_summary_rejects_stale_assurance_and_unknown_compact_zero(renderer, spanish):
    from tests.test_client_summary_scanner_population import canonical
    from nico.candidate_phase1_report_workload_pdf_v1 import render_phase1_evidence_review_gate_pdf
    from nico.comprehensive_client_ready_projection_v1 import render_evidence_review_gate_pdf
    c = canonical('es-MX' if spanish else 'en')['json']
    c['scanner_execution_records'][0].update(compact_record=True, raw_findings_embedded=False,
                                             findings=[], finding_summary={'raw': None})
    c['analyzer_evidence_report'] = {'commit_sha': 'f' * 40, 'analyzers': [
        {'scanner': 'eslint', 'required': True, 'consecutive_successful_passes': 99,
         'consecutive_passes_required': 2, 'acceptance_ready': True}]}
    before = deepcopy(c)
    render = render_phase1_evidence_review_gate_pdf if renderer == 'phase1' else render_evidence_review_gate_pdf
    pdf = render(c, {}, spanish=spanish)
    text = ' '.join(' '.join(p.extract_text().split()) for p in PdfReader(io.BytesIO(pdf)).pages)
    assert ('eslint: recuento de candidatos originales=no disponible' if spanish else
            'eslint: raw candidate count=unavailable') in text
    assert '99/2' not in text
    assert c == before
