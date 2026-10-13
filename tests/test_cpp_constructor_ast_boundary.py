"""Unit-test the emitted helper with controlled endpoints and delimiter links.

The Token shim isolates boundary behavior; it is not native parser evidence.
Native AST and variable-ID checks live in tests/native/cppcheck_constructor_ast.cpp.
"""
import shutil
import subprocess

import pytest

from scripts import repair_cppcheck_placement_ast as repair


@pytest.fixture(scope='module')
def boundary_runner(tmp_path_factory):
    compiler = shutil.which('g++')
    if not compiler:
        pytest.skip('C++ compiler required for emitted helper unit tests')
    directory = tmp_path_factory.mktemp('constructor-boundary')
    source = directory / 'boundary.cpp'
    source.write_text(r'''
#include <iostream>
#include <sstream>
#include <string>
#include <vector>
struct Token {
    std::string text;
    int index;
    Token *after = nullptr, *before = nullptr, *other = nullptr;
    const std::string& str() const { return text; }
    Token* next() const { return after; }
    Token* previous() const { return before; }
    Token* link() const { return other; }
    static bool Match(const Token* tok, const char* pattern) {
        std::istringstream alternatives(pattern);
        std::string word;
        while (std::getline(alternatives, word, '|'))
            if (tok && tok->str() == word) return true;
        return false;
    }
};
bool precedes(const Token* a, const Token* b) { return a && b && a->index < b->index; }
struct TokenList {
    static Token* end;
    static const Token* isFunctionHead(Token*, const std::string&) { return end; }
};
Token* TokenList::end = nullptr;
static Token *skipMethodDeclEnding(Token *tok) {
    if (tok->str() != ")") tok = tok->previous();
    if (!tok || tok->str() != ")") return nullptr;
''' + repair.METHOD_REPLACEMENT.decode() + r'''
    return nullptr;
}
int main(int argc, char** argv) {
    std::istringstream input(argv[1]);
    std::string word;
    std::vector<Token> tokens;
    while (input >> word) { Token token; token.text = word; tokens.push_back(token); }
    for (unsigned i = 0; i < tokens.size(); ++i) {
        tokens[i].index = i;
        if (i) tokens[i].before = &tokens[i-1];
        if (i+1 < tokens.size()) tokens[i].after = &tokens[i+1];
    }
    int end = std::stoi(argv[3]);
    TokenList::end = end < 0 ? nullptr : &tokens.at(end);
    for (int i = 4; i < argc; ++i) {
        std::string pair(argv[i]);
        int a = std::stoi(pair.substr(0, pair.find(':')));
        int b = std::stoi(pair.substr(pair.find(':') + 1));
        tokens.at(a).other = &tokens.at(b);
        tokens.at(b).other = &tokens.at(a);
    }
    Token* result = skipMethodDeclEnding(&tokens.at(std::stoi(argv[2])));
    std::cout << (result ? result->index : -1) << '\n';
}
''')
    binary = directory / 'boundary'
    subprocess.run([compiler, '-std=c++11', '-Wall', '-Wextra', '-Werror',
                    str(source), '-o', str(binary)], check=True, capture_output=True, timeout=30)
    return binary


@pytest.mark.parametrize('tokens,start,end,links,expected', [
    (') requires true : member ( seed ) {', 0, 8, ['5:7'], -1),
    (') requires true : member ( seed ) {', 1, 8, ['5:7'], -1),
    (') requires ns :: C {', 0, 5, [], 5),
    (') requires ( p ? q : r ) {', 0, 9, ['2:8'], 9),
    (') requires ( p ? q : r ) : member {', 0, 11, ['2:8'], -1),
    (') requires C < T > : member {', 0, 8, ['3:5'], -1),
    (') requires C < T > : member {', 0, 8, [], 8),
    (') requires bool { C < T > } : member {', 0, 11, ['3:8', '5:7'], -1),
    (') requires bool { p ? q : r } {', 0, 10, ['3:9'], 10),
    (') requires [ p : q ] {', 0, 7, ['2:6'], 7),
    (') requires [ p : q ] : member {', 0, 9, ['2:6'], -1),
    (') noexcept ( p ? q : r ) requires true {', 0, 11, ['2:8'], 11),
    (') -> decltype ( p ? q : r ) {', 0, 10, ['3:9'], 10),
    (') requires true { : }', 0, 3, [], 3),
    (') {', 0, 1, [], -1),
    (') requires true {', 0, -1, [], -1),
    ('name requires true {', 0, 3, [], -1),
    ('name requires true {', 1, 3, [], -1),
    # A delimiter link crossing the candidate endpoint must terminate the scan.
    (') requires ( p { : )', 0, 4, ['2:6'], 4),
])
def test_boundary_decisions(boundary_runner, tokens, start, end, links, expected):
    result = subprocess.run([str(boundary_runner), tokens, str(start), str(end), *links],
                            check=True, capture_output=True, text=True, timeout=5)
    assert int(result.stdout) == expected


@pytest.mark.parametrize('opener', ['<', '[', '(', '{'])
def test_unlinked_delimiter_retains_old_endpoint(boundary_runner, opener):
    result = subprocess.run([str(boundary_runner), f') requires {opener} : x {{', '0', '5'],
                            check=True, capture_output=True, text=True, timeout=5)
    assert int(result.stdout) == 5
