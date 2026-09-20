from pathlib import Path
import gzip
import hashlib
import json

import pytest

from nico import scanner_evidence_pipeline_v1 as pipeline
from nico.node_scanner_applicability_v1 import inspect_node_inputs, justified_inapplicability
from nico.scanner_tool_runners import ScannerToolSpec
from nico.worker_execution import WorkerCommandResult, WorkerWorkspace

SHA = 'a' * 40
XML = '''<?xml version="1.0"?><results version="2"><cppcheck version="2.17.1"/><errors>
<error id="arrayIndexOutOfBounds" severity="error" msg="Out of bounds" cwe="788">
<location file="src/value.cpp" line="3" column="5"/></error></errors></results>'''


def workspace(tmp_path):
    (tmp_path / 'repo' / 'src').mkdir(parents=True)
    (tmp_path / 'repo' / 'src' / 'value.cpp').write_text('int f() {\n int a[2];\n a[4]=0;\n return 0;\n}\n')
    return WorkerWorkspace(tmp_path, node_input_inventory=inspect_node_inputs(tmp_path / 'repo', SHA))


def test_cppcheck_native_findings_targets_and_raw_evidence(monkeypatch, tmp_path):
    target = workspace(tmp_path)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: '/tools/cppcheck')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'Cppcheck 2.17.1')
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        Path(next(a.split('=', 1)[1] for a in args if a.startswith('--output-file='))).write_text(XML)
        stdout_path.write_text('Checking src/value.cpp ...\n1/1 files checked 100% done\n')
        assert not any('project' in a or 'inline-suppr' in a for a in args)
        return WorkerCommandResult(tuple(args), 0, stdout_path.read_text(), '')
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, runner)
    assert result['status'] == 'completed'
    assert result['findings_count'] == 1
    finding = result['findings'][0]
    assert (finding['rule_id'], finding['path'], finding['line']) == ('arrayIndexOutOfBounds', 'src/value.cpp', 3)
    assert result['cppcheck_source_coverage']['requested_target_count'] == 1
    assert result['cppcheck_source_coverage']['observed_target_count'] == 1
    assert result['cppcheck_source_coverage']['all_repository_configurations_analyzed'] is False
    raw = json.loads(gzip.decompress(bytes.fromhex(result['_raw_artifact_blob']['gzip_hex'])))
    assert 'arrayIndexOutOfBounds' in raw['native_xml']
    assert raw['progress_log'].startswith('Checking')
    assert result['scanner_execution_receipt']['input_identity_status'] == 'stable_observed_inputs'


@pytest.mark.parametrize('output,timeout,expected', [('<broken', False, 'failed'), (XML, True, 'timeout')])
def test_cppcheck_invalid_or_timed_out_output_is_not_complete(monkeypatch, tmp_path, output, timeout, expected):
    target = workspace(tmp_path)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: '/tools/cppcheck')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'Cppcheck 2.17.1')
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        Path(next(a.split('=', 1)[1] for a in args if a.startswith('--output-file='))).write_text(output)
        stdout_path.write_text('Checking src/value.cpp ...\n')
        return WorkerCommandResult(tuple(args), 124 if timeout else 0, '', '', timed_out=timeout)
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, runner)
    assert result['status'] == expected
    assert result['verified_for_this_report'] is False


def test_cppcheck_absence_requires_complete_exact_source_inventory(tmp_path):
    (tmp_path / 'main.py').write_text('print(1)\n')
    inventory = inspect_node_inputs(tmp_path, SHA)
    assert justified_inapplicability(inventory, 'cppcheck', SHA)
    assert not justified_inapplicability(inventory, 'cppcheck', 'b' * 40)
    (tmp_path / 'main.cpp').write_text('int main() {}\n')
    assert not justified_inapplicability(inspect_node_inputs(tmp_path, SHA), 'cppcheck', SHA)


def test_prepared_cppcheck_is_not_activated_without_worker_qualification():
    from nico.scanner_tool_runners import TOOL_SPECS
    assert 'cppcheck' not in pipeline.REQUIRED_EVIDENCE_TOOLS
    assert 'cppcheck' not in {spec.name for spec in TOOL_SPECS}


def test_cppcheck_does_not_reuse_prior_native_output(monkeypatch, tmp_path):
    target = workspace(tmp_path)
    raw = tmp_path / 'scanner-raw'
    raw.mkdir()
    (raw / 'cppcheck.xml').write_text(XML)
    (raw / 'cppcheck-progress.txt').write_text('Checking src/value.cpp ...\n')
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: '/tools/cppcheck')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'Cppcheck 2.17.1')
    def runner(args, **kwargs):
        return WorkerCommandResult(tuple(args), 0, '', '')
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, runner)
    assert result['status'] == 'failed'
    assert result['output_capture_complete'] is False
    assert result['cppcheck_source_coverage']['observed_target_count'] == 0


def test_cppcheck_missing_binary_keeps_positive_input_evidence(monkeypatch, tmp_path):
    target = workspace(tmp_path)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: None)
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, None)
    assert result['status'] == 'unavailable'
    assert result['applicability_evidence']['cpp_input_paths'] == ['src/value.cpp']
    assert not justified_inapplicability(result['applicability_evidence'], 'cppcheck', SHA)


def test_cppcheck_partial_receipt_hashes_the_final_state(monkeypatch, tmp_path):
    target = workspace(tmp_path)
    monkeypatch.setattr(pipeline.shutil, 'which', lambda name: '/tools/cppcheck')
    monkeypatch.setattr(pipeline, '_scanner_version', lambda *args: 'Cppcheck 2.17.1')
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        Path(next(a.split('=', 1)[1] for a in args if a.startswith('--output-file='))).write_text(XML)
        stdout_path.write_text('')
        return WorkerCommandResult(tuple(args), 0, '', '')
    result = pipeline._run_cppcheck(ScannerToolSpec('cppcheck', ('cppcheck',), 'static'), target, runner)
    assert result['status'] == 'partial'
    assert result['failure_or_unavailable_reason'] == result['reason']
    assert result['deterministic_fingerprint'] == pipeline._deterministic_fingerprint(result, target)
    canonical = {key: value for key, value in result.items() if key not in {'artifact_hash', '_raw_artifact_blob'}}
    assert result['artifact_hash'] == hashlib.sha256(json.dumps(canonical, sort_keys=True, default=str, separators=(',', ':')).encode()).hexdigest()
