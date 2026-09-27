# Full-run result and Clang/GCC runtime alignment

Run [36235924285](https://github.com/BoneManTGRM/NICO/actions/runs/36235924285)
completed on the published collection correction `8dc23f905f42ef63123edf998610d55c0f313070`.
The full qualification failed; its evidence was retained in artifact `10904614857`.
The archive SHA-256 is `89d7ccc1dd290979c9af2d6f05db1740a0ff56cf468b6ad293a6637941aedea0`.

| Required population | Retained result |
| --- | --- |
| Baseline native tests | 377/377 passed |
| Compiler contexts | 475/475 checked |
| Static analysis contexts | 475/475 analyzed |
| Selected functional tests | 6/6 passed |
| AddressSanitizer tests | 377/377 passed |
| UndefinedBehaviorSanitizer tests | 376/377 passed; `net_tests` failed |
| Fuzz corpus staging and CMake configure | Both executed and passed |
| Fuzz build | Failed linking `mpgen` at approximately 60%; exit 2 after 550.166 seconds |
| Fuzz replay and campaign | Not executed because the build failed |

The collection correction worked in this complete workload: it preserved
`runtime-undefined-tests` as the first failure, then collected independent fuzz
setup and build results. The final failure operation is `runtime-fuzz-build`;
`complete` and production qualification remain false. The original UBSan
diagnostic at frozen `src/streams.cpp:99:24` remains an open failed finding.

The new build diagnostic is `undefined reference to __cxa_call_terminate` in the
GCC-14-built `/usr/local/lib/libcapnp.a` and `libcapnpc.a`. The operation neither
timed out nor truncated its output. `native-fuzz-build.json` binds the decoded
`native-fuzz-build.log` to the retained operation and archive.

## Mechanism and correction

The pinned full-project image installs GCC 14.2.0 under `/usr/local`; its Cap'n
Proto builder uses that compiler. Clang 17's default GCC discovery searches its
own installation and distribution prefixes, which do not select this GCC.
Setting `LD_LIBRARY_PATH` affects runtime loading but does not select the GCC
installation used by the Clang driver when compiling and linking.

The image now supplies `--gcc-toolchain=/usr/local` through Clang's documented
driver configuration files. This selects the headers and runtime belonging to
the compiler that built the static dependencies. The immutable image digest
already binds this provisioning choice to each native receipt; execution plan
and retained evidence schemas and command arguments do not change.

Primary implementation references:

- [Clang 17 GCC toolchain selection](https://releases.llvm.org/17.0.1/tools/clang/docs/ClangCommandLineReference.html)
- [Clang 17 default driver configuration](https://releases.llvm.org/17.0.1/tools/clang/docs/UsersManual.html#configuration-files)
- [Pinned LLVM 17.0.6 GCC discovery implementation](https://github.com/llvm/llvm-project/blob/llvmorg-17.0.6/clang/lib/Driver/ToolChains/Gnu.cpp)

The image must pass an owned native control before qualification starts:

1. Verify exact compiler versions, matching GCC/Clang library paths, and GCC 14 C++ headers.
2. Compile a small owned object that instantiates the actual pinned Cap'n Proto types.
3. Link that object and the same static archives with default configuration disabled;
   require the original missing-symbol failure.
4. Link and execute the object with the corrected default configuration.
5. Build and execute an owned libFuzzer control using AddressSanitizer and
   UndefinedBehaviorSanitizer against those same archives.

The control records every invocation and result. An unexpected negative result,
failed positive control, timeout, missing compiler, or mismatched headers/runtime
fails image construction. CI retains the control receipt as `cpp-runtime-toolchain.json`.
The control uses owned source only and cannot establish completion of the Bitcoin
fuzz stages. The existing image and native execution time limits remain unchanged.

## Completion boundary

Local Python verification and data-only revalidation are recorded separately.
The exact-image native control and a new full Bitcoin execution are required
before claiming this correction is verified. The UBSan finding, authenticated
replay of `comprun_34a469900baa742c0d557f42634b318f`, and complete review of both
PRs remain release requirements. Neither PR is merged and production is unchanged.
