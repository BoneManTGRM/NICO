"""Owned snapshot lifecycle and work controls; not native project qualification."""
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import repair_cppcheck_header_grammar as repair


def production_parts():
    replacements = repair.EXTRA_REPLACEMENTS['lib/tokenize.cpp']
    source = b'\n'.join(new for _, new in replacements).decode()
    start = source.index('            std::set<const Token*> aliasShadowed;')
    end = source.index('            for (Token *tok2 = tok;', start)
    snapshot = source[start:end]
    guards = []
    for marker in (b'(inMemberFunc && tok2->str() == typeName->str()))) {',
                   b'                if (simplifyType) {'):
        matches = [new for old, new in replacements if old.startswith(marker)
                   or old.lstrip().startswith(marker.lstrip())]
        assert len(matches) == 1
        body = matches[0].decode()
        # Execute the actual injected barrier, not a separately maintained copy.
        guards.append(''.join(line+'\n' for line in body.splitlines()
                              if 'ensureAliasShadowed();' in line))
        assert guards[-1].strip() == 'ensureAliasShadowed();'
    return snapshot, guards


def run_kernel(tmp_path, mutation=None):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('native GCC unavailable; no execution credit')
    snapshot, guards = production_parts()
    if mutation == 'no_match_barrier':
        guards[0] = ''
    elif mutation == 'no_mutation_barrier':
        guards[1] = ''
    elif mutation == 'empty_is_unready':
        snapshot = snapshot.replace('if (aliasShadowedReady)', 'if (!aliasShadowed.empty())')
    elif mutation == 'eager':
        snapshot += '            ensureAliasShadowed();\n'
    elif mutation == 'stale_declarator':
        snapshot = snapshot.replace('std::set<const Token*> aliasShadowed;',
                                    'static std::set<const Token*> aliasShadowed;')
        snapshot = snapshot.replace('bool aliasShadowedReady = false;',
                                    'static bool aliasShadowedReady = false;')
    source = Path('tests/fixtures/cpp/alias-snapshot-kernel.cpp').read_text()
    source = source.replace('SNAPSHOT\n', snapshot).replace('MATCH_BARRIER\n', guards[0])
    source = source.replace('MUTATION_BARRIER\n', guards[1])
    path = tmp_path/'snapshot.cpp'; path.write_text(source)
    binary = tmp_path/'snapshot'
    built = subprocess.run([compiler, '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(path), '-o', str(binary)], capture_output=True, timeout=20)
    assert built.returncode == 0, built.stderr.decode(errors='replace')
    return subprocess.run([str(binary)], capture_output=True, timeout=20)


def test_snapshot_semantics_and_eliminated_unused_work(tmp_path):
    result = run_kernel(tmp_path)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert result.stdout == b'event_cases=2730 unused_sweeps=64 unused_visits=0 one_snapshot_visits=8192\n'


@pytest.mark.parametrize('mutation', ['no_match_barrier', 'no_mutation_barrier',
                                     'empty_is_unready', 'eager', 'stale_declarator'])
def test_snapshot_controls_detect_work_or_lifetime_regression(tmp_path, mutation):
    result = run_kernel(tmp_path, mutation)
    assert result.returncode == 1, result.stdout.decode(errors='replace')
