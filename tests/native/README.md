# Pinned Cppcheck AST regressions

These are owned tests of the composed parser, not full native project qualification. They assert
AST parent/child links for constructor initializer arguments, preserve variable
IDs through the normal tokenizer, check `noexcept`/`decltype` call ASTs, and retain
function declarators without losing pointer-conversion argument ASTs.
The parser fixtures are not a claim of compiler acceptance for every form (in
particular the unparenthesized `requires bool{...}` case follows an existing
Cppcheck parser idiom). No real GCC header or project failure is reproduced.

Use a fresh official Cppcheck 2.17.1 checkout at
`ac9db3069b9f90e81e126a090b99ad456e122cf8`. Set `NICO_AST` to this NICO checkout,
`CPPCHECK_AST` to that fresh upstream checkout, and `AST_RESULTS` to a new local
evidence directory. Use absolute paths for all three variables. No container,
service, workflow, or baseline binary is needed.

```sh
set -e
mkdir -p "$AST_RESULTS"
cd "$CPPCHECK_AST"
test "$(git rev-parse HEAD)" = ac9db3069b9f90e81e126a090b99ad456e122cf8
python3 "$NICO_AST/scripts/repair_cppcheck_placement_ast.py" lib/tokenlist.cpp > "$AST_RESULTS/repair-receipt.json"
python3 "$NICO_AST/scripts/repair_cppcheck_header_grammar.py" "$CPPCHECK_AST" > "$AST_RESULTS/grammar-receipt.json"
python3 "$NICO_AST/scripts/patch_cppcheck_header_evidence.py" "$CPPCHECK_AST" "$NICO_AST/scripts/cppcheck-header-evidence" > "$AST_RESULTS/observer-receipt.json"
timeout 180s make -j2 testrunner 'TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o test/testtokenize.o test/testvarid.o test/testtokenlist.o test/testtoken.o test/testpreprocessor.o test/testcppcheck.o test/testsimplifytemplate.o test/testsimplifytypedef.o' 'CXXFLAGS=-O0'
timeout 180s ./testrunner TestTokenizer TestVarID TestTokenList TestToken TestPreprocessor TestCppcheck TestSimplifyTemplate TestSimplifyTypedef > "$AST_RESULTS/upstream-tests.txt" 2>&1
cp testrunner "$AST_RESULTS/upstream-testrunner"
timeout 60s g++ -std=c++11 -O0 -Ilib -Itest -Iexternals/simplecpp -Iexternals/tinyxml2 -c "$NICO_AST/tests/native/cppcheck_constructor_ast.cpp" -o "$AST_RESULTS/nicoast.o"
timeout 60s make -j2 testrunner "TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o $AST_RESULTS/nicoast.o" 'CXXFLAGS=-O0'
timeout 60s ./testrunner > "$AST_RESULTS/owned-tests.txt" 2>&1
```

Run the owned runner without a class filter and verify its nonzero test count.
The owned fixture deliberately uses upstream's friend class name `TestTokenizer`
but displays `TestNicoConstructorAst`; never link it alongside upstream
`testtokenize.o`. Separate binaries avoid duplicate class definitions and require
no production header modification.

For call-site evidence, instrument only the patched translation unit and relink
the owned runner:

```sh
set -e
timeout 60s g++ -std=c++11 -O0 --coverage -Ilib -Iexternals/simplecpp -Iexternals/tinyxml2 -c lib/tokenlist.cpp -o lib/tokenlist.o
timeout 60s make -j2 testrunner "TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o $AST_RESULTS/nicoast.o" 'CXXFLAGS=-O0' 'LDFLAGS=--coverage'
timeout 60s ./testrunner > "$AST_RESULTS/coverage-tests.txt" 2>&1
timeout 60s gcov -b -c lib/tokenlist.cpp > "$AST_RESULTS/coverage-summary.txt"
```

Inspect `tokenlist.cpp.gcov` at both `skipMethodDeclEnding` call sites. This
measures execution of the actual helper calls, unlike the Python test's controlled
Token shim. Python boundary tests run in the existing contract-regressions job;
these native builds remain explicit local tests and have not been added to CI.
