"""Offline report regressions using retained runtime collection evidence."""
import base64
from copy import deepcopy
import hashlib

import pytest

from nico.assessment_cpp_full_project_report import enrich_scanner_stage
from nico.assessment_cpp_runtime_scope import validate_retained_runtime
from nico.assessment_worker_receipts import canonical_bytes
from tests.test_cpp_runtime_collection import fixture, output, validate


@pytest.mark.parametrize('locale,incomplete,collected,failed', [
    ('en', 'Declared runtime scope is incomplete.',
     'Declared runtime evidence was fully collected; target runtime checks failed.',
     'Sanitizer / undefined: 0/'),
    ('es-MX', 'El alcance de ejecución declarado está incompleto.',
     'La evidencia de ejecución declarada se recopiló por completo; las comprobaciones de ejecución del proyecto fallaron.',
     'Sanitizador / undefined: 0/'),
])
@pytest.mark.parametrize('fault', [None, 'missing_fuzz', 'truncated_log'])
def test_report_distinguishes_collected_failure_from_incomplete_evidence(
        tmp_path, locale, incomplete, collected, failed, fault):
    value = fixture(tmp_path, later_fault='runtime-fuzz-build' if fault == 'missing_fuzz' else None)
    if fault == 'truncated_log':
        output(value[0]['evidence']['failure_diagnostics'][0]['log_read'], canonical_bytes({
            'data': base64.b64encode(b'partial').decode(), 'truncated': True}))
    raw = canonical_bytes(value[0])
    summary = validate_retained_runtime(raw, *value[1:])['summary']
    assert summary['complete'] is False
    if fault is None:
        decision = validate(value)
        assert decision['status'] == 'complete_with_findings'
        assert decision['target_tests_passed'] is False
        assert decision['full_project_qualified'] is False
        assert decision['production_qualified'] is False
        assert decision['summary'] == summary
        collection_complete = decision['collection_complete']
    else:
        with pytest.raises(ValueError, match='worker_runtime_collection_incomplete'):
            validate(value)
        collection_complete = False

    digest = hashlib.sha256(raw).hexdigest()
    record = {
        'commit_sha': 'b' * 40, 'raw_artifact_retention_complete': True,
        'raw_artifact_sha256': digest, 'current_run': True, 'exact_commit_match': True,
        'execution_observed_for_this_report': True,
        'worker_provenance': {'profile': 'cpp-configure-first-v2', 'receipt_sha256': digest,
            'identity': {'run_id': 'run', 'revision': 'b' * 40}},
        'cppcheck_source_coverage': {'header_context_verified': True},
        'cpp_build_evidence': {'profile': 'cpp-configure-first-v2', 'compiled': True,
            'collection_complete': collection_complete, 'runtime_scope': summary},
    }
    canonical = {'report_language': locale,
        'identity': {'run_id': 'run', 'commit_sha': 'b' * 40},
        'scanner_execution_records': [record]}
    original = deepcopy(canonical)
    rendered = enrich_scanner_stage(canonical, {'summary': '', 'evidence': [], 'unavailable': []})
    text = ' '.join([rendered['summary'], *rendered['evidence'], *rendered['unavailable']])
    assert failed in text
    assert (collected in text) is (fault is None)
    assert (incomplete in text) is (fault is not None)
    assert canonical == original
