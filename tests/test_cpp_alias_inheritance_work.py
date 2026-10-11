"""Actual injected lookup kernel; owned evidence, not full analyzer qualification."""
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import repair_cppcheck_header_grammar as repair


def kernel():
    source = b'\n'.join(new for _, new in repair.EXTRA_REPLACEMENTS['lib/tokenize.cpp']).decode()
    start = source.index('    struct ScopeInfo3 {')
    scopes = source[start:source.index('    void setScopeInfo(', start)]
    # Count actual name resolution, including the unmodified reference method.
    scopes = scopes.replace('const ScopeInfo3 * findScope(const std::string & scope) const {',
                            'const ScopeInfo3 * findScope(const std::string & scope) const { ++scopeSearches;')
    start = source.index('    using AliasBaseResolutions =')
    memo = source[start:source.index('    std::set<const Token*> aliasShadowedTokens', start)]
    memo = memo.replace('        bool result =', '        ++queryExpansions;\n        bool result =')
    start = source.index('        // Only records can match through inheritance')
    body = source[start:source.index('        return result;', start)] + '        return result;\n'
    return scopes, memo, body


def run_kernel(tmp_path, *, mutation=None):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('native GCC unavailable; no native evidence claimed')
    scopes, memo, body = kernel()
    if mutation == 'no_memo':
        memo = memo.replace('if (known != matches.end())', 'if (false && known != matches.end())')
    elif mutation == 'stale_target':
        body = body.replace('            std::map<const ScopeInfo3*, bool> baseVisibility, recordVisibility;\n', '')
        body = body.replace('        for (const auto& record : recordAliases) {',
                            '        std::map<const ScopeInfo3*, bool> baseVisibility, recordVisibility;\n'
                            '        for (const auto& record : recordAliases) {')
    elif mutation == 'rhs_visible':
        body = body.replace('                if (!eligible)', '                if (false && !eligible)')
    fixture = Path('tests/fixtures/cpp/alias-inheritance-kernel.cpp').read_text()
    source = tmp_path / 'inheritance.cpp'
    source.write_text(fixture.replace('SCOPES', scopes).replace('MEMO', memo).replace('BODY', body))
    binary = tmp_path / 'inheritance'
    built = subprocess.run([compiler, '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror',
                            str(source), '-o', str(binary)], capture_output=True, timeout=20)
    assert built.returncode == 0, built.stderr.decode(errors='replace')
    return subprocess.run([str(binary)], capture_output=True, timeout=20)


def test_alias_inheritance_semantics_and_bounded_shared_graph_work(tmp_path):
    result = run_kernel(tmp_path)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert b'graph_cases=1024' in result.stdout
    assert b'mutation_rebuilt=1' in result.stdout
    assert b'diamond_baseline_searches=524286 diamond_candidate_searches=70' in result.stdout


@pytest.mark.parametrize('mutation', ['no_memo', 'stale_target', 'rhs_visible'])
def test_kernel_detects_work_and_visibility_regressions(tmp_path, mutation):
    result = run_kernel(tmp_path, mutation=mutation)
    assert result.returncode == 1, result.stdout.decode(errors='replace')
