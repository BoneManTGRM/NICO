"""Synthetic native regressions for failures observed in retained Cppcheck XML."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
from xml.sax.saxutils import quoteattr

import pytest

from nico.cppcheck_native_output import parse_native
from nico.assessment_worker_jobs import _digest

CRITICAL = 'Active checkers: There was critical errors (use --checkers-report=<filename> to see details)'
INVENTORY = 'Active checkers: 167/856 (use --checkers-report=<filename> to see details)'
CASES = [
    ('preprocessorErrorDirective', '#error Owned compiler environment is unavailable', 'error'),
    ('checkersReport', CRITICAL, 'information'),
    ('checkersReport', 'Active checkers: 0/856 (use --checkers-report=<filename> to see details)', 'information'),
]


def xml(path, rule, message, severity):
    return ('<results version="2"><cppcheck version="2.17.1"/><errors>'
            f'<error id={quoteattr(rule)} severity={quoteattr(severity)} msg={quoteattr(message)}>'
            f'<location file={quoteattr(path)} line="1" column="1"/>'
            '</error></errors></results>')


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_fatal_native_diagnostics_are_limits_not_code_risk_findings(rule, message, severity):
    findings, limits, observed = parse_native(xml('owned.cpp', rule, message, severity),
        'Checking owned.cpp ...\n', ['owned.cpp'], version='2.17.1')
    assert not findings
    assert observed == ['owned.cpp']  # A progress line is only a launch observation.
    assert limits[0]['rule_id'] == rule and limits[0]['message'] == message


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_failed_static_context_never_earns_completion_and_other_contexts_survive(tmp_path, rule, message, severity):
    from tests.test_cpp_project_static import request, native
    from nico.assessment_cpp_project_compiler import _canonical
    from nico.assessment_cpp_project_static import validate_project_static
    req = request(tmp_path)
    value = native(req)
    row = value['records'][0]
    raw = xml(req['contexts'][0]['analysis_file'], rule, message, severity).encode()
    row.update(xml=base64.b64encode(raw).decode(), xml_sha256=hashlib.sha256(raw).hexdigest())
    proof = validate_project_static(_canonical(value), req)
    assert not proof['complete'] and not proof['findings']
    assert proof['attempted_contexts'] == proof['required_contexts']
    assert proof['analyzed_contexts'] == proof['required_contexts'][1:]
    assert proof['limitations'][0]['rule_id'] == rule
    assert not proof['human_review_completed'] and not proof['production_qualified']


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_standalone_worker_reparses_native_failure_before_canonical_completion(rule, message, severity):
    from scripts.worker_protocol_fixture import receipt
    from tests.test_assessment_worker_receipts import validate
    value = receipt()
    value['native']['xml'] = xml('src/control.cpp', rule, message, severity)
    value['native_sha256'] = _digest(value['native'])
    raw, record, _ = validate(value)
    assert json.loads(raw)['native'] == value['native']
    assert record['status'] == 'partial' and not record['completed']
    assert not record['findings'] and not record['verified_for_this_report']
    assert record['cppcheck_source_coverage']['limitations'][0]['rule_id'] == rule
    assert not record['client_delivery_allowed']


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_configured_worker_preserves_build_but_not_failed_analysis(rule, message, severity):
    from tests.test_assessment_cpp_configuration import configured_contract, configured_receipt
    from nico.assessment_cpp_configuration import validate_native
    plan = configured_contract()
    _, value = configured_receipt(plan)
    row = next(r for r in value['native']['steps'] if r['id'] == 'analyze-0')
    row['artifact'] = base64.b64encode(xml('/work/source/main.cpp', rule, message, severity).encode()).decode()
    result = validate_native(value['native'], plan)
    assert result['status'] == 'partial' and not result['complete']
    assert result['coverage']['observed_targets'] == ['value.cpp']
    assert result['findings'] == []
    assert result['build']['build_completed'] and result['build']['native_test']['passed'] == 1


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_full_project_worker_keeps_failed_static_stage_out_of_completed_coverage(rule, message, severity):
    from tests.test_assessment_cpp_full_project import plan, native
    from nico.assessment_cpp_full_project import validate_native
    contract = plan(); value = native(contract)
    row = next(r for r in value['steps'] if r['id'] == 'static-analysis')
    row['artifacts']['analysis_xml'] = base64.b64encode(xml('/work/source/main.cpp', rule, message, severity).encode()).decode()
    result = validate_native(value, contract)
    assert not result['complete'] and result['status'] == 'partial'
    assert not result['findings']
    assert not result['coverage']['configuration_aware']
    assert result['build']['build_completed']


@pytest.mark.parametrize('rule,message,severity', CASES)
def test_standalone_scanner_preserves_raw_failure_without_claiming_report_assurance(monkeypatch, tmp_path, rule, message, severity):
    from tests.test_cppcheck_execution import workspace
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import ScannerToolSpec
    from nico.worker_execution import WorkerCommandResult
    target = workspace(tmp_path)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: '/tools/cppcheck')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'Cppcheck 2.17.1')
    raw = xml('src/value.cpp', rule, message, severity)
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        Path(next(a.split('=', 1)[1] for a in args if a.startswith('--output-file='))).write_text(raw)
        stdout_path.write_text('Checking src/value.cpp ...\n')
        return WorkerCommandResult(tuple(args), 0, stdout_path.read_text(), '')
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, runner)
    assert result['status'] == 'partial' and not result['verified_for_this_report']
    assert not result['findings']
    artifact = json.loads(gzip.decompress(bytes.fromhex(result['_raw_artifact_blob']['gzip_hex'])))
    assert artifact['native_xml'] == raw


@pytest.mark.parametrize('rule,message,severity', [
    ('checkersReport', INVENTORY, 'information'),
    ('uninitvar', 'Uninitialized variable: owned', 'warning'),
])
def test_positive_inventory_and_genuine_findings_still_allow_completed_execution(tmp_path, rule, message, severity):
    from tests.test_cpp_project_static import request, native
    from nico.assessment_cpp_project_compiler import _canonical
    from nico.assessment_cpp_project_static import validate_project_static
    req = request(tmp_path); value = native(req)
    for context, row in zip(req['contexts'], value['records']):
        raw = xml(context['analysis_file'], rule, message, severity).encode()
        row.update(xml=base64.b64encode(raw).decode(), xml_sha256=hashlib.sha256(raw).hexdigest())
    result = validate_project_static(_canonical(value), req)
    assert result['complete'] and result['analyzed_contexts'] == result['required_contexts']
    assert len(result['findings']) == (3 if rule == 'uninitvar' else 0)


def test_project_parser_reuses_preparsed_xml_without_changing_native_truth(monkeypatch):
    import xml.etree.ElementTree as ET
    from nico import cppcheck_native_output as parser
    raw = xml('owned.cpp', 'uninitvar', 'Uninitialized variable: owned', 'warning')
    document = ET.fromstring(raw)
    monkeypatch.setattr(parser.ET, 'fromstring', lambda value: pytest.fail('XML parsed twice'))
    findings, limits, observed = parser.parse_native(raw, 'Checking owned.cpp ...\n', ['owned.cpp'],
        version='2.17.1', document=document)
    assert observed == ['owned.cpp'] and not limits
    assert len(findings) == 1 and findings[0]['rule_id'] == 'uninitvar'
