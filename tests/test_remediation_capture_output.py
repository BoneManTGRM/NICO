"""Execute the actual workflow shell with deterministic offline scanner doubles.

This proves capture plumbing, not Semgrep rule coverage or parser compatibility.
"""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def static_step():
    source = (ROOT / '.github/workflows/remediation-evidence.yml').read_text()
    section = source.split('      - name: Collect static evidence\n', 1)[1]
    body = section.split('        run: |\n', 1)[1].split('\n      - name:', 1)[0]
    return '\n'.join(line[10:] for line in body.splitlines() if line.startswith('          '))


@pytest.mark.parametrize('exit_code', [0, 1, 2])
def test_scanner_output_is_outside_target_and_diagnostics_are_retained(tmp_path, exit_code):
    checkout = tmp_path / 'checkout'
    staging = tmp_path / 'runner-temp'
    binaries = tmp_path / 'bin'
    for path in (checkout / 'remediation-evidence', checkout / 'apps/web', staging, binaries):
        path.mkdir(parents=True)
    (checkout / 'ordinary.py').write_text('value = 1\n')
    # A real source JSON file must remain visible, unlike our own generated output.
    (checkout / 'source.json').write_text('{"source": true}\n')
    for name in ('bandit', 'npm'):
        p = binaries / name
        p.write_text('#!/bin/sh\nexit 0\n')
        p.chmod(0o755)
    scanner = binaries / 'semgrep'
    scanner.write_text('#!' + sys.executable + '\n' + '''
import json, os, pathlib, sys
assert sys.argv[1:] == ['scan', '--json', '--config', 'auto', '.']
root = pathlib.Path.cwd()
# Shell redirection creates the destination before scanner execution.
# Detect precisely the reported self-output collision, without running rules.
collision = (root / 'remediation-evidence/semgrep.json').exists()
assert (root / 'source.json').is_file()
print(json.dumps({'self_output_in_target': collision, 'errors': [{'type': 'PartialParsing', 'path': '.github/workflows/example.yml'}]}))
print('retained parser diagnostic', file=sys.stderr)
sys.exit(int(os.environ['SCANNER_EXIT']))
''')
    scanner.chmod(0o755)
    env = {'PATH': str(binaries) + ':/usr/bin:/bin', 'RUNNER_TEMP': str(staging),
           'SCANNER_EXIT': str(exit_code)}
    result = subprocess.run(['/bin/bash', '-e', '-c', static_step()], cwd=checkout,
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr  # Existing evidence-collection contract.
    evidence = checkout / 'remediation-evidence'
    captured = json.loads((evidence / 'semgrep.json').read_text())
    assert captured['self_output_in_target'] is False
    assert captured['errors'] == [{'type': 'PartialParsing', 'path': '.github/workflows/example.yml'}]
    assert (evidence / 'semgrep.stderr').read_text() == 'retained parser diagnostic\n'
    assert (evidence / 'semgrep.exit').read_text().strip() == str(exit_code)
    assert (evidence / 'typescript.exit').read_text().strip() == '0'
    assert list(staging.iterdir()) == []


def test_capture_staging_failure_cannot_claim_success(tmp_path):
    checkout = tmp_path / 'checkout'
    binaries = tmp_path / 'bin'
    (checkout / 'remediation-evidence').mkdir(parents=True)
    binaries.mkdir()
    bandit = binaries / 'bandit'
    bandit.write_text('#!/bin/sh\nexit 0\n')
    bandit.chmod(0o755)
    env = {'PATH': str(binaries) + ':/usr/bin:/bin',
           'RUNNER_TEMP': str(tmp_path / 'missing-directory')}
    result = subprocess.run(['/bin/bash', '-e', '-c', static_step()], cwd=checkout,
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode != 0
    assert not (checkout / 'remediation-evidence/semgrep.json').exists()
    assert not (checkout / 'remediation-evidence/semgrep.exit').exists()
