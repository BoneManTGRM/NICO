"""Synthetic workflow controls; never invoke a real scanner or provider."""
from pathlib import Path
import os
import subprocess
import sys

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / '.github/workflows/security-audit.yml'


def workflow():
    return yaml.load(WORKFLOW.read_text(), Loader=yaml.BaseLoader)


def steps():
    return {step['name']: step for step in workflow()['jobs']['audit-evidence']['steps']}


def test_one_fresh_security_run_for_non_main_draft_pr():
    triggers = workflow()['on']
    assert triggers['pull_request']['branches'] == ['main']
    assert triggers['push']['branches'] == ['main']
    assert set(triggers) == {'pull_request', 'push', 'workflow_dispatch'}
    assert 'concurrency' not in workflow()
    assert 'concurrency' not in workflow()['jobs']['audit-evidence']


def test_identity_output_cannot_disable_final_enforcement_or_upload():
    items = steps()
    names = list(items)
    emit = items['Emit fresh bounded security identities']
    enforce = items['Require complete clean security evidence']
    assert emit['if'] == enforce['if'] == 'always()'
    assert 'continue-on-error' not in emit
    assert emit['env']['SECURITY_IDENTITY_FRESH_CAPTURE'] == '${{ steps.gitleaks_identity.outputs.sealed }}'
    assert items['Collect gitleaks git-history evidence']['id'] == 'gitleaks_identity'
    assert emit['run'] == 'python scripts/security_identity_console.py emit --root .'
    assert enforce['run'] == 'python scripts/security_audit_gate.py --enforce --require-sanitized-trufflehog'
    assert names.index('Build fail-closed scanner manifest') < names.index('Emit fresh bounded security identities')
    assert names.index('Emit fresh bounded security identities') < names.index('Upload audit evidence before enforcement') < names.index('Require complete clean security evidence')
    assert items['Upload audit evidence before enforcement']['if'] == 'always()'
    assert '.security-identity-context.json' not in items['Upload audit evidence before enforcement']['with']['path']


@pytest.mark.parametrize('helper_failure', [False, True])
def test_setup_failure_does_not_skip_fresh_collection_or_summary(tmp_path, helper_failure):
    # Only synthetic executables: no actual scanner and no network access.
    executable = tmp_path / 'bin'
    executable.mkdir()
    log = tmp_path / 'calls'
    python = executable / 'python'
    python.write_text(f'''#!{sys.executable}
import os, sys
from pathlib import Path
if sys.argv[1:2] == ['scripts/security_identity_console.py']:
    with open(os.environ['CALL_LOG'], 'a') as stream: stream.write(sys.argv[2] + '\\n')
    raise SystemExit({int(helper_failure)})
os.execv(sys.executable, [sys.executable, *sys.argv[1:]])
''')
    scanner = executable / 'gitleaks'
    scanner.write_text(f'''#!{sys.executable}
import os, sys
from pathlib import Path
with open(os.environ['CALL_LOG'], 'a') as stream: stream.write('scan\\n')
Path('gitleaks.json').write_text('[]')
print('synthetic-private-output-canary')
print('synthetic-private-error-canary', file=sys.stderr)
raise SystemExit(1)
''')
    python.chmod(0o755)
    scanner.chmod(0o755)
    env = dict(os.environ, PATH=str(executable) + os.pathsep + os.environ['PATH'], CALL_LOG=str(log), GITHUB_OUTPUT=str(tmp_path / 'step-output'))
    result = subprocess.run(['bash', '-e', '-o', 'pipefail', '-c', steps()['Collect gitleaks git-history evidence']['run']], cwd=tmp_path, env=env, capture_output=True, timeout=15)
    assert result.returncode == 0
    assert log.read_text().splitlines() == ['prepare', 'scan', 'seal']
    assert (tmp_path / 'gitleaks-summary.json').is_file()
    assert (tmp_path / 'step-output').exists() is (not helper_failure)
    assert b'canary' not in result.stdout + result.stderr


def test_scanner_flags_and_trufflehog_no_verification_remain_intact():
    items = steps()
    run = items['Collect gitleaks git-history evidence']['run']
    assert 'gitleaks detect --source . --report-format json --report-path gitleaks.json --no-banner --redact >/dev/null 2>&1' in run
    assert '--no-verification' in items['Collect trufflehog git-history evidence']['run']
    env = workflow()['jobs']['audit-evidence']['env']
    assert env['SECURITY_IDENTITY_PR_HEAD'] == '${{ github.event.pull_request.head.sha || github.sha }}'
    assert env['SECURITY_IDENTITY_BASE'] == '${{ github.event.pull_request.base.sha || github.sha }}'


def test_diagnostic_changes_do_not_match_native_workflow_path_filters():
    from fnmatch import fnmatchcase
    changed = {
        '.github/workflows/security-audit.yml',
        'scripts/security_identity_console.py',
        'tests/test_security_identity_console.py',
        'tests/test_security_identity_workflow.py',
    }
    for name in ('cpp-full-project-integration.yml', 'cpp-worker-boundary-qualification.yml',
                 'cpp-worker-image-retrieval.yml', 'cpp-full-project-control.yml',
                 'native-timeout-diagnostic.yml'):
        source = yaml.load((WORKFLOW.parent / name).read_text(), Loader=yaml.BaseLoader)
        for event in ('pull_request', 'push'):
            trigger = source['on'].get(event)
            if trigger is None:
                continue
            patterns = trigger.get('paths', [])
            assert patterns, name
            assert not any(fnmatchcase(path, pattern) for path in changed for pattern in patterns), name
