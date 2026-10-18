import json
import logging
import pytest
from nico import report_delivery_timing_v1 as timing

DETAILS = {'prep_reconcile', 'prep_truth_repair', 'prep_installed_completion',
           'prep_stage_projection', 'prep_coverage', 'finalize_core',
           'finalize_prepare', 'finalize_legacy', 'finalize_truth',
           'finalize_presentation', 'finalize_pdf', 'finalize_validation',
           'finalize_binding', 'finalize_manifest_attach'}


def records(caplog, prefix):
    return [json.loads(r.getMessage().split('=', 1)[1]) for r in caplog.records
            if r.getMessage().startswith(prefix + '=')]


def test_detail_slots_survive_ordinary_phase_saturation(caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_' + 'a'*32, 'es-MX'):
        for phase in sorted(timing._PHASE_NAMES - DETAILS):
            with timing.report_delivery_phase_scope(phase):
                pass
        for phase in sorted(DETAILS):
            with timing.report_delivery_phase_scope(phase):
                pass
    progress = records(caplog, 'NICO_REPORT_PROGRESS')
    final, = records(caplog, 'NICO_REPORT_TIMING')
    assert {r.get('phase') for r in progress} >= DETAILS
    assert len(progress) + 1 == 32
    assert sum(r.get('phase') not in DETAILS for r in progress) == 17
    assert DETAILS <= final['phases'].keys()
    assert all(final['phases'][phase]['calls'] == 1 for phase in DETAILS)


def install_production_chain():
    from nico.api import specialist_ship_ready_bootstrap as bootstrap
    from nico.comprehensive_report_review_integrity_v1 import install_comprehensive_report_review_integrity_v1
    from nico.comprehensive_intake_display_metadata_v2 import install_comprehensive_intake_display_metadata_v2
    from nico.comprehensive_canonical_truth_hash_compat_v1 import install_canonical_truth_hash_compat
    from nico.comprehensive_commercial_ship_projection_v3 import install_comprehensive_commercial_ship_projection_v3
    assert bootstrap.APPROVED_LIFECYCLE_CONSISTENCY['installed'] is True
    for install in (install_comprehensive_report_review_integrity_v1,
                    install_comprehensive_intake_display_metadata_v2,
                    install_canonical_truth_hash_compat,
                    install_comprehensive_commercial_ship_projection_v3):
        install()


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
    from tests.test_comprehensive_localized_export_v1 import source_status
    from nico.comprehensive_localized_export_v1 import localized_evidence_package
    install_production_chain()
    source = source_status.__wrapped__(); before = deepcopy(source)
    expected = localized_evidence_package(source, language)
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_' + 'c'*32, language):
        actual = localized_evidence_package(source, language)
    assert actual.body == expected.body
    assert dict(actual.headers) == dict(expected.headers)
    assert actual.status_code == expected.status_code
    assert source == before
    assert records(caplog, 'NICO_REPORT_TIMING')[0]['outcome'] == 'completed'


def manifest_wrapper(current, attach):
    """Compile the actual installed wrapper in an isolated namespace, not runtime patches."""
    import ast
    from functools import wraps
    from pathlib import Path
    import nico.comprehensive_artifact_manifest_approval_v1 as module
    root = ast.parse(Path(module.__file__).read_text())
    installer = next(node for node in root.body if isinstance(node, ast.FunctionDef) and node.name == 'install_comprehensive_artifact_manifest_approval_v1')
    wrapper = next(node for node in ast.walk(installer) if isinstance(node, ast.FunctionDef) and node.name == 'finalize_client_report_package')
    factory = ast.FunctionDef(name='factory', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='current')], kwonlyargs=[], kw_defaults=[], defaults=[]),
                              body=[wrapper, ast.Return(value=ast.Name(id=wrapper.name,ctx=ast.Load()))], decorator_list=[])
    tree = ast.fix_missing_locations(ast.Module(body=[factory], type_ignores=[]))
    namespace = {'wraps':wraps, 'Mapping':dict, 'Any':object, 'attach_artifact_manifest':attach,
                 'report_delivery_phase_scope':timing.report_delivery_phase_scope}
    exec(compile(tree,'<isolated-installed-manifest-wrapper>','exec'),namespace)
    return namespace['factory'](current), namespace


def test_manifest_captures_outer_callable_before_inner_call_and_invokes_once(caplog):
    events = []; value = object(); package = object()
    def original_attach(result):
        events.append('original_attach'); assert result is value; return package
    def replacement(result):
        events.append('replacement'); return result
    def current(argument):
        events.append('current'); assert argument is package
        namespace['attach_artifact_manifest'] = replacement
        return value
    wrapper, namespace = manifest_wrapper(current, original_attach)
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_'+'d'*32,'en'):
        assert wrapper(package) is package
    assert events == ['current','original_attach']
    assert records(caplog,'NICO_REPORT_TIMING')[0]['phases']['finalize_manifest_attach']['calls'] == 1


@pytest.mark.parametrize('where', ['current','attach'])
def test_manifest_exception_identity_recovery_and_no_payload_logging(caplog, where):
    events = []; original = ValueError('SECRET_REPORT_CONTENT_AND_TOKEN')
    def current(argument):
        events.append('current')
        if where == 'current': raise original
        return argument
    def attach(argument):
        events.append('attach')
        raise original
    wrapper, _ = manifest_wrapper(current, attach)
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with pytest.raises(ValueError) as caught:
        with timing.report_delivery_timing('comprun_'+'e'*32,'es-MX'):
            wrapper({'secret':'SECRET_REPORT_CONTENT_AND_TOKEN'})
    assert caught.value is original
    assert events == (['current'] if where == 'current' else ['current','attach'])
    assert timing._ACTIVE.get() is None
    assert 'SECRET_REPORT_CONTENT_AND_TOKEN' not in caplog.text
    recovered, _ = manifest_wrapper(lambda value:value, lambda value:value)
    with timing.report_delivery_timing('comprun_'+'f'*32,'en'):
        assert recovered(7) == 7
    assert records(caplog,'NICO_REPORT_TIMING')[-1]['outcome'] == 'completed'


def test_nested_context_and_suppressed_details_keep_complete_aggregates(caplog):
    caplog.set_level(logging.INFO, logger='uvicorn.error')
    with timing.report_delivery_timing('comprun_'+'a'*32,'en'):
        outer = timing._ACTIVE.get()
        for _ in range(3):
            for name in sorted(DETAILS):
                with timing.report_delivery_phase_scope(name): pass
        with timing.report_delivery_timing('comprun_'+'b'*32,'es-MX'):
            with timing.report_delivery_phase_scope('prep_reconcile'): pass
        assert timing._ACTIVE.get() is outer
    assert timing._ACTIVE.get() is None
    inner, outer_result = records(caplog,'NICO_REPORT_TIMING')
    assert inner['phases']['prep_reconcile']['calls'] == 1
    assert all(outer_result['phases'][name]['calls'] == 3 for name in DETAILS)
    assert outer_result['progress_suppressed'] == 28
    assert outer_result['progress_records'] == 15


def test_actual_preparation_preserves_original_exception_and_recovers(caplog):
    from collections.abc import Mapping
    from tests.test_v2_premium_report_renderer import _package
    from nico.phase17_canonical_artifact_rebuild_v1 import _prepare_client_artifact_package
    original = ValueError('SECRET_SOURCE_PATH_AND_REPORT_CONTENT')
    class BrokenMapping(Mapping):
        def __iter__(self): raise original
        def __len__(self): return 1
        def __getitem__(self,key): raise original
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    with pytest.raises(ValueError) as caught:
        with timing.report_delivery_timing('comprun_'+'a'*32,'es-MX'):
            _prepare_client_artifact_package(BrokenMapping())
    assert caught.value is original
    assert timing._ACTIVE.get() is None
    assert 'SECRET_SOURCE_PATH_AND_REPORT_CONTENT' not in caplog.text
    failed = records(caplog,'NICO_REPORT_PROGRESS')[-2]
    assert failed['phase'] == 'prep_reconcile' and failed['outcome'] == 'failed'
    with timing.report_delivery_timing('comprun_'+'b'*32,'en'):
        assert 'json' in _prepare_client_artifact_package(_package('en'))
    assert records(caplog,'NICO_REPORT_TIMING')[-1]['outcome'] == 'completed'


def test_detail_budgets_are_isolated_across_concurrent_requests(caplog):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    barrier = Barrier(2)
    caplog.set_level(logging.INFO,logger='uvicorn.error')
    def request(index):
        with timing.report_delivery_timing('comprun_'+str(index)*32,'es-MX'):
            barrier.wait(timeout=3)
            for name in sorted(timing._PHASE_NAMES):
                with timing.report_delivery_phase_scope(name): pass
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(request,[1,2]))
    finals = records(caplog,'NICO_REPORT_TIMING')
    assert len(finals) == 2
    for final in finals:
        progress = [row for row in records(caplog,'NICO_REPORT_PROGRESS') if row['request_id']==final['request_id']]
        assert len(progress) == 31
        assert {row.get('phase') for row in progress} >= DETAILS
        assert all(final['phases'][name]['calls']==1 for name in DETAILS)
