# Pinned Cppcheck AST regressions

These are owned parser tests, not full native project qualification. They assert
AST parent/child links for constructor initializer arguments, preserve variable
IDs through the normal tokenizer, and check `noexcept`/`decltype` call ASTs.
The parser fixtures are not a claim of compiler acceptance for every form (in
particular the unparenthesized `requires bool{...}` case follows an existing
Cppcheck parser idiom). No real GCC header or project failure is reproduced.

Use a fresh official Cppcheck 2.17.1 checkout at
`ac9db3069b9f90e81e126a090b99ad456e122cf8`. Set `NICO_AST` to this NICO checkout,
`CPPCHECK_AST` to that fresh upstream checkout, and `AST_RESULTS` to a new local
evidence directory. No container, service, workflow, or baseline binary is needed.

```sh
mkdir -p "$AST_RESULTS"
cd "$CPPCHECK_AST"
test "$(git rev-parse HEAD)" = ac9db3069b9f90e81e126a090b99ad456e122cf8
python3 "$NICO_AST/scripts/repair_cppcheck_placement_ast.py" lib/tokenlist.cpp > "$AST_RESULTS/repair-receipt.json"
make -j2 testrunner 'TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o test/testtokenize.o test/testvarid.o test/testtokenlist.o' 'CXXFLAGS=-O0'
./testrunner TestTokenizer TestVarID TestTokenList > "$AST_RESULTS/upstream-tests.txt" 2>&1
cp testrunner "$AST_RESULTS/upstream-testrunner"
g++ -std=c++11 -O0 -Ilib -Itest -Iexternals/simplecpp -Iexternals/tinyxml2 -c "$NICO_AST/tests/native/cppcheck_constructor_ast.cpp" -o "$AST_RESULTS/nicoast.o"
make -j2 testrunner "TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o $AST_RESULTS/nicoast.o" 'CXXFLAGS=-O0'
./testrunner > "$AST_RESULTS/owned-tests.txt" 2>&1
```

Run the owned runner without a class filter and verify its nonzero test count.
The owned fixture deliberately uses upstream's friend class name `TestTokenizer`
but displays `TestNicoConstructorAst`; never link it alongside upstream
`testtokenize.o`. Separate binaries avoid duplicate class definitions and require
no production header modification.

For call-site evidence, instrument only the patched translation unit and relink
the owned runner:

```sh
g++ -std=c++11 -O0 --coverage -Ilib -Iexternals/simplecpp -Iexternals/tinyxml2 -c lib/tokenlist.cpp -o lib/tokenlist.o
make -j2 testrunner "TESTOBJ=test/fixture.o test/helpers.o test/main.o test/options.o $AST_RESULTS/nicoast.o" 'CXXFLAGS=-O0' 'LDFLAGS=--coverage'
./testrunner > "$AST_RESULTS/coverage-tests.txt" 2>&1
gcov -b -c lib/tokenlist.cpp > "$AST_RESULTS/coverage-summary.txt"
```

Inspect `tokenlist.cpp.gcov` at both `skipMethodDeclEnding` call sites. This
measures execution of the actual helper calls, unlike the Python test's controlled
Token shim. Python boundary tests run in the existing contract-regressions job;
these native builds remain explicit local tests and have not been added to CI.
