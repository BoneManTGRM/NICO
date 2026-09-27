# Retained UBSan finding — open source-bound diagnostic

The failed result remains open. This disposition does not mark the test passed,
establish exploitability, change Bitcoin, suppress UBSan, or grant qualification.

- Target: `bitcoin/bitcoin` at `bb5296576e8f1a9fc11c19d9a25ba02ed4547e24`.
- NICO execution: run `36207402575`, head `0c8ed5758cfae7ef66eb749655dc2ea9e9fe8c81`.
- Artifact: `10896373460`, SHA-256 `d460f23b62fc54474a5fb2aa0880f54b7b1d71d009af3b06c16c87632d533286`.
- Population: 377 CTest records returned, 376 passed, one failed; `net_tests` took 0.999795 seconds. CTest exited 8 without a controller timeout.
- Retained diagnostic: `/work/source/src/streams.cpp:99:24: runtime error: null pointer passed as argument 1, which is declared to never be null`.
- Exact source: `AutoFile::write(std::span<const std::byte> src)` passes `src.data()` to `std::fwrite` in its non-obfuscated branch. The preceding guard checks the file handle, not the data pointer.
- The retained output enters `initial_advertise_from_version_message` and records a zero-byte `wtxidrelay` message just before the diagnostic. An empty-span path is a plausible explanation, not a proven call stack or exploitability finding.

The NICO correction addresses collection control flow: independent later checks
may run only after a fully returned, valid CTest population with explicit Failed
records. The failed sanitizer and `complete=false` remain authoritative. Missing
results, timeouts, and execution infrastructure failures still abort. Historical
evidence retains its original semantics.

Resolution still requires the applicable independent source/toolchain review and
native evidence for the remaining stages. Neither this note nor later successful
fuzzing can silently turn the retained failed test into a clean qualification.
