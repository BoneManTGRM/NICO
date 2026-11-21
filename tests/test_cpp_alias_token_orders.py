"""Extracted alias endpoint checks; not full Cppcheck qualification evidence."""
import shutil
import subprocess

import pytest

from scripts import repair_cppcheck_header_grammar as repair


def injected_kernel():
    source = b'\n'.join(new for _, new in repair.EXTRA_REPLACEMENTS['lib/tokenize.cpp']).decode()
    start = source.index('    Token *findSemicolon(Token *tok,')
    end = source.index('\n} // namespace', start)
    walker = source[start:end]
    start = source.index('        struct AliasEnd {')
    end = source.index('        // Only records can match', start)
    collector = source[start:end] + '        return aliasEnds;\n'
    return walker, collector


HARNESS = r'''
#include <iostream>
#include <string>
#include <vector>
using std::size_t;
struct Token {
    std::string text;
    Token* following;
    const std::string& str() const { return text; }
    Token* next() { return following; }
};
WALKER
struct Lookup { Token* token; const void* scope; size_t order; };
struct Endpoint { Token* token; size_t order; };
std::vector<Endpoint> endpoints(const std::vector<Lookup>& aliases) {
    const auto collect = [&]() {
COLLECTOR
    };
    std::vector<Endpoint> result;
    for (const auto& entry : collect()) result.push_back({entry.alias.token, entry.endOrder});
    return result;
}
bool check(const std::vector<std::string>& words, int expectedFirst = -2) {
    std::vector<Token> tokens;
    tokens.reserve(words.size());
    for (const auto& word : words) tokens.push_back({word, nullptr});
    for (size_t i = 1; i < tokens.size(); ++i) tokens[i-1].following = &tokens[i];
    std::vector<Lookup> aliases;
    std::vector<Endpoint> expected;
    // Independent positional oracle uses vector indices, including non-semicolons.
    const size_t offset = 113;
    for (size_t i = 0; i < tokens.size(); ++i) {
        size_t j = i, depth = 0;
        for (; j < words.size(); ++j) {
            if (!depth && words[j] == ";") break;
            if (words[j] == "{") ++depth;
            else if (depth && words[j] == "}") --depth;
        }
        Token* want = j == tokens.size() ? nullptr : &tokens[j];
        size_t order = offset + i;
        Token* found = findSemicolon(&tokens[i], &order);
        if (found != want || findSemicolon(&tokens[i]) != want) {
            std::cerr << "endpoint differs\n"; return false;
        }
        if (found && order != offset + j) {
            std::cerr << "original position lost\n"; return false;
        }
        if (i == 0 && expectedFirst != -2 &&
            (found ? static_cast<int>(j) : -1) != expectedFirst) return false;
        aliases.push_back({&tokens[i], nullptr, offset+i});
        if (want) expected.push_back({&tokens[i], offset+j});
    }
    const auto actual = endpoints(aliases);
    if (actual.size() != expected.size()) {
        std::cerr << "null endpoint retained\n"; return false;
    }
    for (size_t i = 0; i < actual.size(); ++i) {
        if (actual[i].token != expected[i].token || actual[i].order != expected[i].order) {
            std::cerr << "alias order differs\n"; return false;
        }
    }
    size_t untouched = 9;
    if (findSemicolon(nullptr, &untouched) || untouched != 9 || findSemicolon(nullptr)) return false;
    return true;
}
int main() {
    // Shared endpoints, nested reversed endpoints, missing delimiters and RHS uses.
    if (!check({}, -1) || !check({"name"}, -1) || !check({";"}, 0) ||
        !check({"using", "A", "=", "A", ";", "A"}, 4) ||
        !check({"using", "A", "=", "{", "using", "B", "=", "A", ";", "}", ";"}, 10) ||
        !check({"{", "{", ";", "}", ";", "}", ";"}, 6) ||
        !check({"using", "A", "=", "{", ";"}, -1) || !check({"}", "name", ";"}, 2)) return 1;
    const std::string alphabet[] = {"name", ";", "{", "}"};
    size_t cases = 0;
    for (size_t length = 0, combinations = 1; length <= 7; ++length, combinations *= 4) {
        for (size_t encoded = 0; encoded < combinations; ++encoded) {
            std::vector<std::string> words; size_t value = encoded;
            for (size_t i = 0; i < length; ++i, value /= 4) words.push_back(alphabet[value % 4]);
            if (!check(words)) return 1;
            ++cases;
        }
    }
    std::vector<std::string> sparse(100000, "name");
    for (size_t i = 96; i < sparse.size(); i += 97) sparse[i] = ";";
    if (!check(sparse)) return 1;
    sparse.erase(sparse.begin(), sparse.begin() + 17);
    if (!check(sparse)) return 1;
    std::cout << "exhaustive_cases=" << cases << "\n";
}
'''


def run_kernel(tmp_path, walker, collector):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('native GCC is unavailable in this unit-test environment')
    source = tmp_path / 'alias-endpoints.cpp'
    source.write_text(HARNESS.replace('WALKER', walker).replace('COLLECTOR', collector))
    binary = tmp_path / 'alias-endpoints'
    built = subprocess.run(
        [compiler, '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
        capture_output=True, timeout=15, check=False,
    )
    assert built.returncode == 0, built.stderr.decode(errors='replace')
    return subprocess.run([str(binary)], capture_output=True, timeout=15, check=False)


def test_alias_endpoint_positions_and_default_calls(tmp_path):
    result = run_kernel(tmp_path, *injected_kernel())
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert result.stdout == b'exhaustive_cases=21845\n'


@pytest.mark.parametrize('mutation,reason', [
    ('missed_token', b'original position lost'),
    ('relative_order', b'alias order differs'),
    ('null_endpoint', b'null endpoint retained'),
])
def test_endpoint_kernel_rejects_semantic_regressions(tmp_path, mutation, reason):
    walker, collector = injected_kernel()
    if mutation == 'missed_token':
        walker = walker.replace('++*order;', '*order += 0;')
    elif mutation == 'relative_order':
        collector = collector.replace('size_t endOrder = alias.order;', 'size_t endOrder = 0;')
    else:
        collector = collector.replace('if (findSemicolon(alias.token, &endOrder))',
                                      'if (findSemicolon(alias.token, &endOrder) || true)')
    result = run_kernel(tmp_path, walker, collector)
    assert result.returncode == 1
    assert reason in result.stderr
