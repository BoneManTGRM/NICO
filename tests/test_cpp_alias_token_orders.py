"""Cheap owned kernel checks; not full Cppcheck or native qualification evidence."""
import shutil
import subprocess

import pytest

from scripts import repair_cppcheck_header_grammar as repair


def injected_kernel():
    source = b'\n'.join(new for _, new in repair.EXTRA_REPLACEMENTS['lib/tokenize.cpp']).decode()
    start = source.index('    Token *findSemicolon(Token *tok)')
    end = source.index('\n} // namespace', start)
    find_semicolon = source[start:end]
    start = source.index('        std::map<const Token*, size_t> orders;')
    end = source.index('            if ((Token::Match(token,', start)
    index = source[start:end] + '        }\n        return orders;\n'
    return find_semicolon, index


HARNESS = r'''
#include <algorithm>
#include <iostream>
#include <map>
#include <string>
#include <vector>
using std::size_t;
struct Token {
    std::string text;
    Token* following;
    const std::string& str() const { return text; }
    Token* next() { return following; }
};
FIND_SEMICOLON
std::map<const Token*, size_t> indexedOrders(Token* first) {
INDEX_BODY
}
bool check(const std::vector<std::string>& words, int firstEnd = -2) {
    std::vector<Token> tokens;
    tokens.reserve(words.size());
    for (const auto& word : words) tokens.push_back({word, nullptr});
    for (size_t i = 1; i < tokens.size(); ++i) tokens[i-1].following = &tokens[i];
    Token* first = tokens.empty() ? nullptr : &tokens.front();
    const auto orders = indexedOrders(first);
    if (orders.size() != static_cast<size_t>(std::count(words.begin(), words.end(), ";"))) {
        std::cerr << "unused or missing token order keys\n"; return false;
    }
    // Independent positional oracle: vector offsets, including non-semicolons.
    for (size_t i = 0; i < tokens.size(); ++i) {
        const auto found = orders.find(&tokens[i]);
        if (words[i] == ";") {
            if (found == orders.end() || found->second != i) {
                std::cerr << "original token position lost\n"; return false;
            }
        } else if (found != orders.end()) return false;
        Token* end = findSemicolon(&tokens[i]);
        const auto selected = orders.find(end);
        if (end) {
            if (end->str() != ";" || selected == orders.end() ||
                selected->second != static_cast<size_t>(end - tokens.data())) {
                std::cerr << "semicolon lookup differs\n"; return false;
            }
        } else if (selected != orders.end()) return false;
    }
    if (orders.find(nullptr) != orders.end()) return false;
    if (firstEnd != -2) {
        Token* end = findSemicolon(first);
        const int actual = end ? static_cast<int>(end - tokens.data()) : -1;
        if (actual != firstEnd) { std::cerr << "nested/malformed lookup differs\n"; return false; }
    }
    return true;
}
int main() {
    if (!check({}, -1) || !check({"name"}, -1) || !check({";"}, 0) ||
        !check({"using", "A", "=", "T", ";"}, 4) ||
        !check({"using", "A", "=", "{", "x", ";", "}", ";"}, 7) ||
        !check({"{", "{", ";", "}", ";", "}", ";"}, 6) ||
        !check({"using", "A", "=", "{", ";"}, -1) ||
        !check({"}", "name", ";"}, 2)) return 1;
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
    // Deterministic allocation-work proxy, not a wall-time benchmark.
    std::vector<std::string> sparse(100000, "name");
    for (size_t i = 96; i < sparse.size(); i += 97) sparse[i] = ";";
    if (!check(sparse)) return 1;
    // New helper-local map after a changed list: no pointer/order reuse.
    sparse.erase(sparse.begin(), sparse.begin() + 17);
    if (!check(sparse)) return 1;
    std::cout << "exhaustive_cases=" << cases << " sparse_semicolons=1030\n";
}
'''


def run_kernel(tmp_path, find_semicolon, index):
    compiler = shutil.which('g++')
    if compiler is None:
        pytest.skip('native GCC is unavailable in this unit-test environment')
    source = tmp_path / 'token-orders.cpp'
    source.write_text(HARNESS.replace('FIND_SEMICOLON', find_semicolon).replace('INDEX_BODY', index))
    binary = tmp_path / 'token-orders'
    built = subprocess.run(
        [compiler, '-std=c++11', '-O2', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)],
        capture_output=True, timeout=15, check=False,
    )
    assert built.returncode == 0, built.stderr.decode(errors='replace')
    return subprocess.run([str(binary)], capture_output=True, timeout=15, check=False)


def test_token_orders_preserve_positions_with_only_semicolon_keys(tmp_path):
    result = run_kernel(tmp_path, *injected_kernel())
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert result.stdout == b'exhaustive_cases=21845 sparse_semicolons=1030\n'


@pytest.mark.parametrize('mutation,reason', [
    ('dense', b'unused or missing token order keys'),
    ('renumbered', b'original token position lost'),
    ('wrong_delimiter', b'unused or missing token order keys'),
])
def test_order_kernel_rejects_work_and_semantic_regressions(tmp_path, mutation, reason):
    find_semicolon, index = injected_kernel()
    guard = 'if (token->str() == ";")'
    assert index.count(guard) == 1
    if mutation == 'dense':
        index = index.replace(guard, 'if (true)')
    elif mutation == 'renumbered':
        index = index.replace('orders[token] = order;', 'orders[token] = orders.size();')
    else:
        index = index.replace(guard, 'if (token->str() == ",")')
    result = run_kernel(tmp_path, find_semicolon, index)
    assert result.returncode == 1
    assert reason in result.stderr
