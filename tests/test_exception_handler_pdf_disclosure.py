"""Installed export abstains when producer capture is not available to PDF labels."""
from copy import deepcopy
import pytest
from tests.test_candidate_investigation_pdf_disclosure import SCOPE, fixture
from nico.report_preview_labels_v1 import retained_coverage_disclosures


@pytest.mark.parametrize('spanish', [False, True])
@pytest.mark.parametrize('rule_field', ['rule_id', 'rule'])
def test_export_never_authenticates_packet_embedded_handler_fact(spanish, rule_field):
    context = fixture()
    register = context['assessment']['canonical_scanner_finding_register']
    register['findings'][0].pop('rule_id', None)
    register['findings'][0][rule_field] = 'B110'
    register['candidate_investigation']['packets'][0]['exception_handler'] = {
        'version': 'nico.exception-handler-evidence.v1', 'body_kind': 'single_pass',
        'raw_source': 'PRIVATE_HANDLER_SENTINEL'}
    before = deepcopy(context)
    text = '\n'.join(retained_coverage_disclosures(context, spanish=spanish))
    assert ('Evidencia del cuerpo del manejador no disponible' if spanish else
            'Handler body evidence unavailable for this export') in text
    assert 'PRIVATE_HANDLER_SENTINEL' not in text
    assert 'contains only pass' not in text and 'contiene solo pass' not in text
    assert context == before


def _installed_worker(locale):
    import base64, io
    from pypdf import PdfReader
    from nico.api import final_report_worker_bootstrap
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts
    from nico.candidate_investigation_finalization_v1 import final_investigation_scope
    from nico.candidate_investigation_pipeline_v1 import capture_sources, investigate_register
    from nico.comprehensive_exact_artifact_hash_binding_v1 import _validate_exact_artifact_hashes
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from tests.test_comprehensive_same_run_locale_report_v1 import _install_finalized_scanner_register
    from tests.test_candidate_investigation_pdf_disclosure import production_count_fixture
    package = {'json': _fixed_status(locale)['reports']['json']}
    package['json']['identity'].update(SCOPE)
    seed = _install_finalized_scanner_register(package['json'])
    register, _ = production_count_fixture()
    register['findings'][0].update(rule_id='B110', line=3)
    capture = capture_sources({'example.py': 'try:\n    risky()\nexcept Exception:\n    pass\n'}, SCOPE)
    register['candidate_investigation'] = investigate_register(register, capture, SCOPE)
    seed.update(register)
    context = {**SCOPE, 'prior_stage_results': {'evidence_reconciliation_and_scoring': {
        'candidate_source_observations': capture, 'assessment': {'canonical_scanner_finding_register': deepcopy(seed)}}}}
    before = deepcopy((context, package))
    with final_investigation_scope(context):
        result = rebuild_client_artifacts(package)
    _validate_exact_artifact_hashes(result)
    pdf = ' '.join(page.extract_text() or '' for page in PdfReader(io.BytesIO(base64.b64decode(result['pdf_base64']))).pages)
    expected = ('Handler body evidence unavailable for this export; handler candidates remain unresolved and require human contextual review.' if locale == 'en' else
                'Evidencia del cuerpo del manejador no disponible para esta exportación; los candidatos de manejadores siguen sin resolver y requieren revisión contextual humana.')
    assert ''.join(expected.split()) in ''.join(pdf.split())
    assert 'Handler body contains only pass' not in pdf
    assert 'El cuerpo del manejador contiene solo pass' not in pdf
    assert result['human_review_required'] is True and result['client_delivery_allowed'] is False
    assert (context, package) == before


@pytest.mark.parametrize('locale', ['en', 'es-MX'])
def test_installed_pdf_explicitly_abstains_without_trusted_capture(locale, tmp_path):
    import os, subprocess, sys
    from pathlib import Path
    from tests.owned_worker_environment import owned_worker_environment
    root = Path(__file__).resolve().parents[1]
    code = 'import sys; from tests.test_exception_handler_pdf_disclosure import _installed_worker; _installed_worker(sys.argv[1])'
    result = subprocess.run([sys.executable, '-c', code, locale], cwd=root,
                            env=owned_worker_environment(root, tmp_path, os.environ),
                            capture_output=True, text=True, timeout=240)
    assert result.returncode == 0, result.stdout + result.stderr
