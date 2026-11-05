import logging
import pytest
from tests.test_export_phase_diagnostics import DETAILS, records, timing, install_production_chain

@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_real_installed_chain_hits_all_details_without_changing_outputs(caplog, language):
    from copy import deepcopy
    from tests.test_v2_premium_report_renderer import _package
    from nico import phase17_canonical_artifact_rebuild_v1 as phase17
    install_production_chain()
    source = _package(language); before = deepcopy(source)
    # Establish the same installed extension state before differential execution.
    phase17.rebuild_client_artifacts(source)
    expected = phase17.rebuild_client_artifacts(source)
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_' + 'b'*32, language):
        actual = phase17.rebuild_client_artifacts(source)
    final, = records(caplog, 'NICO_REPORT_TIMING')
    assert DETAILS <= final['phases'].keys(), sorted(DETAILS - final['phases'].keys())
    assert final['phases']['prep_reconcile']['calls'] == 2
    assert actual == expected
    assert source == before
    assert len(records(caplog, 'NICO_REPORT_PROGRESS')) + 1 <= 32
    for name in DETAILS:
        assert final['phases'][name]['calls'] == (2 if name == 'prep_reconcile' else 1)
    assert source['json']['identity']['repository'] not in caplog.text


@pytest.mark.parametrize('language', ['en', 'es-MX'])
def test_real_export_response_bytes_headers_and_manifests_are_identical(caplog, language):
    from copy import deepcopy
    from tests.test_cross_locale_pdf_repeatability_v1 import _fixed_status
    from nico.comprehensive_localized_export_v1 import localized_evidence_package
    install_production_chain()
    # Exercise new English rendering and retained Spanish export without bypassing admission.
    source = _fixed_status('es-MX'); before = deepcopy(source)
    expected = localized_evidence_package(source, language)
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_' + 'c'*32, language):
        actual = localized_evidence_package(source, language)
    assert actual.body == expected.body
    assert dict(actual.headers) == dict(expected.headers)
    assert actual.status_code == expected.status_code
    assert source == before
    assert records(caplog, 'NICO_REPORT_TIMING')[0]['outcome'] == 'completed'
