"""Regression cases captured from native TypeScript 6.0.3 owned controls."""
from nico.scanner_evidence_pipeline_v1 import _typescript_findings


def test_native_missing_file_diagnostic_retains_project_scope_and_explanation():
    text = (
        "error TS6053: File '/owned/repo/missing.ts' not found.\n"
        "  The file is in the program because:\n"
        "    Part of 'files' list in tsconfig.json\n"
    )
    findings = _typescript_findings(text)
    assert len(findings) == 1
    assert findings[0]['code'] == 'TS6053'
    assert findings[0]['diagnostic_scope'] == 'project'
    assert 'file_path' not in findings[0] and 'line' not in findings[0]
    assert "Part of 'files' list in tsconfig.json" in findings[0]['message']


def test_native_no_inputs_diagnostic_retains_project_scope():
    text = (
        "error TS18003: No inputs were found in config file '/owned/repo/tsconfig.json'. "
        "Specified 'include' paths were '[\"absent/**/*.ts\"]' and 'exclude' paths were '[]'.\n"
    )
    findings = _typescript_findings(text)
    assert len(findings) == 1
    assert findings[0]['code'] == 'TS18003'
    assert findings[0]['diagnostic_scope'] == 'project'
    assert 'file_path' not in findings[0] and 'line' not in findings[0]


def test_source_diagnostic_location_is_preserved():
    findings = _typescript_findings(
        'index.ts(1,7): error TS2322: Type string is not assignable to type number.\n'
    )
    assert findings == [{
        'file_path': 'index.ts', 'line': 1, 'column': 7, 'code': 'TS2322',
        'message': 'Type string is not assignable to type number.', 'severity': 'high'
    }]


def test_non_native_output_is_not_diagnostic_evidence():
    assert _typescript_findings('unexpected runner error\n') == []
    assert _typescript_findings('error TSbroken: unsupported diagnostic\n') == []


def test_unrecognized_stdout_resets_continuation_and_is_incomplete():
    from nico.scanner_evidence_pipeline_v1 import _typescript_diagnostics
    findings, complete = _typescript_diagnostics(
        "error TS6053: File 'missing.ts' not found.\n"
        "unrecognized worker log\n  unrelated payload\n"
    )
    assert complete is False
    assert len(findings) == 1
    assert findings[0]['message'] == "File 'missing.ts' not found."


def test_malformed_diagnostic_resets_continuation():
    from nico.scanner_evidence_pipeline_v1 import _typescript_diagnostics
    for malformed in ('error TSbroken: malformed header', '  error TSbroken: malformed header'):
        findings, complete = _typescript_diagnostics(
            'index.ts(1,7): error TS2322: Type string is not assignable to type number.\n'
            + malformed + '\n  unrelated payload\n'
        )
        assert complete is False
        assert len(findings) == 1
        assert findings[0]['message'] == 'Type string is not assignable to type number.'


def test_multiline_diagnostic_bound_keeps_complete_flag_truthful():
    from nico.scanner_evidence_pipeline_v1 import _typescript_diagnostics
    findings, complete = _typescript_diagnostics('error TS6053: missing\n  ' + 'x' * 65_536 + '\n')
    assert complete is False
    assert findings[0]['message'] == 'missing'


def test_capture_requires_consistent_exit_and_fully_classified_output(tmp_path, monkeypatch):
    from nico.scanner_evidence_pipeline_v1 import _run_typescript
    from nico.scanner_tool_runners import ProjectCommandPreparation, ScannerToolSpec
    from nico.worker_execution import WorkerCommandResult, WorkerWorkspace
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'true')
    workspace = WorkerWorkspace(root=tmp_path)
    project = workspace.repo_dir
    (project / 'node_modules' / '.bin').mkdir(parents=True)
    (project / 'tsconfig.json').write_text('{}')
    (project / 'node_modules' / '.bin' / 'tsc').write_text('')
    prep = ProjectCommandPreparation('completed', project, True)
    spec = ScannerToolSpec('typescript', ('tsc',), 'static')
    cases = [
        (0, '', '', 'completed', 0),
        (2, 'error TS6053: missing\n', '', 'completed', 1),
        (1, 'error TS18003: No inputs\n', '', 'completed', 1),
        (0, 'error TS6053: missing\n', '', 'failed', 1),
        (2, '', '', 'failed', 0),
        (0, '', 'opaque stderr', 'failed', 0),
        (2, 'error TS6053: missing\nopaque stdout\n', '', 'failed', 1),
    ]
    for exit_code, stdout, stderr, status, count in cases:
        def runner(args, *, cwd, limits, stdout_path, extra_env):
            stdout_path.write_text(stdout)
            return WorkerCommandResult(args=tuple(args), returncode=exit_code, stdout=stdout,
                                       stderr=stderr, stdout_path=str(stdout_path),
                                       stdout_bytes=len(stdout), stderr_bytes=len(stderr))
        result = _run_typescript(spec, workspace, runner, prep)
        assert result['status'] == status
        assert result['findings_count'] == count
        assert result['returncode'] == exit_code
        assert result['output_capture_complete'] is (status == 'completed')
        if exit_code:
            assert result['returncode'] != 0


def test_invalid_utf8_cannot_become_complete_native_evidence(tmp_path, monkeypatch):
    from nico.scanner_evidence_pipeline_v1 import _run_typescript
    from nico.scanner_tool_runners import ProjectCommandPreparation, ScannerToolSpec
    from nico.worker_execution import WorkerCommandResult, WorkerWorkspace
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'true')
    workspace = WorkerWorkspace(root=tmp_path)
    project = workspace.repo_dir
    (project / 'node_modules' / '.bin').mkdir(parents=True)
    (project / 'tsconfig.json').write_text('{}')
    (project / 'node_modules' / '.bin' / 'tsc').write_text('')
    prep = ProjectCommandPreparation('completed', project, True)
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        raw = b'error TS6053: corrupted \xff diagnostic\n'
        stdout_path.write_bytes(raw)
        return WorkerCommandResult(args=tuple(args), returncode=2, stdout='', stderr='',
                                   stdout_path=str(stdout_path), stdout_bytes=len(raw))
    result = _run_typescript(ScannerToolSpec('typescript', ('tsc',), 'static'), workspace, runner, prep)
    assert result['status'] == 'failed'
    assert result['output_capture_complete'] is False
    assert 'UTF-8' in result['failure_or_unavailable_reason']


def test_zero_exit_does_not_override_native_parse_bound(tmp_path, monkeypatch):
    from nico import scanner_evidence_pipeline_v1 as pipeline
    from nico.scanner_tool_runners import ProjectCommandPreparation, ScannerToolSpec
    from nico.worker_execution import WorkerCommandResult, WorkerWorkspace
    monkeypatch.setenv('NICO_ALLOW_PROJECT_COMMANDS', 'true')
    monkeypatch.setattr(pipeline, 'MAX_PARSE_BYTES', 16)
    workspace = WorkerWorkspace(root=tmp_path)
    project = workspace.repo_dir
    (project / 'node_modules' / '.bin').mkdir(parents=True)
    (project / 'tsconfig.json').write_text('{}')
    (project / 'node_modules' / '.bin' / 'tsc').write_text('')
    def runner(args, *, cwd, limits, stdout_path, extra_env):
        stdout_path.write_text(' ' * 17)
        return WorkerCommandResult(args=tuple(args), returncode=0, stdout='', stderr='',
                                   stdout_path=str(stdout_path))
    result = pipeline._run_typescript(ScannerToolSpec('typescript', ('tsc',), 'static'),
                                     workspace, runner, ProjectCommandPreparation('completed', project, True))
    assert result['returncode'] == 0
    assert result['status'] == 'failed'
    assert result['output_capture_complete'] is False
