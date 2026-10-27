"""Report consumers exercise the real authenticated import and durable byte validator."""
import copy

import pytest
from test_retained_typescript_status_coverage_v1 import (
    api, retained, project, display_value, persisted_case, evaluate, replace_projection,
)
from nico.production_report_truth_gate_v1 import reconcile_production_report_truth
from nico.report_execution_provenance_e6 import scanner_execution_evidence
from nico.comprehensive_release_provenance_v1 import _provenance_lines as release_provenance_lines
from nico import comprehensive_scanner_inventory_v1 as inventory


@pytest.fixture(autouse=True)
def verified_checkout(persisted_case):
    # The shared importer fixture stubs checkout verification; report provenance
    # also requires the independently verified checkout used in production.
    persisted_case.record['source_checkout_verified'] = True


def consume(case, monkeypatch, damage=None):
    canonical, _ = evaluate(case, monkeypatch)
    # Keep this inventory restricted to the real persisted scanner under test.
    scan = inventory.get_scan(case.binding['scan_id'])
    scan.update(scanner_results=[case.record], tools_requested=['typescript'])
    canonical['scanner_execution_records'] = [r for r in canonical['scanner_execution_records'] if r['tool'] == 'typescript']
    row = canonical['scanner_execution_records'][0]
    if damage == 'stale_projection': row['raw_artifact_sha256'] = 'd' * 64
    canonical['assessment'] = {'technical_score':93, 'evidence_adjusted_score':93,
        'sections':[{'id':'static_analysis', 'label':'Static Analysis', 'unavailable':[], 'evidence':[]}]}
    stages = {'dependency_security_static_analysis':{'scan_id':case.binding['scan_id']}}
    evidence = scanner_execution_evidence(canonical['identity'], stages)
    report = reconcile_production_report_truth({'json':canonical})['json']
    return report, evidence


@pytest.mark.parametrize('outcome', ['clean', 'errors'])
def test_report_recognizes_retained_ci_without_claiming_current_execution(persisted_case, monkeypatch):
    before = copy.deepcopy(persisted_case.record)
    report, evidence = consume(persisted_case, monkeypatch)
    row = report['scanner_execution_records'][0]
    assert evidence['verification_status'] == 'verified', str(evidence)
    assert report['assessment']['sections'][0]['unavailable'] == []
    assert row['retained_ci_evidence_verified'] is True
    assert row['verified_complete'] is False
    assert row['current_run'] is False and row['execution_observed_for_this_report'] is False
    assert row['finding_count'] == (0 if before['clean'] else 1)
    assert report['assessment']['technical_score'] == report['assessment']['evidence_adjusted_score'] == 93
    assert evidence['verification_status'] == 'verified'
    assert evidence['scanner_records'][0]['retained_ci_evidence_verified'] is True
    assert evidence['scanner_records'][0]['execution_evidence_verified'] is False
    text = str(release_provenance_lines({'scanner_execution_evidence':evidence}))
    assert 'retained CI evidence verified=True' in text
    assert 'current_run=False' in str(report['assessment']['sections'][0]['evidence'])
    assert report['client_readiness_contract']['explicit_required_scanners_verified'] is False
    assert persisted_case.record == before


@pytest.mark.parametrize('outcome,damage', [('incomplete', None)] + [('clean', d) for d in (
    'unqualified', 'wrong_sha', 'tampered', 'stale_scan', 'stale_projection', 'incomplete_actual', 'durable_corruption', 'unverified_checkout', 'forged_labels',
)])
def test_invalid_evidence_stays_unavailable(persisted_case, monkeypatch, damage):
    case = persisted_case
    if damage == 'durable_corruption':
        with case.store.connect() as connection:
            connection.execute('UPDATE scanner_raw_artifacts SET gzip_blob=? WHERE artifact_id=?',
                               (b'changed', case.record['raw_artifact']['artifact_id']))
            connection.commit()
    elif damage == 'unverified_checkout': case.record['source_checkout_verified'] = False
    elif damage == 'forged_labels':
        case.record.update(coverage_basis='authenticated_retained_typescript_ci', retained_ci_evidence_verified=True)
        replace_projection(case, lambda body: body.pop('authenticated_import'))
    elif damage == 'unqualified': replace_projection(case, lambda body: body.pop('authenticated_import'))
    elif damage == 'wrong_sha': case.record['ci_source_sha'] = 'c' * 40
    elif damage == 'tampered': case.record['raw_artifact']['sha256'] = 'c' * 64
    elif damage == 'stale_scan': case.record['run_id'] = 'comprun_stale'
    elif damage == 'incomplete_actual':
        case.record.update(current_run=True, execution_observed_for_this_report=True,
                           output_capture_complete=False, raw_artifact_retention_complete=False)
    report, evidence = consume(case, monkeypatch, damage)
    assert report['assessment']['sections'][0]['unavailable']
    assert report['scanner_execution_records'][0].get('retained_ci_evidence_verified') is not True
    if damage != 'stale_projection':
        assert evidence['verification_status'] == 'unverified'
        assert evidence['scanner_records'][0].get('retained_ci_evidence_verified') is not True


@pytest.mark.parametrize('outcome', ['clean', 'errors'])
@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_retained_provenance_renders_in_all_report_formats(persisted_case, monkeypatch, language):
    import base64
    import io
    from pypdf import PdfReader
    from nico.api import final_report_worker_bootstrap  # noqa: F401
    from nico.comprehensive_canonical_report_source_v1 import build_canonical_report_source
    from nico.phase17_canonical_artifact_rebuild_v1 import rebuild_client_artifacts

    canonical, evidence = consume(persisted_case, monkeypatch)
    # Use the existing provenance composition fixture's empty control scorecard;
    # ordinary Static Analysis coverage is asserted separately above.
    render_assessment = {**canonical['assessment'], 'sections': []}
    context = dict(**canonical['identity'], evidence_ledger_id='ledger_owned_report', generated_at='2026-10-17T00:00:00Z', report_language=language,
        prior_stage_results={
            'authorization_and_scope': {'status':'complete', 'evidence':{'authorized':True}},
            'dependency_security_static_analysis': {'status':'complete', 'scan_id':persisted_case.binding['scan_id'],
                'scanner_execution_records':canonical['scanner_execution_records']},
            'evidence_reconciliation_and_scoring': {'status':'complete', 'assessment':render_assessment, 'evidence':{}},
        })
    result = build_canonical_report_source(context)
    assert result['status'] == 'complete', str(result)
    original_package = copy.deepcopy(result['report_package'])
    original_record = copy.deepcopy(persisted_case.record)
    raw_files = {path.relative_to(persisted_case.raw_root): path.read_bytes()
                 for path in persisted_case.raw_root.rglob('*') if path.is_file()}
    assert raw_files
    package = rebuild_client_artifacts(result['report_package'])
    assert result['report_package'] == original_package
    assert persisted_case.record == original_record
    assert {path.relative_to(persisted_case.raw_root): path.read_bytes()
            for path in persisted_case.raw_root.rglob('*') if path.is_file()} == raw_files
    retained = package['json']['assessment']['nico_release_provenance']['scanner_execution_evidence']
    assert retained['verification_status'] == 'verified'
    assert retained['scanner_records'][0]['execution_observed'] is False
    assert retained['scanner_records'][0]['retained_ci_evidence_verified'] is True
    pdf = PdfReader(io.BytesIO(base64.b64decode(package['pdf_base64'])))
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    label = 'retained CI evidence verified=True' if language == 'en' else 'evidencia de CI conservada verificada=Sí'
    for rendered in (package['markdown'], package['html'], text):
        assert label in rendered
        false_label = ('execution observed for this report=False' if language == 'en'
                       else 'ejecución observada para este informe=No')
        assert false_label in ' '.join(rendered.split())
        if language == 'es-MX':
            assert 'evidencia de CI conservada verificada=True' not in rendered
        assert persisted_case.record['raw_artifact_sha256'] in rendered

    # Unknown display states remain explicit; raw enums/nulls are not rewritten.
    for state in (None, 'unknown', 'future_status_preserve'):
        probe = copy.deepcopy(retained)
        probe['scanner_records'][0]['execution_status'] = state
        probe['scanner_records'][0]['retained_ci_evidence_verified'] = None
        before_probe = copy.deepcopy(probe)
        lines = release_provenance_lines({'scanner_execution_evidence': probe}, spanish=language == 'es-MX')
        display = ' '.join(value for _, value in lines)
        expected_state = (state if state == 'future_status_preserve' else
                          ('desconocido' if language == 'es-MX' else 'unknown'))
        assert f": {expected_state};" in display
        # Verification is not established by an unknown/null value.
        assert ('retained CI evidence verified=No' if language == 'es-MX'
                else 'retained CI evidence verified=False') in display
        assert probe == before_probe
    assert retained['scanner_records'][0]['execution_observed'] is False
    assert retained['scanner_records'][0]['retained_ci_evidence_verified'] is True
